"""Temporary probe: Victorian housing targets source and ABS Victorian housing series."""
import re, sys, json
import pandas as pd, requests
sys.path.insert(0, "scripts")
import wa_sources as w
B = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
url = "https://engage.vic.gov.au/project/developing-a-new-plan-for-Victoria/page/housing-targets-2051"
t = requests.get(url, headers=B, timeout=60).text
for kw in ["Brimbank", "59,500", "59500", "Banyule", "45,500", "Greater Geelong"]:
    for m in list(re.finditer(kw, t))[:3]:
        print(f"[{kw}] ...{t[max(0, m.start() - 300): m.end() + 300]!r}")
print("api-like urls:", sorted(set(re.findall(r'https?://[^"\'\s<>]+(?:api|json|widget|content)[^"\'\s<>]*', t)))[:40])
print("iframes:", re.findall(r'<iframe[^>]+src="([^"]+)"', t)[:10])
print("data attrs:", re.findall(r'data-(?:page|props|state)="([^"]{0,200})', t)[:5])

for flow in ["BA_LGA2025", "BA_LGA2026"]:
    u = f"{w.ABS_BASE}/ABS,{flow},/all?startPeriod=2026-06&endPeriod=2026-06&format=csvfilewithlabels"
    rr = requests.get(u, headers=w.UA, timeout=180)
    print(f"\n=== {flow} HTTP {rr.status_code} {len(rr.text)/1e6:.2f}MB")
    if rr.status_code != 200:
        print(rr.text[:200]); continue
    df = w.parse_abs_csv(rr.text).dropna(subset=["OBS_VALUE"])
    for c in ["MEASURE", "SECTOR", "WORK_TYPE", "BUILDING_TYPE", "REGION_TYPE"]:
        print(c, df[[c + "__code", c]].drop_duplicates().head(12).values.tolist())
    vic = df[df["REGION__code"].str.match(r"^2\d{4}$")]
    print("Vic LGAs", vic["REGION"].nunique(), vic[["REGION__code", "REGION"]].drop_duplicates().head(8).values.tolist())
    for f2 in ["BA_LGA2025", "BA_LGA2026"]:
        pass
# time coverage of each LGA flow (one LGA: Melbourne 24600)
for flow in ["BA_LGA2023", "BA_LGA2024", "BA_LGA2025", "BA_LGA2026"]:
    u = f"{w.ABS_BASE}/ABS,{flow},/all?startPeriod=2019-01&format=csvfilewithlabels&dimensionAtObservation=AllDimensions"
    u = f"{w.ABS_BASE}/ABS,{flow},/1....24600.M?startPeriod=2019-01&format=csvfilewithlabels"
    rr = requests.get(u, headers=w.UA, timeout=180)
    if rr.status_code == 200:
        df = w.parse_abs_csv(rr.text).dropna(subset=["OBS_VALUE"])
        print(flow, "Melbourne coverage", df["TIME_PERIOD"].min(), df["TIME_PERIOD"].max(), len(df))
    else:
        print(flow, rr.status_code, rr.text[:120])

u = f"{w.ABS_BASE}/ABS,BUILDING_ACTIVITY,/.2......Q?startPeriod=2015-01&format=csvfilewithlabels"
rr = requests.get(u, headers=w.UA, timeout=240)
print("\n=== BUILDING_ACTIVITY Vic", rr.status_code, f"{len(rr.text)/1e6:.1f}MB")
if rr.status_code == 200:
    df = w.parse_abs_csv(rr.text).dropna(subset=["OBS_VALUE"])
    g = df[df["MEASURE"].str.contains("Dwelling units", case=False)]
    g = g.groupby(["MEASURE__code", "MEASURE", "BLD_WORK_TYPE__code", "BLD_WORK_TYPE", "SECTOR_OWN__code", "SECTOR_OWN", "TYPE_BLDG__code", "TYPE_BLDG", "TSEST__code", "TSEST", "PRICE_ADJ__code"]).agg(last=("TIME_PERIOD", "max"), v=("OBS_VALUE", "last")).reset_index()
    g = g[g["SECTOR_OWN"].str.contains("Total") & g["TYPE_BLDG"].str.contains("Total|All", regex=True)]
    with pd.option_context("display.width", 400, "display.max_rows", 100, "display.max_colwidth", 40):
        print(g.to_string(index=False))
u = f"{w.ABS_BASE}/ABS,BA_GCCSA,/1.1.9..100..2.M?startPeriod=2023-01&format=csvfilewithlabels"
rr = requests.get(u, headers=w.UA, timeout=180)
print("\n=== BA_GCCSA Vic", rr.status_code)
if rr.status_code == 200:
    df = w.parse_abs_csv(rr.text).dropna(subset=["OBS_VALUE"])
    print(df.groupby(["WORK_TYPE__code", "WORK_TYPE", "TSEST"]).agg(last=("TIME_PERIOD", "max"), v=("OBS_VALUE", "last")).to_string())
