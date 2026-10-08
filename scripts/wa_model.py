"""
Nowcasting model for the WA economy page (wa-economy.html).

Target: quarterly growth in WA State Final Demand (chain volume,
seasonally adjusted), the ABS's quarterly measure of spending in WA.
Gross State Product is only published once a year, so SFD is the
closest quarterly read on the state economy.

The model "nowcasts" a quarter: it uses indicators that come out during
or shortly after the quarter (jobs, hours, prices, approvals, iron ore,
oil, the dollar) to estimate SFD growth before the ABS publishes it,
roughly two months after the quarter ends.

Candidate models are compared with an expanding-window backtest, each
quarter predicted using only data before it. The best one by backtest
error is used for the headline nowcast; the range comes from its own
past errors.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

SEED = 7
COVID = {pd.Period("2020Q2", "Q"), pd.Period("2020Q3", "Q")}
BACKTEST_FROM = pd.Period("2010Q1", "Q")

FEATURE_LABELS = {
    "sfd_l1": "Last quarter's demand growth",
    "sfd_l2": "Demand growth 2 quarters ago",
    "d_unemp": "Unemployment rate change",
    "emp_g": "Jobs growth",
    "hours_g": "Hours worked growth",
    "spend_g": "Household spending growth",
    "cpi_y_l1": "Perth inflation (yearly, last quarter)",
    "wpi_y_l1": "Wage growth (yearly, last quarter)",
    "dwell_y": "Dwelling approvals (yearly)",
    "iron_g": "Iron ore in A$, this quarter",
    "iron_g_l1": "Iron ore in A$, last quarter",
    "iron_y": "Iron ore in A$, over the year",
    "brent_g": "Oil price growth",
    "aud_g": "Australian dollar movement",
}
# series that come out monthly; features from these use the latest three months
MONTHLY = ["unemp", "emp", "hours", "hsi", "retail", "dwell", "iron", "brent", "audusd"]
# months between a reference month and a run on the 20th that can use it
# (Labour Force mid-month, FRED monthly averages early next month,
# household spending and approvals in the first days of the month after next)
LAG = {"unemp": 1, "emp": 1, "hours": 1, "brent": 1, "iron": 1, "audusd": 1,
       "hsi": 2, "retail": 2, "dwell": 2}
# the three points in a quarter where a monthly run (on the 20th) nowcasts it,
# as months after the quarter's first month: two months of jobs data in,
# all three, and all three with every other monthly series complete
STAGES = {"2 months in": 2, "3 months in": 3, "all monthly data in": 4}


def pct(s: pd.Series, n: int = 1) -> pd.Series:
    return 100 * (s / s.shift(n) - 1)


def _roll3(s: pd.Series) -> pd.Series:
    """Average of the latest three months, on a gap-free monthly index."""
    s = s.reindex(pd.period_range(s.index.min(), s.index.max(), freq="M"))
    return s.rolling(3, min_periods=3).mean()


def _at_quarter(f: pd.Series) -> pd.Series:
    """Each quarter takes the value at its latest available month. For a full
    quarter that is the usual quarter-on-quarter figure; for a quarter with one
    or two months in, it compares the latest three months with the three before,
    so the window is always the same length."""
    f = f.dropna()
    return f.groupby(f.index.asfreq("Q")).last()


def build_features(q: dict[str, pd.Series], m: dict[str, pd.Series] | None = None,
                   cutoff: pd.Period | None = None) -> pd.DataFrame:
    """q holds quarterly series and m monthly ones, keyed by short name.
    cutoff (a month) rebuilds the features as a run on the 20th of that month
    would have seen them: each monthly series stops LAG months earlier, and
    quarterly ABS figures stop before the cutoff's quarter. Returns target + features."""
    m = dict(m or {})
    q = dict(q)
    if cutoff is not None:
        m = {k: v[v.index <= cutoff - LAG.get(k, 1)] for k, v in m.items()}
        cq = cutoff.asfreq("Q")
        q = {k: (v[v.index < cq] if k != "sfd" else v) for k, v in q.items()}
    lo = min(s.index.min() for s in q.values())
    hi = max([s.index.max() for s in q.values()] + [v.index.max().asfreq("Q") for v in m.values()])
    idx = pd.period_range(lo, hi, freq="Q")
    d = pd.DataFrame({k: v.reindex(idx) for k, v in q.items()})
    R = {k: _roll3(v) for k, v in m.items() if k in MONTHLY and len(v)}
    X = pd.DataFrame(index=idx)
    y = pct(d["sfd"])
    X["sfd_l1"] = y.shift(1)
    X["sfd_l2"] = y.shift(2)
    mq = lambda f: _at_quarter(f).reindex(idx)  # noqa: E731
    if "unemp" in R:
        X["d_unemp"] = mq(R["unemp"] - R["unemp"].shift(3))
    if "emp" in R:
        X["emp_g"] = mq(pct(R["emp"], 3))
    if "hours" in R:
        X["hours_g"] = mq(pct(R["hours"], 3))
    if "hsi" in R or "retail" in R:
        # the spending indicator where it exists, retail turnover before it
        g = [pct(R[k], 3) for k in ("hsi", "retail") if k in R]
        X["spend_g"] = mq(g[0].combine_first(g[1]) if len(g) == 2 else g[0])
    # CPI and wages for the quarter being estimated are never out in time, so use last quarter's
    if "cpi" in d:
        X["cpi_y_l1"] = pct(d["cpi"], 4).shift(1)
    if "wpi" in d:
        X["wpi_y_l1"] = pct(d["wpi"], 4).shift(1)
    if "dwell" in R:
        # approvals are not seasonally adjusted for WA, so compare with a year earlier
        X["dwell_y"] = mq(100 * np.log(R["dwell"] / R["dwell"].shift(12)))
    if "iron" in R:
        iron_aud = R["iron"] / R["audusd"] if "audusd" in R else R["iron"]
        X["iron_g"] = mq(pct(iron_aud, 3))
        X["iron_g_l1"] = X["iron_g"].shift(1)
        X["iron_y"] = mq(pct(iron_aud, 12))
    if "brent" in R:
        X["brent_g"] = mq(pct(R["brent"], 3))
    if "audusd" in R:
        X["aud_g"] = mq(pct(R["audusd"], 3))
    X = X.replace([np.inf, -np.inf], np.nan)
    # drop features that are mostly empty
    if cutoff is None:
        X = X.loc[:, X.notna().mean() > 0.5]
    X["target"] = y
    return X


def make_models() -> dict:
    imp = lambda: SimpleImputer(strategy="median")  # noqa: E731
    return {
        "naive": None,  # mean of the last eight quarters, handled below
        "ar": ("ar", lambda: make_pipeline(imp(), LinearRegression())),
        "ridge": ("all", lambda: make_pipeline(imp(), StandardScaler(),
                                               RidgeCV(alphas=np.logspace(-2, 3, 30)))),
        "forest": ("all", lambda: make_pipeline(imp(), RandomForestRegressor(
            n_estimators=400, min_samples_leaf=3, max_features=0.5, random_state=SEED, n_jobs=-1))),
        "boost": ("all", lambda: HistGradientBoostingRegressor(
            max_depth=3, learning_rate=0.04, max_iter=250, min_samples_leaf=8,
            l2_regularization=1.0, random_state=SEED)),
    }


MODEL_NAMES = {
    "naive": "Recent average (benchmark)",
    "ar": "Momentum only (benchmark)",
    "ridge": "Ridge regression",
    "forest": "Random forest",
    "boost": "Gradient boosting",
    "blend": "Blend of the three",
}
ML = ["ridge", "forest", "boost"]


def _cols(kind: str, feats: list[str]) -> list[str]:
    return ["sfd_l1", "sfd_l2"] if kind == "ar" else feats


def fit_predict(train: pd.DataFrame, test: pd.DataFrame, feats: list[str]) -> dict:
    out = {"naive": np.repeat(train["target"].iloc[-8:].mean(), len(test))}
    tr = train[~train.index.isin(COVID)]
    for name, spec in make_models().items():
        if spec is None:
            continue
        kind, factory = spec
        cols = _cols(kind, feats)
        m = factory().fit(tr[cols], tr["target"])
        out[name] = m.predict(test[cols])
    out["blend"] = np.mean([out[k] for k in ML], axis=0)
    return out


def backtest(df: pd.DataFrame, feats: list[str], q: dict | None = None,
             m: dict | None = None) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """Expanding-window backtest. The first frame scores each quarter with all of
    its data; given the raw series, the second scores it at each STAGE, using
    only what a monthly run at that point would have had."""
    known = df.dropna(subset=["target", "sfd_l1"])
    rows, staged = [], {k: [] for k in STAGES}
    for t in known.index[known.index >= BACKTEST_FROM]:
        train = known[known.index < t]
        if len(train) < 40:
            continue
        tests = [known.loc[[t], feats]]
        if q is not None:
            first = t.asfreq("M", how="start")
            tests += [build_features(q, m, first + n).reindex([t])[feats] for n in STAGES.values()]
        p = fit_predict(train, pd.concat(tests), feats)
        actual = known.at[t, "target"]
        rows.append({"q": t, "actual": actual, **{k: float(v[0]) for k, v in p.items()}})
        for i, name in enumerate(STAGES, start=1):
            if q is not None:
                staged[name].append({"q": t, "actual": actual, **{k: float(v[i]) for k, v in p.items()}})
    stages = {k: pd.DataFrame(v).set_index("q") for k, v in staged.items() if v}
    return pd.DataFrame(rows).set_index("q"), stages


def score(bt: pd.DataFrame) -> pd.DataFrame:
    b = bt[~bt.index.isin(COVID)]
    res = []
    for k in MODEL_NAMES:
        e = b[k] - b["actual"]
        res.append({
            "id": k, "name": MODEL_NAMES[k],
            "rmse": float(np.sqrt((e ** 2).mean())),
            "mae": float(e.abs().mean()),
            # share of quarters where it got the direction relative to trend right
            # (undefined for the recent average itself, which is the reference)
            "direction": np.nan if k == "naive" else float(
                ((b[k] - b["naive"]).apply(np.sign) == (b["actual"] - b["naive"]).apply(np.sign)).mean()),
            "n": int(len(b)),
        })
    return pd.DataFrame(res).set_index("id")


class Final:
    """The chosen model refitted on all known quarters."""

    def __init__(self, choice: str, df: pd.DataFrame, feats: list[str]):
        self.choice, self.feats = choice, feats
        known = df.dropna(subset=["target", "sfd_l1"])
        self.train = known[~known.index.isin(COVID)]
        names = ML if choice == "blend" else [choice]
        self.models = []
        for n in names:
            kind, factory = make_models()[n]
            cols = _cols(kind, feats)
            self.models.append((cols, factory().fit(self.train[cols], self.train["target"])))

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.mean([m.predict(X[c]) for c, m in self.models], axis=0)

    def importance(self, repeats: int = 25) -> pd.Series:
        rng = np.random.default_rng(SEED)
        X, y = self.train[self.feats], self.train["target"].values
        base = np.sqrt(((self.predict(X) - y) ** 2).mean())
        imp = {}
        for f in self.feats:
            gains = []
            for _ in range(repeats):
                Xp = X.copy()
                Xp[f] = rng.permutation(Xp[f].values)
                gains.append(np.sqrt(((self.predict(Xp) - y) ** 2).mean()) - base)
            imp[f] = float(np.mean(gains))
        return pd.Series(imp).sort_values(ascending=False)

    def drivers(self, row: pd.DataFrame) -> pd.Series:
        """How much each indicator moves this estimate away from an
        'ordinary quarter' (every indicator at its usual level)."""
        typical = self.train[self.feats].median()
        out = {}
        p = self.predict(row)[0]
        for f in self.feats:
            r = row.copy()
            r[f] = typical[f] if pd.notna(row[f].iloc[0]) else np.nan
            out[f] = float(p - self.predict(r)[0])
        return pd.Series(out).sort_values(key=np.abs, ascending=False)
