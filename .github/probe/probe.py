"""Temporary probe: the jobs, business and income measures in ABS Data by Region."""
import re, sys
import requests
sys.path.insert(0, "scripts")
import wa_sources as w
J = {**w.UA, "Accept": "application/vnd.sdmx.structure+json"}
s = requests.get("https://data.api.abs.gov.au/rest/datastructure/ABS/ABS_REGIONAL_LGA2021?references=codelist", headers=J, timeout=120).json()
for cl in s["data"]["codelists"]:
    if cl["id"] == "CL_REGIONAL_MEASURE_2026":
        for c in cl["codes"]:
            if re.search(r"industr|business|job|employ|income|worker|unemploy|turnover|entr|exit|ANZSIC|agricultur|mining|manufactur|touris|electric|wage|salar", c["name"], re.I):
                print(c["id"], "|", c["name"][:120])
