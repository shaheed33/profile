"""
Builds data/wa_economy.js for wa-economy.html. Downloads the ABS and FRED
series into raw/wa/, backtests the models and writes the nowcast.

    python scripts/build_wa_economy.py              # live download
    python scripts/build_wa_economy.py --offline    # reuse files in raw/wa/
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from wa_model import (COVID, FEATURE_LABELS, MODEL_NAMES, SURVEYS, Final,  # noqa: E402
                      backtest, base_feats, build_features, score)
from wa_sources import SITE_ONLY, load_abs, load_fred  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "wa"
OUT = ROOT / "data" / "wa_economy.js"


def r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def qlabel(p: pd.Period) -> str:
    months = {1: "Jan to Mar", 2: "Apr to Jun", 3: "Jul to Sep", 4: "Oct to Dec"}
    return f"{months[p.quarter]} {p.year}"


def perth_inflation(allser: dict) -> dict | None:
    """The Perth inflation tracker. Not a model: the ABS publishes Perth CPI each
    month, and the quarterly index is the average of its three months, so the
    quarter is mostly known before its release. Months still to come are filled
    in at the typical monthly rise of the past year, with a range from the spread
    of past monthly moves."""
    if "cpi_m" not in allser or "cpi" not in allser:
        return None
    mon = allser["cpi_m"][3].dropna()
    qtr = allser["cpi"][0].dropna()
    if len(mon) < 15:
        return None
    last_m = mon.index[-1]
    cq = last_m.asfreq("Q")
    if cq in qtr.index:          # the quarter is already published: track the next one
        cq = cq + 1
    have = [p for p in mon.index if p.asfreq("Q") == cq]
    todo = 3 - len(have)
    g = mon.pct_change().dropna()
    typical = float(g.iloc[-12:].median())
    lo_g, hi_g = (float(x) for x in np.quantile(g, [0.1, 0.9]))

    def quarter_index(step):
        vals = [float(mon[p]) for p in have]
        level = float(mon[last_m])
        for _ in range(todo):
            level *= 1 + step
            vals.append(level)
        return float(np.mean(vals))

    prev_q = qtr.get(cq - 1, np.nan)
    year_q = qtr.get(cq - 4, np.nan)
    est = {k: quarter_index(v) for k, v in [("point", typical), ("lo", lo_g), ("hi", hi_g)]}
    # check the averaging rule on quarters with all three months published
    checks = []
    for p in sorted({m.asfreq("Q") for m in mon.index}):
        ms = [m for m in mon.index if m.asfreq("Q") == p]
        # the quarterly CPI has been built from the monthly one since Oct to Dec 2025
        if len(ms) == 3 and p in qtr.index and p >= pd.Period("2025Q4", "Q"):
            checks.append(abs(float(mon[ms].mean()) - float(qtr[p])))
    year_m = mon.get(last_m - 12, np.nan)
    hist = qtr.pct_change(4).dropna() * 100
    return {
        "quarter": str(cq), "label": qlabel(cq), "months_in": len(have),
        "latest_month": last_m.strftime("%b %Y"),
        "latest_annual": r(100 * (float(mon[last_m]) / year_m - 1)) if pd.notna(year_m) else None,
        "latest_monthly": r(100 * float(g.iloc[-1])),
        "q_annual": {k: r(100 * (v / year_q - 1)) for k, v in est.items()} if pd.notna(year_q) else None,
        "q_quarterly": {k: r(100 * (v / prev_q - 1)) for k, v in est.items()} if pd.notna(prev_q) else None,
        "last_q": {"label": qlabel(qtr.index[-1]), "annual": r(hist.iloc[-1])},
        "max_check_gap": r(max(checks), 3) if checks else None,
        "monthly": [[p.strftime("%Y-%m"), r(100 * (float(mon[p]) / float(mon[p - 12]) - 1))]
                    for p in mon.index if (p - 12) in mon.index],
        "history": [[str(p), r(v)] for p, v in hist[hist.index >= pd.Period("2015Q1", "Q")].items()],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use files already in data/raw")
    args = ap.parse_args()

    abs_s, n1 = load_abs(RAW, args.offline)
    fred_s, n2 = load_fred(RAW, args.offline)
    notes = n1 + n2
    for n in notes:
        print("NOTE:", n)
    allser = {**abs_s, **fred_s}
    model_ser = {k: v for k, v in allser.items() if k not in SITE_ONLY}
    q = {k: v[0] for k, v in model_ser.items() if v[3] is None}
    m = {k: v[3] for k, v in model_ser.items() if v[3] is not None}

    df = build_features(q, m)
    feats = [c for c in df.columns if c != "target"]
    print(f"Features ({len(feats)}): {', '.join(feats)}")

    known = df.dropna(subset=["target"])
    last_known = known.index.max()
    nxt = last_known + 1
    if nxt not in df.index or df.loc[[nxt], feats].drop(columns=["sfd_l1", "sfd_l2"]).notna().sum(axis=1).iloc[0] == 0:
        raise SystemExit(f"No indicator data yet for {nxt}; nothing to nowcast.")

    # how far into the quarter being estimated the data runs
    def months_in(k):
        return int((m[k].dropna().index.asfreq("Q") == nxt).sum()) if k in m else 0
    jobs_in = months_in("emp")
    surveys_in = all(k in q and nxt in q[k].dropna().index for k in SURVEYS)
    stage = ("surveys in" if surveys_in else "2 months in" if jobs_in < 3 else
             "3 months in" if months_in("dwell") < 3 else "all monthly data in")
    use = feats if surveys_in else base_feats(feats)
    print(f"Estimating {nxt}: {jobs_in} months of jobs data ({stage})")

    print("Backtesting...")
    bt, stages = backtest(df, feats, q, m)
    sc = score(bt)
    print("With each quarter's full data:")
    print(sc.round(3).to_string())
    ssc = {k: score(v) for k, v in stages.items()}
    for k, v in ssc.items():
        print(f"{k}:")
        print(v[["rmse", "mae", "n"]].round(3).T.to_string())

    # pick the model that does best across the points in a quarter where it is really used
    contenders = ["ridge", "forest", "boost", "blend"]
    avg = pd.concat([v["rmse"] for v in ssc.values()], axis=1).mean(axis=1)
    choice = avg[contenders].idxmin()
    cur = ssc[stage]
    beat_naive = cur.at[choice, "rmse"] < cur.at["naive", "rmse"]
    beat_ar = cur.at[choice, "rmse"] < cur.at["ar", "rmse"]

    # the range comes from past misses at the same point in the quarter
    sb = stages[stage]
    err = (sb[choice] - sb["actual"])[~sb.index.isin(COVID)]
    lo_e, hi_e = np.quantile(err, [0.1, 0.9])

    fin = Final(choice, df, use)
    row = df.loc[[nxt], use]
    point = float(fin.predict(row)[0])
    imp = fin.importance()
    drv = fin.drivers(row)

    # a year of backtest misses, for the "how often it was close" line
    within = float((err.abs() <= 0.5).mean())

    hist = []
    for p in known.index[known.index >= pd.Period("2005Q1", "Q")]:
        hist.append({
            "q": str(p), "label": qlabel(p),
            "actual": r(known.at[p, "target"]),
            "model": r(stages[stage].at[p, choice]) if p in stages[stage].index else None,
            "covid": p in COVID,
        })

    level = q["sfd"].dropna()
    indicators = []
    for k, (s, label, src, mon) in allser.items():
        if k in SITE_ONLY:
            continue
        if mon is not None:
            # latest three months against the same three months a year earlier
            mon = mon.dropna()
            mon = mon.reindex(pd.period_range(mon.index.min(), mon.index.max(), freq="M"))
            s = mon.rolling(3, min_periods=3).mean().dropna()
            prev = s.get(s.index[-1] - 12, np.nan)
            last = s.index[-1]
            period = f"3 months to {last.strftime('%b %Y')}"
            series_pts = s[s.index >= pd.Period("2015-01", "M")]
        else:
            s = s.dropna()
            prev = s.iloc[-5] if len(s) > 4 else np.nan
            period = qlabel(s.index[-1])
            series_pts = s[s.index >= pd.Period("2015Q1", "Q")]
        if s.empty:
            continue
        indicators.append({
            "id": k, "label": label, "source": src, "period": period,
            "latest": r(s.iloc[-1], 3), "year_ago": r(prev, 3),
            "series": [[str(i), r(v, 3)] for i, v in series_pts.items()],
        })

    inflation = perth_inflation(allser)

    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "target": "Quarterly growth in WA State Final Demand, chain volume, seasonally adjusted (%)",
        "last_published": {"q": str(last_known), "label": qlabel(last_known),
                           "growth": r(known.at[last_known, "target"]),
                           "level_millions": r(level.iloc[-1], 0)},
        "nowcast": {
            "q": str(nxt), "label": qlabel(nxt),
            "point": r(point), "lo": r(point + lo_e), "hi": r(point + hi_e),
            "model": choice, "model_name": MODEL_NAMES[choice], "stage": stage,
        },
        "accuracy": {
            "rmse": r(cur.at[choice, "rmse"]), "naive_rmse": r(cur.at["naive", "rmse"]),
            "ar_rmse": r(cur.at["ar", "rmse"]), "beats_naive": bool(beat_naive),
            "beats_ar": bool(beat_ar), "within_half_point": r(within, 3),
            "quarters_tested": int(cur.at[choice, "n"]), "from": str(sb.index.min()),
            "stage": stage, "jobs_months": jobs_in,
            "by_stage": [{"stage": k, "rmse": r(v.at[choice, "rmse"]), "naive_rmse": r(v.at["naive", "rmse"])}
                         for k, v in ssc.items()],
            "recent_rmse": r(float(np.sqrt((err[err.index >= pd.Period("2017Q1", "Q")] ** 2).mean()))),
        },
        "models": [{"id": i, **{k: (r(v, 3) if isinstance(v, float) else v)
                                for k, v in rw.items()}} for i, rw in cur.iterrows()],
        "importance": [{"id": f, "label": FEATURE_LABELS.get(f, f), "value": r(v, 4)}
                       for f, v in imp.items()],
        "drivers": [{"id": f, "label": FEATURE_LABELS.get(f, f), "value": r(v, 3),
                     "input": r(row[f].iloc[0], 2)}
                    for f, v in drv.items() if pd.notna(row[f].iloc[0])],
        "history": hist,
        "indicators": indicators,
        "inflation": inflation,
        "notes": notes,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.WA_ECONOMY = " + json.dumps(out, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"\nNowcast {nxt}: {point:+.2f}% (80% range {point+lo_e:+.2f} to {point+hi_e:+.2f}) using {choice}")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
