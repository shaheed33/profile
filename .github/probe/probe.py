"""Temporary probe: get the Victorian performance reporting spreadsheet."""
import pathlib, re, requests
out = pathlib.Path("raw/councils"); out.mkdir(parents=True, exist_ok=True)
U = "https://www.localgovernment.vic.gov.au/__data/assets/excel_doc/0019/191008/LGPRF-2020-2025-Full-Council-Data-Set-Nov25-Final-Release.xlsx"
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*;q=0.8",
     "Accept-Language": "en-AU,en;q=0.9", "Referer": "https://discover.data.vic.gov.au/"}
def save(name, r):
    ok = r.status_code == 200 and r.content[:2] == b"PK"
    print(name, r.status_code, len(r.content), r.headers.get("content-type"), "OK" if ok else "")
    if ok: (out / name).write_bytes(r.content)
    return ok
s = requests.Session()
got = save("vic_lgprf_2020_2025.xlsx", s.get(U, headers=H, timeout=120))
if not got:
    for w in [f"https://web.archive.org/web/2026id_/{U}", f"https://web.archive.org/web/2025id_/{U}"]:
        if save("vic_lgprf_2020_2025.xlsx", requests.get(w, headers=H, timeout=180)):
            got = True; break
r = requests.get("https://www.knowyourcouncil.vic.gov.au/data", headers=H, timeout=60)
print("KYC data page", r.status_code)
for l in sorted(set(re.findall(r'href="([^"]+)"', r.text))):
    if re.search(r"xlsx|csv|data|download|lgprf", l, re.I): print("   ", l)
r = requests.get("https://discover.data.vic.gov.au/api/3/action/package_show?id=local-government-performance-reporting", headers=H, timeout=60)
for x in r.json()["result"]["resources"]:
    print("resource", x.get("format"), x.get("name"), x.get("url"), x.get("datastore_active"))
