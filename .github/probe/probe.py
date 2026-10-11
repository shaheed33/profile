"""Temporary probe: ABS dataflows for jobs by industry and businesses by council."""
import re, sys, json
import requests
sys.path.insert(0, "scripts")
import wa_sources as w
J = {**w.UA, "Accept": "application/vnd.sdmx.structure+json"}
flows = requests.get("https://data.api.abs.gov.au/rest/dataflow/ABS", headers=J, timeout=90).json()["data"]["dataflows"]
print("total dataflows", len(flows))
pat = r"industr|CABEE|business|counts of australian|REGIONAL|working population|place of work|W\d\d|INDP|employ"
hits = [f for f in flows if re.search(pat, f["id"] + " " + f["name"], re.I)]
for f in hits:
    print(f["id"], "|", f["name"])
print("\n--- census flows sample")
for f in flows:
    if re.match(r"(ABS_)?C(16|21)_", f["id"]) or "census" in f["name"].lower():
        print(f["id"], "|", f["name"])
