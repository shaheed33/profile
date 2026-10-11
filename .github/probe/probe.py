"""Temporary probe: what ABS Data by Region (LGA 2021) holds."""
import re, sys
import requests
sys.path.insert(0, "scripts")
import wa_sources as w
J = {**w.UA, "Accept": "application/vnd.sdmx.structure+json"}
s = requests.get("https://data.api.abs.gov.au/rest/datastructure/ABS/ABS_REGIONAL_LGA2021?references=codelist", headers=J, timeout=120).json()
ds = s["data"]["dataStructures"][0]["dataStructureComponents"]["dimensionList"]["dimensions"]
print("dims", [d["id"] for d in sorted(ds, key=lambda d: d.get("position", 0))])
for cl in s["data"].get("codelists", []):
    codes = cl.get("codes", [])
    if len(codes) > 600:
        print("codelist", cl["id"], len(codes), "(regions)"); continue
    print("\ncodelist", cl["id"], len(codes))
    for c in codes:
        if cl["id"].startswith("CL_REGIONAL") or "MEASURE" in cl["id"] or len(codes) < 80:
            if re.search(r"industr|business|job|employ|income|worker|unemploy|GDP|turnover|entr|exit|agri|mining|manufact|touris|ANZSIC", c["name"], re.I) or len(codes) < 30:
                print("  ", c["id"], "|", c["name"][:110])
