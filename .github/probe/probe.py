"""Temporary probe: where the Victorian and NSW council performance data can be downloaded."""
import json, re
import requests
B = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}

def ckan(base, q, rows=12):
    try:
        r = requests.get(f"{base}/api/3/action/package_search", params={"q": q, "rows": rows}, headers=B, timeout=60)
        print(f"\n### {base} q={q!r} HTTP {r.status_code}")
        res = r.json()["result"]["results"]
        for p in res:
            print(f"- {p['name']} | {p['title']} | modified {p.get('metadata_modified', '')[:10]} | org {(p.get('organization') or {}).get('title')}")
            for x in p.get("resources", [])[:25]:
                print(f"    [{x.get('format')}] {x.get('name')} -> {x.get('url')}")
    except Exception as e:
        print(base, q, "failed", e)

for q in ["local government performance reporting", "LGPRF", "know your council"]:
    ckan("https://discover.data.vic.gov.au", q)
for q in ["local government time series", "your council", "office of local government council data"]:
    ckan("https://data.nsw.gov.au/data", q)

for url in ["https://www.yourcouncil.nsw.gov.au/", "https://www.olg.nsw.gov.au/public/about-councils/comparative-council-information/",
            "https://www.olg.nsw.gov.au/public/about-councils/comparative-council-information/your-council-report/",
            "https://www.localgovernment.vic.gov.au/council-performance-reporting",
            "https://www.knowyourcouncil.vic.gov.au/"]:
    try:
        r = requests.get(url, headers=B, timeout=60)
        links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|xls|csv|zip)[^"]*)"', r.text, re.I)))
        print(f"\n### {url} HTTP {r.status_code} {len(r.text)} chars, file links {len(links)}")
        for l in links[:40]:
            print("   ", l)
        if not links:
            more = sorted(set(re.findall(r'href="([^"]*(?:data|download|time-series|report)[^"]*)"', r.text, re.I)))
            print("    other:", more[:30])
    except Exception as e:
        print(url, "failed", e)
