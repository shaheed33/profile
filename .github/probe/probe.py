"""Temporary probe: Victorian housing targets and ABS council-level approvals."""
import io, re, sys
import pandas as pd, requests
sys.path.insert(0, "scripts")
import wa_sources as w
B = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
for url in ["https://www.planning.vic.gov.au/planforvictoria/housing-for-all-victorians/housing-targets",
            "https://engage.vic.gov.au/project/developing-a-new-plan-for-Victoria/page/housing-targets-2051"]:
    try:
        r = requests.get(url, headers=B, timeout=60)
        print("\n=== ", url, r.status_code, len(r.text))
        try:
            for i, t in enumerate(pd.read_html(io.StringIO(r.text))):
                print(f"--- table {i} shape {t.shape}")
                with pd.option_context("display.width", 300, "display.max_rows", 200, "display.max_colwidth", 60):
                    print(t.to_string(index=False))
        except Exception as e:
            print("no tables:", e)
        txt = re.sub(r"<[^>]+>", " ", r.text); txt = re.sub(r"\s+", " ", txt)
        for kw in ["2051", "baseline", "net new", "greenfield", "established", "2.24"]:
            for m in list(re.finditer(kw, txt))[:4]:
                print(f"[{kw}]", txt[max(0, m.start() - 200): m.end() + 200])
        links = re.findall(r'href="([^"]+\.(?:xlsx|csv|pdf|xls))"', r.text)
        print("file links:", links[:30])
    except Exception as e:
        print(url, "failed", e)
J = {**w.UA, "Accept": "application/vnd.sdmx.structure+json"}
j = requests.get("https://data.api.abs.gov.au/rest/dataflow/ABS", headers=J, timeout=60).json()
for f in j["data"]["dataflows"]:
    if re.search(r"^BA|building", f["id"] + " " + f["name"], re.I):
        print(f["id"], "|", f["name"])
        try:
            s = requests.get(f"https://data.api.abs.gov.au/rest/datastructure/ABS/{f['id']}", headers=J, timeout=60).json()
            print("   dims", [d["id"] for d in sorted(s["data"]["dataStructures"][0]["dataStructureComponents"]["dimensionList"]["dimensions"], key=lambda d: d.get("position", 0))])
        except Exception as e:
            print("   structure failed", e)
