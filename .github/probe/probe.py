"""Temporary probe: WA household spending indicator."""
import re, sys
import pandas as pd, requests
sys.path.insert(0, "scripts")
import wa_sources as w
for flow in ["HSI_M", "HSI_Q"]:
    f = flow[-1]
    r = requests.get(f"{w.ABS_BASE}/ABS,{flow},/....5.{f}?startPeriod=1980-01&format=csvfilewithlabels", headers=w.UA, timeout=180)
    print(f"\n=== {flow} HTTP {r.status_code} {len(r.text)/1e6:.1f}MB")
    if r.status_code != 200:
        print(r.text[:300]); continue
    df = w.parse_abs_csv(r.text).dropna(subset=["OBS_VALUE"])
    dims = [c for c in df.columns if not c.endswith("__code") and c not in ("TIME_PERIOD", "OBS_VALUE")]
    g = df.groupby([c for d in dims for c in (d + "__code", d)]).agg(first=("TIME_PERIOD", "min"), last=("TIME_PERIOD", "max"), n=("TIME_PERIOD", "size")).reset_index()
    g = g[g["CATEGORY"].str.contains("total", case=False)] if g["CATEGORY"].str.contains("total", case=False).any() else g
    with pd.option_context("display.width", 400, "display.max_colwidth", 60, "display.max_rows", 200):
        print(g.drop(columns=[c for c in g.columns if c.startswith(("STATE", "FREQ"))]).to_string(index=False))
