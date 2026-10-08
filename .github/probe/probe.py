"""Temporary probe: find the household spending and retail dataflows for WA."""
import json, re, sys, time
import pandas as pd, requests
sys.path.insert(0, "scripts")
import wa_sources as w
J = {**w.UA, "Accept": "application/vnd.sdmx.structure+json"}
j = requests.get("https://data.api.abs.gov.au/rest/dataflow/ABS", headers=J, timeout=60).json()
flows = [f for f in j["data"]["dataflows"] if re.search(r"^(HSI|RT|HHS)|spending|retail", f["id"] + " " + f["name"], re.I)]
for f in flows:
    print(f["id"], "|", f["name"])
for f in flows:
    fid = f["id"]
    try:
        s = requests.get(f"https://data.api.abs.gov.au/rest/datastructure/ABS/{fid}", headers=J, timeout=60).json()
        dims = sorted(s["data"]["dataStructures"][0]["dataStructureComponents"]["dimensionList"]["dimensions"], key=lambda d: d.get("position", 0))
        ids = [d["id"] for d in dims]
    except Exception as e:
        print(fid, "structure failed", e); continue
    print(f"\n=== {fid} dims {ids}")
    if "REGION" not in ids or "FREQ" not in ids:
        continue
    key = ".".join("5" if d == "REGION" else "M" if d == "FREQ" else "" for d in ids)
    r = requests.get(f"{w.ABS_BASE}/ABS,{fid},/{key}?startPeriod=1980-01&format=csvfilewithlabels", headers=w.UA, timeout=180)
    print("key", key, "HTTP", r.status_code, f"{len(r.text)/1e6:.1f}MB")
    if r.status_code != 200:
        print(r.text[:200]); continue
    df = w.parse_abs_csv(r.text)
    dims = [c for c in df.columns if not c.endswith("__code") and c not in ("TIME_PERIOD", "OBS_VALUE")]
    g = df.dropna(subset=["OBS_VALUE"]).groupby([c for d in dims for c in (d + "__code", d)]).agg(first=("TIME_PERIOD", "min"), last=("TIME_PERIOD", "max"), n=("TIME_PERIOD", "size")).reset_index()
    tot = g[g.apply(lambda r: all(not re.search(r"total|all|persons|households", str(r[d]), re.I) is None or d in ("MEASURE", "TSEST", "REGION", "FREQ", "UNIT_MEASURE", "PRICE_ADJUSTMENT") for d in dims), axis=1)]
    with pd.option_context("display.width", 400, "display.max_colwidth", 60, "display.max_rows", 120):
        print((tot if len(tot) else g).head(120).to_string(index=False))
