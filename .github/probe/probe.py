"""Temporary probe: Victorian housing targets table and ABS Victorian housing series."""
import io, re, sys, json
import pandas as pd, requests
from bs4 import BeautifulSoup
sys.path.insert(0, "scripts")
import wa_sources as w
B = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
url = "https://engage.vic.gov.au/project/developing-a-new-plan-for-Victoria/page/housing-targets-2051"
r = requests.get(url, headers=B, timeout=60)
soup = BeautifulSoup(r.text, "lxml")
for s in soup(["script", "style", "noscript"]):
    s.decompose()
tables = soup.find_all("table")
print("tables:", len(tables))
for i, t in enumerate(tables):
    rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])] for tr in t.find_all("tr")]
    print(f"--- table {i} ({len(rows)} rows)")
    for rw in rows:
        print(" | ".join(rw))
main = soup.get_text("\n", strip=True)
i = main.find("2051")
print("\n=== page text (first 6000 chars from first mention of targets)")
k = max(0, main.lower().find("housing target"))
print(main[k:k + 6000])
links = [a.get("href") for a in soup.find_all("a") if a.get("href") and re.search(r"\.(xlsx|csv|pdf|xls)", a.get("href"), re.I)]
print("file links:", links[:40])

# ABS: which LGA approvals flows cover recent months, for Victoria
for flow in ["BA_LGA2024", "BA_LGA2025", "BA_LGA2026"]:
    u = f"{w.ABS_BASE}/ABS,{flow},/1.9.TOT.100.LGA..M?startPeriod=2023-01&format=csvfilewithlabels"
    rr = requests.get(u, headers=w.UA, timeout=180)
    print(f"\n=== {flow} HTTP {rr.status_code} {len(rr.text)/1e6:.2f}MB")
    if rr.status_code != 200:
        print(rr.text[:300]); continue
    df = w.parse_abs_csv(rr.text).dropna(subset=["OBS_VALUE"])
    vic = df[df["REGION__code"].str.startswith("2")]
    print("dims", [c for c in df.columns if not c.endswith("__code")])
    print("labels", {c: df[c].unique()[:4].tolist() for c in ["MEASURE", "SECTOR", "WORK_TYPE", "BUILDING_TYPE", "REGION_TYPE"]})
    print("periods", df["TIME_PERIOD"].min(), df["TIME_PERIOD"].max(), "Vic LGAs", vic["REGION"].nunique())
    print(vic.groupby(["REGION__code", "REGION"]).size().head(12).to_string())

# ABS: Victoria commencements and completions, quarterly
u = f"{w.ABS_BASE}/ABS,BUILDING_ACTIVITY,/.2.....Q?startPeriod=2015-01&format=csvfilewithlabels"
rr = requests.get(u, headers=w.UA, timeout=240)
print("\n=== BUILDING_ACTIVITY Vic", rr.status_code, f"{len(rr.text)/1e6:.1f}MB")
df = w.parse_abs_csv(rr.text).dropna(subset=["OBS_VALUE"])
g = df[df["MEASURE"].str.contains("Dwelling units", case=False)]
g = g.groupby(["MEASURE__code", "MEASURE", "BLD_WORK_TYPE", "SECTOR_OWN", "TYPE_BLDG__code", "TYPE_BLDG", "TSEST", "PRICE_ADJ"]).agg(last=("TIME_PERIOD", "max"), n=("TIME_PERIOD", "size")).reset_index()
g = g[g["SECTOR_OWN"].str.contains("Total") & g["BLD_WORK_TYPE"].str.contains("Total|New", regex=True)]
with pd.option_context("display.width", 400, "display.max_rows", 100, "display.max_colwidth", 40):
    print(g.to_string(index=False))
# Victoria monthly approvals, state total, seasonally adjusted, all work types
u = f"{w.ABS_BASE}/ABS,BA_GCCSA,/1.1.9..100..2.M?startPeriod=2023-01&format=csvfilewithlabels"
rr = requests.get(u, headers=w.UA, timeout=180)
df = w.parse_abs_csv(rr.text).dropna(subset=["OBS_VALUE"])
print("\n=== BA_GCCSA Vic", rr.status_code)
print(df.groupby(["WORK_TYPE__code", "WORK_TYPE", "TSEST"]).agg(last=("TIME_PERIOD", "max"), v=("OBS_VALUE", "last")).to_string())
