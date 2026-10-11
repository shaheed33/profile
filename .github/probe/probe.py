"""Temporary probe: extract Victorian council targets, boundaries and approvals coverage."""
import html, json, re, sys
import pandas as pd, requests
sys.path.insert(0, "scripts")
import wa_sources as w
B = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
url = "https://engage.vic.gov.au/project/developing-a-new-plan-for-Victoria/page/housing-targets-2051"
t = requests.get(url, headers=B, timeout=60).text
u = html.unescape(t).replace("\\/", "/").replace('\\"', '"')
rows = []
for m in re.finditer(r'<summary class="details__summary">(.*?)</summary>\s*<div class="details__content">(.*?)</div>', u, re.S):
    name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
    body = re.sub(r"<[^>]+>", " | ", m.group(2))
    body = re.sub(r"\s+", " ", body).strip(" |")
    rows.append((name, body))
print("details entries:", len(rows))
for r in rows:
    print(r[0], "::", r[1])
# also the 2025 hotspot entries (final map)
hs = re.findall(r'"title":"([^"]+)"[^{}]*?"description":"(.*?)"\}', u)
print("\nhotspots:", len(hs))
for name, d in hs:
    d2 = re.sub(r"<[^>]+>", " | ", d); d2 = re.sub(r"\s+", " ", d2).strip(" |")
    if "2051" in d2 and "draft" not in d2.lower() and "proposed" not in d2.lower():
        print("HS", name, "::", d2)
# headings around the details lists (metro vs regional)
for m in re.finditer(r"<h[23][^>]*>(.*?)</h[23]>", u):
    print("H:", re.sub(r"<[^>]+>", "", m.group(1))[:120])

# boundaries
for svc in ["ASGS2025/LGA", "ASGS2024/LGA", "ASGS2021/LGA"]:
    q = (f"https://geo.abs.gov.au/arcgis/rest/services/{svc}/MapServer/0/query?where=state_code_2021%3D%272%27"
         f"&outFields=*&returnGeometry=true&outSR=4326&maxAllowableOffset=0.01&geometryPrecision=3&f=geojson")
    r = requests.get(q, headers=B, timeout=120)
    print("\n=== boundaries", svc, r.status_code, len(r.text), r.text[:300])
    if r.status_code == 200 and '"features"' in r.text:
        g = r.json(); print("features", len(g["features"]), "props", list(g["features"][0]["properties"].items())[:12]); break
r = requests.get("https://geo.abs.gov.au/arcgis/rest/services?f=json", headers=B, timeout=60)
print("services root", r.status_code, r.text[:800])

# approvals coverage for Victoria by LGA flow
for flow, rt in [("BA_LGA2024", "LGA2024"), ("BA_LGA2025", "LGA2025")]:
    q = f"{w.ABS_BASE}/ABS,{flow},/1.9.TOT.100.{rt}..M?startPeriod=2023-01&format=csvfilewithlabels"
    r = requests.get(q, headers=w.UA, timeout=180)
    print("\n===", flow, r.status_code, f"{len(r.text)/1e6:.2f}MB")
    if r.status_code == 200:
        df = w.parse_abs_csv(r.text).dropna(subset=["OBS_VALUE"])
        vic = df[df["REGION__code"].str.match(r"^2\d{4}$")]
        print("months", vic["TIME_PERIOD"].min(), vic["TIME_PERIOD"].max(), "LGAs", vic["REGION"].nunique())
        last12 = vic[vic["TIME_PERIOD"] > sorted(vic["TIME_PERIOD"].unique())[-13]]
        print(last12.groupby("REGION")["OBS_VALUE"].sum().sort_values(ascending=False).head(10).to_string())
        print("Vic total last 12m", last12["OBS_VALUE"].sum())
        print("non-standard regions", vic[~vic["REGION__code"].str.match(r"^2[0-8]\d{3}$")][["REGION__code", "REGION"]].drop_duplicates().values.tolist())
        print(sorted(vic[["REGION__code", "REGION"]].drop_duplicates().itertuples(index=False))[:90])
q = f"{w.ABS_BASE}/ABS,BA_GCCSA,/1.1.9.TOT.100.10..M?startPeriod=2025-01&format=csvfilewithlabels"
r = requests.get(q, headers=w.UA, timeout=180)
df = w.parse_abs_csv(r.text).dropna(subset=["OBS_VALUE"])
print("\nGCCSA regions", df[["REGION__code", "REGION"]].drop_duplicates().values.tolist())
