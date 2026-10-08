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
from wa_model import (COVID, FEATURE_LABELS, MODEL_NAMES, Final,  # noqa: E402
                   backtest, build_features, score)
from wa_sources import load_abs, load_fred  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "wa"
OUT = ROOT / "data" / "wa_economy.js"


def r(x, n=2):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), n)


def qlabel(p: pd.Period) -> str:
    months = {1: "Jan to Mar", 2: "Apr to Jun", 3: "Jul to Sep", 4: "Oct to Dec"}
    return f"{months[p.quarter]} {p.year}"


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
    q = {k: v[0] for k, v in allser.items()}

    df = build_features(q)
    feats = [c for c in df.columns if c != "target"]
    print(f"Features ({len(feats)}): {', '.join(feats)}")

    known = df.dropna(subset=["target"])
    last_known = known.index.max()
    nxt = last_known + 1
    if nxt not in df.index or df.loc[[nxt], feats].drop(columns=["sfd_l1", "sfd_l2"]).notna().sum(axis=1).iloc[0] == 0:
        raise SystemExit(f"No indicator data yet for {nxt}; nothing to nowcast.")

    print("Backtesting...")
    bt = backtest(df, feats)
    sc = score(bt)
    print(sc.round(3).to_string())

    contenders = sc.loc[["ridge", "forest", "boost", "blend"]]
    choice = contenders["rmse"].idxmin()
    beat_naive = sc.at[choice, "rmse"] < sc.at["naive", "rmse"]
    beat_ar = sc.at[choice, "rmse"] < sc.at["ar", "rmse"]

    err = (bt[choice] - bt["actual"])[~bt.index.isin(COVID)]
    lo_e, hi_e = np.quantile(err, [0.1, 0.9])

    fin = Final(choice, df, feats)
    row = df.loc[[nxt], feats]
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
            "model": r(bt.at[p, choice]) if p in bt.index else None,
            "covid": p in COVID,
        })

    level = q["sfd"].dropna()
    indicators = []
    for k, (s, label, src) in allser.items():
        s = s.dropna()
        if s.empty:
            continue
        prev = s.iloc[-5] if len(s) > 4 else np.nan
        indicators.append({
            "id": k, "label": label, "source": src, "period": qlabel(s.index[-1]),
            "latest": r(s.iloc[-1], 3), "year_ago": r(prev, 3),
            "series": [[str(i), r(v, 3)] for i, v in s[s.index >= pd.Period("2015Q1", "Q")].items()],
        })

    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "target": "Quarterly growth in WA State Final Demand, chain volume, seasonally adjusted (%)",
        "last_published": {"q": str(last_known), "label": qlabel(last_known),
                           "growth": r(known.at[last_known, "target"]),
                           "level_millions": r(level.iloc[-1], 0)},
        "nowcast": {
            "q": str(nxt), "label": qlabel(nxt),
            "point": r(point), "lo": r(point + lo_e), "hi": r(point + hi_e),
            "model": choice, "model_name": MODEL_NAMES[choice],
        },
        "accuracy": {
            "rmse": r(sc.at[choice, "rmse"]), "naive_rmse": r(sc.at["naive", "rmse"]),
            "ar_rmse": r(sc.at["ar", "rmse"]), "beats_naive": bool(beat_naive),
            "beats_ar": bool(beat_ar), "within_half_point": r(within, 3),
            "quarters_tested": int(sc.at[choice, "n"]), "from": str(bt.index.min()),
        },
        "models": [{"id": i, **{k: (r(v, 3) if isinstance(v, float) else v)
                                for k, v in rw.items()}} for i, rw in sc.iterrows()],
        "importance": [{"id": f, "label": FEATURE_LABELS.get(f, f), "value": r(v, 4)}
                       for f, v in imp.items()],
        "drivers": [{"id": f, "label": FEATURE_LABELS.get(f, f), "value": r(v, 3),
                     "input": r(row[f].iloc[0], 2)}
                    for f, v in drv.items() if pd.notna(row[f].iloc[0])],
        "history": hist,
        "indicators": indicators,
        "notes": notes,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("window.WA_ECONOMY = " + json.dumps(out, separators=(",", ":")) + ";\n", encoding="utf-8")
    print(f"\nNowcast {nxt}: {point:+.2f}% (80% range {point+lo_e:+.2f} to {point+hi_e:+.2f}) using {choice}")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
