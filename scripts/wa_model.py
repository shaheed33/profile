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
    "cpi_y": "Perth inflation (yearly)",
    "wpi_y": "Wage growth (yearly)",
    "dwell_y": "Dwelling approvals (yearly)",
    "iron_g": "Iron ore in A$, this quarter",
    "iron_g_l1": "Iron ore in A$, last quarter",
    "iron_y": "Iron ore in A$, over the year",
    "brent_g": "Oil price growth",
    "aud_g": "Australian dollar movement",
}


def pct(s: pd.Series, n: int = 1) -> pd.Series:
    return 100 * (s / s.shift(n) - 1)


def build_features(q: dict[str, pd.Series]) -> pd.DataFrame:
    """q holds quarterly series keyed by short name. Returns target + features."""
    idx = pd.period_range(min(s.index.min() for s in q.values()),
                          max(s.index.max() for s in q.values()), freq="Q")
    d = pd.DataFrame({k: v.reindex(idx) for k, v in q.items()})
    X = pd.DataFrame(index=idx)
    y = pct(d["sfd"])
    X["sfd_l1"] = y.shift(1)
    X["sfd_l2"] = y.shift(2)
    if "unemp" in d:
        X["d_unemp"] = d["unemp"].diff()
    if "emp" in d:
        X["emp_g"] = pct(d["emp"])
    if "hours" in d:
        X["hours_g"] = pct(d["hours"])
    if "cpi" in d:
        X["cpi_y"] = pct(d["cpi"], 4)
    if "wpi" in d:
        X["wpi_y"] = pct(d["wpi"], 4)
    if "dwell" in d:
        # approvals are not seasonally adjusted for WA, so compare with a year earlier
        X["dwell_y"] = 100 * np.log(d["dwell"] / d["dwell"].shift(4))
    if "iron" in d:
        iron_aud = d["iron"] / d["audusd"] if "audusd" in d else d["iron"]
        X["iron_g"] = pct(iron_aud)
        X["iron_g_l1"] = X["iron_g"].shift(1)
        X["iron_y"] = pct(iron_aud, 4)
    if "brent" in d:
        X["brent_g"] = pct(d["brent"])
    if "audusd" in d:
        X["aud_g"] = pct(d["audusd"])
    X = X.replace([np.inf, -np.inf], np.nan)
    # drop features that are mostly empty
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


def backtest(df: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    known = df.dropna(subset=["target", "sfd_l1"])
    rows = []
    for t in known.index[known.index >= BACKTEST_FROM]:
        train = known[known.index < t]
        if len(train) < 40:
            continue
        p = fit_predict(train, known.loc[[t]], feats)
        rows.append({"q": t, "actual": known.at[t, "target"], **{k: float(v[0]) for k, v in p.items()}})
    return pd.DataFrame(rows).set_index("q")


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
