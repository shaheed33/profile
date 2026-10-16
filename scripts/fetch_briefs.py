"""Download the extra public data used by the council briefings (Rockingham, Wellington, Glen Innes Severn)
and their comparison areas. Runs on GitHub Actions through .github/workflows/briefs-data.yml.

Saves into raw/briefs/:
  regional_all.csv.gz      every ABS Data by Region measure for the selected councils, 2010 onwards
  regional_measures.csv    names of those measures
  census/<pack>/<table>.csv  Census 2021 (and 2016) DataPack tables, filtered to the selected areas
  tra_lga_list.xlsx        list of Tourism Research Australia LGA profiles
  fetch.log                what worked and what did not
"""
import gzip, io, json, sys, time, zipfile
from pathlib import Path
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "raw" / "briefs"
OUT.mkdir(parents=True, exist_ok=True)
API = "https://data.api.abs.gov.au/rest"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"}

LGAS = {
    # Rockingham and outer Perth growth councils
    "57490": "Rockingham", "54830": "Kwinana", "51820": "Cockburn", "55110": "Mandurah", "50210": "Armadale",
    "58760": "Wanneroo", "58050": "Swan", "57700": "Serpentine-Jarrahdale", "53780": "Gosnells",
    # Wellington and Gippsland
    "26810": "Wellington", "23810": "Latrobe", "22110": "East Gippsland", "20830": "Baw Baw",
    "26170": "South Gippsland", "20740": "Bass Coast",
    # Glen Innes Severn and New England
    "13010": "Glen Innes Severn", "14220": "Inverell", "17400": "Tenterfield", "10180": "Armidale Regional",
    "17650": "Uralla", "17850": "Walcha", "13660": "Gwydir", "15750": "Narrabri", "15300": "Moree Plains",
}

log = []
def say(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); log.append(s)

def get(url, tries=4, timeout=600, headers=None):
    for i in range(tries):
        try:
            r = requests.get(url, headers=headers or UA, timeout=timeout)
            if r.status_code == 200:
                return r
            say(f"  {r.status_code} from {url[:160]}")
            if r.status_code in (404, 410):
                return None
        except requests.RequestException as e:
            say(f"  {type(e).__name__} from {url[:160]}")
        time.sleep(5 * 2 ** i)
    return None

def regional():
    codes = "+".join(LGAS)
    url = f"{API}/data/ABS,ABS_REGIONAL_LGA2021,/.LGA2021.{codes}.A?startPeriod=2010&format=csvfile"
    r = get(url, headers={**UA, "Accept": "text/csv"})
    if r is None:
        say("regional: FAILED"); return
    df = pd.read_csv(io.StringIO(r.text), dtype=str)
    say(f"regional: {len(df):,} rows, {df['MEASURE'].nunique()} measures, cols {list(df.columns)}")
    keep = [c for c in ["MEASURE", "LGA_2021", "TIME_PERIOD", "OBS_VALUE"] if c in df.columns]
    with gzip.open(OUT / "regional_all.csv.gz", "wt", encoding="utf-8") as fh:
        df[keep].to_csv(fh, index=False)
    s = get(f"{API}/datastructure/ABS/ABS_REGIONAL_LGA2021?references=codelist",
            headers={**UA, "Accept": "application/vnd.sdmx.structure+json"})
    if s is not None:
        rows = []
        for cl in s.json()["data"]["codelists"]:
            if "MEASURE" in cl["id"].upper():
                rows += [{"code": c["id"], "name": c["name"]} for c in cl["codes"]]
        pd.DataFrame(rows).to_csv(OUT / "regional_measures.csv", index=False)
        say(f"regional measures: {len(rows)} names")

def census_pack(name, geo_codes, code_col_hint):
    base = "https://www.abs.gov.au/census/find-census-data/datapacks/download/"
    r = get(base + name + ".zip", timeout=900)
    if r is None:
        say(f"census {name}: FAILED"); return
    z = zipfile.ZipFile(io.BytesIO(r.content))
    dest = OUT / "census" / name
    dest.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in z.namelist():
        low = f.lower()
        if low.endswith((".xlsx", ".xls")) and "metadata" in low:
            (dest / Path(f).name).write_bytes(z.read(f)); continue
        if not low.endswith(".csv"):
            continue
        df = pd.read_csv(z.open(f), dtype=str)
        col = next((c for c in df.columns if code_col_hint in c.upper()), df.columns[0])
        keys = df[col].astype(str).str.replace(r"^[A-Z]+", "", regex=True)
        sub = df[keys.isin(geo_codes)] if geo_codes else df
        if len(sub):
            sub.to_csv(dest / Path(f).name, index=False); n += 1
    say(f"census {name}: {n} tables saved")

def tra():
    r = get("https://www.tra.gov.au/content/dam/austrade-assets/global/wip/tra/documents/Local%20Government%20Area%20profiles.xlsx")
    if r is not None:
        (OUT / "tra_lga_list.xlsx").write_bytes(r.content); say("tra list saved")
    else:
        say("tra list: FAILED")

if __name__ == "__main__":
    for step in [regional,
                 lambda: census_pack("2021_WPP_LGA_for_AUS_short-header", set(LGAS), "LGA"),
                 lambda: census_pack("2021_GCP_LGA_for_AUS_short-header", set(LGAS), "LGA"),
                 lambda: census_pack("2021_WPP_STE_for_AUS_short-header", None, "STE"),
                 lambda: census_pack("2021_GCP_STE_for_AUS_short-header", None, "STE"),
                 lambda: census_pack("2016_WPP_LGA_for_AUS_short-header", None, "LGA"),
                 tra]:
        try:
            step()
        except Exception as e:
            say(f"step failed: {type(e).__name__}: {e}")
    (OUT / "fetch.log").write_text("\n".join(log) + "\n")
