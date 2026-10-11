"""Temporary probe: non-Census business/regional flows, and the detail of Census industry tables."""
import re, sys
import pandas as pd, requests
sys.path.insert(0, "scripts")
import wa_sources as w
J = {**w.UA, "Accept": "application/vnd.sdmx.structure+json"}
flows = requests.get("https://data.api.abs.gov.au/rest/dataflow/ABS", headers=J, timeout=90).json()["data"]["dataflows"]
for f in flows:
    if re.match(r"(ABS_)?C(16|21)_", f["id"]):
        continue
    if re.search(r"industr|CABEE|business|REGIONAL|region|working population|place of work|employ|jobs|ANZSIC", f["id"] + " " + f["name"], re.I):
        print(f["id"], "|", f["name"])
for fid in ["C21_T34_LGA", "C21_G54_LGA"]:
    s = requests.get(f"https://data.api.abs.gov.au/rest/datastructure/ABS/{fid}?references=codelist", headers=J, timeout=90).json()
    ds = s["data"]["dataStructures"][0]["dataStructureComponents"]["dimensionList"]["dimensions"]
    print("\n===", fid, "dims", [d["id"] for d in sorted(ds, key=lambda d: d.get("position", 0))])
    for cl in s["data"].get("codelists", []):
        codes = cl.get("codes", [])
        print("  codelist", cl["id"], len(codes), [c["id"] + ":" + c["name"][:30] for c in codes[:30]])
