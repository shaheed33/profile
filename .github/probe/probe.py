"""Temporary probe: population and area measures, remoteness allocation files, sample data."""
import io, re, sys, zipfile
import pandas as pd, requests
sys.path.insert(0, "scripts")
import wa_sources as w
J = {**w.UA, "Accept": "application/vnd.sdmx.structure+json"}
s = requests.get("https://data.api.abs.gov.au/rest/datastructure/ABS/ABS_REGIONAL_LGA2021?references=codelist", headers=J, timeout=120).json()
for cl in s["data"]["codelists"]:
    if cl["id"] == "CL_REGIONAL_MEASURE_2026":
        for c in cl["codes"]:
            if re.search(r"population|area \(|land area|density|ERP", c["name"], re.I) and not re.search(r"Aboriginal|born|aged|Indigenous", c["name"]):
                print(c["id"], "|", c["name"][:110])
# sample: years available for jobs and businesses, two councils
key = "LEED_24+LEED_6+CABEE_5+INCOME_2.LGA2021.24600+20660.A"
r = requests.get(f"{w.ABS_BASE}/ABS,ABS_REGIONAL_LGA2021,/{key}?format=csvfilewithlabels", headers=w.UA, timeout=120)
print("\nsample", r.status_code)
df = w.parse_abs_csv(r.text).dropna(subset=["OBS_VALUE"])
print(df.pivot_table(index=["LGA_2021", "MEASURE"], columns="TIME_PERIOD", values="OBS_VALUE").to_string()[:3000])
# remoteness allocation files (ASGS Edition 3)
B = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
for u in ["https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/allocation-files",
          "https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3/jul2021-jun2026/access-and-downloads/correspondences"]:
    t = requests.get(u, headers=B, timeout=60)
    print("\n", u, t.status_code)
    for l in sorted(set(re.findall(r'href="([^"]+\.(?:zip|xlsx|csv))"', t.text))):
        if re.search(r"MB|LGA|RA_|remote", l, re.I): print("   ", l)
