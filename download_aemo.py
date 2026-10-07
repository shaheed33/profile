"""
download_aemo.py
Downloads AEMO's NEM Generation Information workbooks into the raw folder,
named so build_roadmap.py can read the date from each file name.

Usage (from the site folder):
  python scripts/download_aemo.py           downloads the fixed list below
  python scripts/download_aemo.py --latest  checks AEMO's page and downloads the newest release if it is new
                                            (prints NEW or NO CHANGE, used by the GitHub workflow)
"""
import os, re, sys, time, urllib.request

BASE = "https://www.aemo.com.au/-/media/files/electricity/nem/planning_and_forecasting/generation_information/"

# One release roughly every six months since the Roadmap began, plus the latest
FILES = {
    "Jan 2021": "2021/nem-generation-information-january-2021.xlsx",
    "Jul 2021": "2021/nem-generation-information-july-2021.xlsx",
    "Jan 2022": "2022/nem-generation-information-january-2022.xlsx",
    "Jul 2022": "2022/nem-generation-information-july-2022.xlsx",
    "Jan 2023": "2023/nem-generation-information-jan-2023.xlsx",
    "Jul 2023": "2023/nem-generation-information-july-2023.xlsx",
    "Jan 2024": "2024/nem-generation-information-jan-2024.xlsx",
    "Jul 2024": "2024/nem-generation-information-july-2024.xlsx",
    "Jan 2025": "2025/nem-generation-information-january-2025.xlsx",
    "Jul 2025": "2025/nem-generation-information-july-2025.xlsx",
    "Jan 2026": "2026/nem-generation-information-jan-2026.xlsx",
    "Jul 2026": "2026/nem-generation-information-july-2026.xlsx",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36",
    "Accept": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,*/*",
}

PAGE = "https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/nem-forecasting-and-planning/forecasting-and-planning-data/generation-information"
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def latest():
    html = fetch(PAGE).decode("utf-8", "ignore")
    links = set(re.findall(r'(/-/media/files/electricity/nem/planning_and_forecasting/generation_information/20\d\d/nem-generation-information-[^"?<> ]+\.xlsx)', html))
    found = []
    for link in links:
        m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*-(20\d\d)\.xlsx$", link)
        if m: found.append((int(m.group(2)), MONTHS.index(m.group(1)) + 1, link))
    if not found:
        raise SystemExit("No Generation Information files found on AEMO's page. The page layout may have changed.")
    year, month, link = max(found)
    label = f"{MONTHS[month - 1].title()} {year}"
    out = os.path.join("raw", f"NEM Generation Information {label}.xlsx")
    have = {re.sub(r"[_ ]", "", f.lower()) for f in os.listdir("raw")} if os.path.isdir("raw") else set()
    if re.sub(r"[_ ]", "", os.path.basename(out).lower()) in have:
        print(f"NO CHANGE  newest release is still {label}")
        return
    os.makedirs("raw", exist_ok=True)
    data = fetch("https://www.aemo.com.au" + link)
    if not data.startswith(b"PK"):
        raise SystemExit("AEMO returned something that is not an Excel file.")
    with open(out, "wb") as fh:
        fh.write(data)
    print(f"NEW  saved {label}")

def main():
    if "--latest" in sys.argv:
        return latest()
    os.makedirs("raw", exist_ok=True)
    failed = []
    for label, path in FILES.items():
        out = os.path.join("raw", f"NEM Generation Information {label}.xlsx")
        if os.path.exists(out) and os.path.getsize(out) > 50_000:
            print(f"Already have {label}")
            continue
        try:
            req = urllib.request.Request(BASE + path, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if not data.startswith(b"PK"):          # every .xlsx file starts with PK
                raise ValueError("did not get an Excel file back")
            with open(out, "wb") as fh:
                fh.write(data)
            print(f"Saved {label}  ({len(data) // 1024} KB)")
        except Exception as e:
            print(f"Could not download {label}: {e}")
            failed.append((label, BASE + path))
        time.sleep(1)                               # be polite to AEMO's server
    if failed:
        print("\nDownload these by hand in your browser and save them in raw with the name shown:")
        for label, url in failed:
            print(f"  NEM Generation Information {label}.xlsx  <-  {url}")
    else:
        print("\nAll done. Next run  python scripts/build_roadmap.py --inspect")

if __name__ == "__main__":
    main()
