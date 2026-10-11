"""Temporary probe: download the council performance spreadsheets."""
import pathlib, requests
B = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}
out = pathlib.Path("raw/councils"); out.mkdir(parents=True, exist_ok=True)
files = {
    "vic_lgprf_2020_2025.xlsx": "https://www.localgovernment.vic.gov.au/__data/assets/excel_doc/0019/191008/LGPRF-2020-2025-Full-Council-Data-Set-Nov25-Final-Release.xlsx",
    "nsw_2024_25.xlsx": "https://www.olg.nsw.gov.au/sites/default/files/2026-05/time-series-data-2024-2025.xlsx",
    "nsw_2023_24.xlsx": "https://www.olg.nsw.gov.au/sites/default/files/2026-02/time-series-data-2023-24.xlsx",
    "nsw_2022_23.xlsx": "https://www.olg.nsw.gov.au/sites/default/files/2026-02/time-series-data-2022-23.xlsx",
}
for name, url in files.items():
    r = requests.get(url, headers=B, timeout=120)
    print(name, r.status_code, len(r.content), r.headers.get("content-type"))
    if r.status_code == 200 and len(r.content) > 10000:
        (out / name).write_bytes(r.content)
