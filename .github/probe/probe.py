"""Temporary probe: ABS construction and capital expenditure dataflows with WA data."""
import re, sys
import pandas as pd, requests
sys.path.insert(0, "scripts")
import wa_sources as w
J = {**w.UA, "Accept": "application/vnd.sdmx.structure+json"}
j = requests.get("https://data.api.abs.gov.au/rest/dataflow/ABS", headers=J, timeout=60).json()
flows = [f for f in j["data"]["dataflows"] if re.search(r"construction|capital expenditure|capex|engineering|building activity|investment", f["name"], re.I)]
for f in flows:
    print(f["id"], "|", f["name"])
for f in flows:
    fid = f["id"]
    try:
        s = requests.get(f"https://data.api.abs.gov.au/rest/datastructure/ABS/{fid}", headers=J, timeout=60).json()
        ids = [d["id"] for d in sorted(s["data"]["dataStructures"][0]["dataStructureComponents"]["dimensionList"]["dimensions"], key=lambda d: d.get("position", 0))]
    except Exception as e:
        print(fid, "structure failed", e); continue
    reg = next((d for d in ids if d in ("REGION", "STATE")), None)
    print(f"\n=== {fid} dims {ids}")
    if reg is None:
        continue
    key = ".".join("5" if d == reg else "Q" if d == "FREQ" else "" for d in ids)
    r = requests.get(f"{w.ABS_BASE}/ABS,{fid},/{key}?startPeriod=1980-01&format=csvfilewithlabels", headers=w.UA, timeout=240)
    print("key", key, "HTTP", r.status_code, f"{len(r.text)/1e6:.2f}MB")
    if r.status_code != 200:
        print(r.text[:200]); continue
    df = w.parse_abs_csv(r.text).dropna(subset=["OBS_VALUE"])
    dims = [c for c in df.columns if not c.endswith("__code") and c not in ("TIME_PERIOD", "OBS_VALUE")]
    g = df.groupby([c for d in dims for c in (d + "__code", d)]).agg(first=("TIME_PERIOD", "min"), last=("TIME_PERIOD", "max"), n=("TIME_PERIOD", "size")).reset_index()
    # keep the headline totals: rows where every non-measure dimension is a total
    keep = g.copy()
    for d in dims:
        if d in ("MEASURE", "TSEST", reg, "FREQ", "PRICE_ADJUSTMENT", "UNIT_MEASURE"):
            continue
        tot = keep[d].str.contains(r"total|all", case=False, na=False)
        if tot.any():
            keep = keep[tot]
    with pd.option_context("display.width", 500, "display.max_colwidth", 55, "display.max_rows", 80):
        print(keep.drop(columns=[c for c in keep.columns if c.startswith((reg, "FREQ"))]).head(80).to_string(index=False))
