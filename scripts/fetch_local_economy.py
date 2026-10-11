"""
Downloads the inputs for local-economy.html and saves them, compressed, in raw/local/:

  regional.csv.gz   ABS Data by Region (ABS_REGIONAL_LGA2021) for every council:
                    jobs by industry, businesses, income, population, land area
  census_ind.csv.gz ABS Census time series T34, industry of employment 2011, 2016
                    and 2021, on 2021 council boundaries
  lga_names.csv     council codes, names and states
  lga_remote.csv    how many residents of each council live in each remoteness
                    area (Census 2021 mesh block counts, ASGS Edition 3)

ABS sites cannot be reached from every network, so this runs in a GitHub Action
(.github/workflows/local-economy.yml). The build itself, scripts/build_local_economy.py,
only reads these files.
"""
from __future__ import annotations

import gzip
import io
import re
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "raw" / "local"
API = "https://data.api.abs.gov.au/rest"
UA = {"User-Agent": "local-economy-explorer/1.0 (personal research project)"}
BROWSER = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/129.0 Safari/537.36"}
ASGS = ("https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/"
        "edition-3-july-2021-june-2026/access-and-downloads/allocation-files/")
MB_COUNTS_PAGE = "https://www.abs.gov.au/census/guide-census-data/mesh-block-counts/latest-release"

# measure codes, grouped so each request stays a sensible size
GROUPS = {
    "jobs": ["LEED_4"] + [f"LEED_{i}" for i in range(5, 25)],
    "business": ["CABEE_5", "CABEE_2", "CABEE_3", "CABEE_4", "CABEE_38",
                 "CABEE_42", "CABEE_43", "CABEE_44", "CABEE_65"] + [f"CABEE_{i}" for i in range(17, 38) if i != 35],
    "people": ["ERP_P_20", "LAND", "INCOME_2", "INCOME_17", "INCOME_19", "LF_4", "LF_6", "AGRIC_15"],
    "census": [f"EMP_IND_{i}" for i in range(2, 23)],
}


def get(url: str, headers: dict, tries: int = 4, timeout: int = 300) -> requests.Response:
    for i in range(tries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            print(f"  {r.status_code} from {url[:140]}")
        except requests.RequestException as e:
            print(f"  {type(e).__name__} from {url[:140]}")
        time.sleep(5 * 2 ** i)
    raise SystemExit(f"Could not download {url}")


def save_gz(name: str, text: str) -> None:
    with gzip.open(OUT / name, "wt", encoding="utf-8", compresslevel=9) as fh:
        fh.write(text)
    print(f"  saved {name} ({(OUT / name).stat().st_size / 1e6:.1f} MB)")


def fetch_regional() -> None:
    parts = []
    for name, codes in GROUPS.items():
        url = f"{API}/data/ABS,ABS_REGIONAL_LGA2021,/{'+'.join(codes)}.LGA2021..A?startPeriod=2011&format=csvfile"
        r = get(url, UA)
        df = pd.read_csv(io.StringIO(r.text), dtype=str)
        print(f"{name}: {len(df):,} rows, {df['MEASURE'].nunique()} measures, "
              f"{df['LGA_2021'].nunique()} councils, years {df['TIME_PERIOD'].min()} to {df['TIME_PERIOD'].max()}")
        missing = sorted(set(codes) - set(df["MEASURE"]))
        if missing:
            print("  measures with no data:", missing)
        parts.append(df[["MEASURE", "LGA_2021", "TIME_PERIOD", "OBS_VALUE"]])
    save_gz("regional.csv.gz", pd.concat(parts).to_csv(index=False))


def fetch_names() -> None:
    J = {**UA, "Accept": "application/vnd.sdmx.structure+json"}
    s = get(f"{API}/datastructure/ABS/ABS_REGIONAL_LGA2021?references=codelist", J).json()
    rows = []
    for cl in s["data"]["codelists"]:
        if re.search(r"LGA", cl["id"]) and len(cl.get("codes", [])) > 400:
            print("council code list", cl["id"], len(cl["codes"]))
            rows = [{"code": c["id"], "name": c["name"]} for c in cl["codes"]]
            break
    if not rows:
        raise SystemExit("No council code list found")
    pd.DataFrame(rows).to_csv(OUT / "lga_names.csv", index=False)


def fetch_census_industry() -> None:
    url = f"{API}/data/ABS,C21_T34_LGA,/all?format=csvfile"
    r = get(url, UA)
    df = pd.read_csv(io.StringIO(r.text), dtype=str)
    print("census T34:", len(df), "rows; columns", list(df.columns))
    for c in df.columns:
        if c not in ("OBS_VALUE", "LGA_2021", "REGION") and df[c].nunique() < 40:
            print(f"  {c}: {sorted(df[c].unique())[:30]}")
    save_gz("census_ind.csv.gz", r.text)


def read_xlsx(url: str) -> pd.DataFrame:
    r = get(url, BROWSER)
    data = r.content
    if data[:2] == b"PK" and url.endswith(".zip"):
        z = zipfile.ZipFile(io.BytesIO(data))
        name = [n for n in z.namelist() if n.lower().endswith((".xlsx", ".csv"))][0]
        data = z.read(name)
        url = name
    if url.lower().endswith(".csv"):
        return pd.read_csv(io.BytesIO(data), dtype=str)
    return pd.read_excel(io.BytesIO(data), dtype=str)


def col(df: pd.DataFrame, pat: str) -> str:
    for c in df.columns:
        if re.fullmatch(pat, str(c), re.I):
            return c
    raise SystemExit(f"No column like {pat} in {list(df.columns)}")


def fetch_remoteness() -> None:
    lga = read_xlsx(ASGS + "LGA_2021_AUST.xlsx")
    print("LGA allocation columns", list(lga.columns))
    ra = read_xlsx(ASGS + "RA_2021_AUST.xlsx")
    print("RA allocation columns", list(ra.columns))
    mb = read_xlsx(ASGS + "MB_2021_AUST.xlsx")
    print("MB allocation columns", list(mb.columns))
    # Census 2021 mesh block counts (people per mesh block)
    page = get(MB_COUNTS_PAGE, BROWSER).text
    links = sorted(set(re.findall(r'href="([^"]+\.(?:xlsx|zip|csv))"', page)))
    print("mesh block count files", links)
    counts = []
    for l in links:
        if not re.search(r"mesh|MB", l, re.I):
            continue
        url = l if l.startswith("http") else "https://www.abs.gov.au" + l
        r = get(url, BROWSER)
        data = r.content
        frames = []
        if url.endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(data))
            for n in z.namelist():
                if n.lower().endswith(".csv"):
                    frames.append(pd.read_csv(z.open(n), dtype=str))
                elif n.lower().endswith(".xlsx"):
                    frames += list(pd.read_excel(z.open(n), sheet_name=None, dtype=str, header=None).values())
        elif url.endswith(".csv"):
            frames.append(pd.read_csv(io.BytesIO(data), dtype=str))
        else:
            frames += list(pd.read_excel(io.BytesIO(data), sheet_name=None, dtype=str, header=None).values())
        for f in frames:
            # sheets carry a few title rows above the header row
            if "MB_CODE_2021" not in [str(c) for c in f.columns]:
                hdr = f.index[f.apply(lambda r: r.astype(str).str.fullmatch("MB_CODE_2021").any(), axis=1)]
                if not len(hdr):
                    continue
                f.columns = [str(c) for c in f.loc[hdr[0]]]
                f = f.loc[hdr[0] + 1:]
            f = f.loc[:, ~pd.Index(f.columns).duplicated()]
            pc = [c for c in f.columns if re.fullmatch(r"Person.*", str(c), re.I)]
            if pc:
                counts.append(pd.DataFrame({"MB_CODE_2021": f["MB_CODE_2021"].astype(str).values,
                                            "persons": f[pc[0]].values}))
    if not counts:
        raise SystemExit("No mesh block counts found")
    cnt = pd.concat(counts, ignore_index=True)
    print(f"mesh block counts: {len(cnt):,} mesh blocks")
    cnt["persons"] = pd.to_numeric(cnt["persons"], errors="coerce").fillna(0)
    a = lga[[col(lga, "MB_CODE_2021"), col(lga, "LGA_CODE_2021")]]
    a.columns = ["MB_CODE_2021", "LGA_CODE_2021"]
    # the RA file may be by mesh block or by SA1; join on whichever it has
    if "MB_CODE_2021" in [c.upper() for c in ra.columns]:
        b = ra[[col(ra, "MB_CODE_2021"), col(ra, "RA_NAME_2021")]]
        b.columns = ["MB_CODE_2021", "RA"]
    else:
        key = col(ra, "SA1_CODE_2021")
        b = ra[[key, col(ra, "RA_NAME_2021")]]
        b.columns = ["SA1_CODE_2021", "RA"]
        m = mb[[col(mb, "MB_CODE_2021"), col(mb, "SA1_CODE_2021")]]
        m.columns = ["MB_CODE_2021", "SA1_CODE_2021"]
        b = m.merge(b, on="SA1_CODE_2021")[["MB_CODE_2021", "RA"]]
    g = mb[[col(mb, "MB_CODE_2021"), col(mb, "GCCSA_NAME_2021")]]
    g.columns = ["MB_CODE_2021", "GCCSA"]
    j = a.merge(b, on="MB_CODE_2021").merge(g, on="MB_CODE_2021").merge(cnt, on="MB_CODE_2021", how="left")
    j["persons"] = j["persons"].fillna(0)
    print(f"joined {len(j):,} mesh blocks, {j['persons'].sum():,.0f} people")
    out = j.groupby(["LGA_CODE_2021", "RA", "GCCSA"], as_index=False)["persons"].sum()
    out.to_csv(OUT / "lga_remote.csv", index=False)
    print(f"  saved lga_remote.csv ({len(out)} rows)")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    steps = [fetch_names, fetch_regional, fetch_census_industry, fetch_remoteness]
    failed = []
    for f in steps:
        print(f"\n== {f.__name__}")
        try:
            f()
        except SystemExit as e:
            print("FAILED", e)
            failed.append(f.__name__)
    if failed:
        sys.exit(f"Failed: {failed}")


if __name__ == "__main__":
    main()
