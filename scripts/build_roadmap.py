"""
build_roadmap.py
Builds data/roadmap.js for roadmap.html from AEMO's NEM Generation Information workbooks.

1. Download one or more "NEM Generation Information" .xlsx files from
   https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/nem-forecasting-and-planning/forecasting-and-planning-data/generation-information
   and put them in the raw/ folder. The newest file drives the headline figures.
   Older files (one per quarter is plenty) build the history chart.
2. pip install pandas openpyxl
3. python scripts/build_roadmap.py --inspect   (checks the columns are found)
   python scripts/build_roadmap.py             (writes data/roadmap.js)
"""
import sys, re, json, glob, os, datetime as dt
import pandas as pd

RAW = "raw"
OUT = "data/roadmap.js"
ROADMAP_START = pd.Timestamp("2021-01-01")   # Electricity Infrastructure Investment Act passed Dec 2020
SHEET_HINT = "ExistingGeneration"

TARGETS = {
    "generation_min_gw": 12, "generation_ambition_gw": 16,   # by 2030
    "storage_min_gw": 2,                                     # long-duration storage by 2030
    "storage_min_gwh_2034": 28, "storage_ambition_gwh_2034": 42,
}

# Column finders: first header containing any of these words (lower case) wins
COLS = {
    "region":   ["region"],
    "name":     ["site name", "station name", "project name", "unit name"],
    "fuel":     ["fuel type", "fuel bucket", "fuel"],
    "tech":     ["technology type", "technology"],
    "status":   ["commitment status", "status"],
    "mw":       ["nameplate capacity", "upper nameplate", "capacity (mw)", "capacity"],
    "mwh":      ["storage capacity (mwh)", "mwh"],
    "fcu":      ["full commercial use date", "commercial use", "commissioning date"],
    "closure":  ["expected closure", "closure year", "closure date"],
}

STATUS_MAP = [  # order matters
    ("withdrawn", None), ("announced withdrawal", "Closing"),
    ("in service", "Operating"), ("in commissioning", "Operating"),
    ("committed", "Committed"), ("anticipated", "Anticipated"), ("maturing", "Anticipated"),
    ("publicly announced", "Proposed"), ("emerging", "Proposed"), ("expansion", "Proposed"), ("upgrade", "Proposed"),
]

# AEMO changed the file layout in October 2025. Both layouts are handled here.
LAYOUTS = [
    {"sheet": "generator information", "status": "Commitment Status", "mw": ["Aggregated Nameplate Capacity (MW AC)", "Agg Nameplate Capacity (MW AC)"],
     "tech": ["Technology Type", "Technology Detail"]},
    {"sheet": "existinggeneration&newdevs", "status": "Unit Status", "mw": ["Nameplate Capacity (MW)"],
     "tech": ["Fuel Type", "Technology Type"]},
]

def tech_of(text):
    t = str(text).lower()
    if "pump" in t: return "Pumped hydro"
    if "batter" in t or "compressed air" in t: return "Battery"
    if "wind" in t: return "Wind"
    if "solar" in t or "photovoltaic" in t: return "Solar"
    return None

def status_of(text):
    t = str(text).lower()
    for key, val in STATUS_MAP:
        if key in t: return val
    return None

def norm(x):
    return re.sub(r"[^a-z0-9]", "", str(x).lower())

def load(path, inspect=False):
    xl = pd.ExcelFile(path)
    lay = sheet = None
    for L in LAYOUTS:
        sheet = next((s for s in xl.sheet_names if s.lower().replace(" ", "") == L["sheet"].replace(" ", "")), None)
        if sheet: lay = L; break
    if inspect: print(f"\n== {os.path.basename(path)}\nSheets: {xl.sheet_names}\nUsing sheet: {sheet}")
    if not lay: raise SystemExit(f"{path}: no generator sheet found. Send me the sheet list above.")
    raw = pd.read_excel(path, sheet_name=sheet, header=None)
    h = next(i for i in range(15) if "Region" in [str(c).strip() for c in raw.iloc[i]])
    df = raw.iloc[h + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[h]]
    mwcol = next((c for c in lay["mw"] if c in df.columns), lay["mw"][0])
    need = ["Region", "Site Name", "DUID", lay["status"], mwcol] + lay["tech"]
    missing = [c for c in need if c not in df.columns]
    if inspect: print("Missing columns:", missing or "none")
    if missing: raise SystemExit(f"{path}: missing {missing}. Send me the output above.")
    closure = next((c for c in ["Expected Closure Year"] if c in df.columns), None)
    coal = df[df["Region"].astype(str).str.strip().str.upper().str.startswith("NSW") &
              (df[lay["tech"][0]].astype(str) + " " + df[lay["tech"][1]].astype(str)).str.lower().str.contains("coal")]
    owner = next((c for c in ["Site Owner", "Owner"] if c in df.columns), None)
    coal = pd.DataFrame({"name": coal["Site Name"].astype(str).str.strip(),
                         "owner": coal[owner].astype(str).str.strip() if owner else "",
                         "mw": pd.to_numeric(coal[mwcol], errors="coerce"),
                         "year": pd.to_numeric(coal[closure], errors="coerce") if closure else float("nan"),
                         "status": coal[lay["status"]].astype(str),
                         "date": pd.to_datetime(coal["Closure Date"], errors="coerce") if "Closure Date" in coal.columns else pd.NaT})
    coal = coal[~coal.status.str.lower().str.contains("withdrawn")]
    out = pd.DataFrame({
        "region": df["Region"].astype(str).str.strip().str.upper(),
        "name": df["Site Name"].astype(str).str.strip(),
        "duid": df["DUID"].fillna("").astype(str).str.strip().str.upper(),
        "tech": (df[lay["tech"][0]].astype(str) + " " + df[lay["tech"][1]].astype(str)).map(tech_of),
        "status": df[lay["status"]].map(status_of),
        "mw": pd.to_numeric(df[mwcol], errors="coerce"),
        "fcu": pd.to_datetime(df["Full Commercial Use Date"], errors="coerce", format="mixed").dt.year if "Full Commercial Use Date" in df.columns else float("nan"),
    })
    nsw = out.region.str.startswith("NSW")
    counts = {"rows": int(nsw.sum()), "other_tech": int((nsw & out.tech.isna()).sum())}
    out = out[nsw & out.tech.notna() & out.status.notna() & (out.mw > 0)].copy()
    counts["dropped"] = counts["rows"] - counts["other_tech"] - len(out)
    out.attrs["coal"] = coal
    out.attrs["counts"] = counts
    out["key"] = [d if d not in ("", "NAN") else "site:" + norm(n) + ":" + t for d, n, t in zip(out.duid, out.name, out.tech)]
    if inspect:
        print("Rows kept (NSW wind, solar, battery, pumped hydro):", len(out))
        print("Status mix:", out.status.value_counts().to_dict())
    return out

def file_date(path):
    m = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s_-]*(20\d\d)", os.path.basename(path).lower())
    if m: return dt.datetime.strptime(m.group(1)[:3] + m.group(2), "%b%Y").date()
    return dt.date.fromtimestamp(os.path.getmtime(path))

TECHS = ["Wind", "Solar", "Battery", "Pumped hydro"]

def summarise(df):
    return {st: {t: int(round(df[(df.status == st) & (df.tech == t)].mw.sum())) for t in TECHS}
            for st in ["Operating", "Committed", "Anticipated", "Proposed"]}

def main():
    inspect = "--inspect" in sys.argv
    files = sorted(glob.glob(os.path.join(RAW, "*.xlsx")), key=file_date)
    if not files: raise SystemExit("Put the Generation Information .xlsx files in the raw folder.")
    frames = [(file_date(f), load(f, inspect)) for f in files]
    if frames[0][0] > ROADMAP_START.date().replace(month=3):
        print("Warning: earliest file is after early 2021, so the baseline of existing projects is approximate.")

    # Baseline is everything already operating in the earliest release (January 2021)
    base = frames[0][1]
    base_keys = set(base[base.status == "Operating"].key)
    base_sites = set(norm(n) for n in base[base.status == "Operating"].name)
    def is_new(df):
        # Units without a DUID are matched on site name, but only when operating, so a new stage
        # at an old site (such as a proposed extension) still counts as new
        old = df.key.isin(base_keys) | ((df.status == "Operating") & df.key.str.startswith("site:") & df.name.map(norm).isin(base_sites))
        return ~old

    history, first_seen = [], {}
    for d, df in frames[1:] if len(frames) > 1 else frames:
        new = df[is_new(df) & (df.status != "Closing")]
        s = summarise(new)
        history.append({"date": d.isoformat(),
                        "operating_gen_mw": s["Operating"]["Wind"] + s["Operating"]["Solar"],
                        "operating_storage_mw": s["Operating"]["Battery"] + s["Operating"]["Pumped hydro"],
                        "committed_gen_mw": s["Committed"]["Wind"] + s["Committed"]["Solar"],
                        "committed_storage_mw": s["Committed"]["Battery"] + s["Committed"]["Pumped hydro"]})
        for k in new[new.status == "Operating"].key:
            first_seen.setdefault(k, d)
        if inspect: print(f"{d}: new operating wind+solar {history[-1]['operating_gen_mw']} MW, storage {history[-1]['operating_storage_mw']} MW")

    latest_date, latest = frames[-1]
    every = latest[latest.status == "Operating"]
    aemo_total = {"gen_mw": int(round(every[every.tech.isin(["Wind", "Solar"])].mw.sum())),
                  "storage_mw": int(round(every[every.tech.isin(["Battery", "Pumped hydro"])].mw.sum()))}
    counts = dict(latest.attrs["counts"])
    keep = is_new(latest) & (latest.status != "Closing")
    counts["pre_roadmap"] = int((~keep).sum())
    latest = latest[keep].copy()
    counts["units"] = len(latest)
    op = latest[latest.status == "Operating"].copy()
    op["year"] = op.key.map(lambda k: first_seen.get(k, latest_date).year)
    by_year, by_year_names = {}, {}
    for (y, t), g in op.groupby(["year", "tech"]):
        by_year.setdefault(int(y), {x: 0 for x in TECHS})[t] = int(round(g.mw.sum()))
        sites = g.groupby("name").mw.sum().sort_values(ascending=False)
        by_year_names.setdefault(int(y), {})[t] = [f"{n} ({int(round(m))} MW)" for n, m in sites.items()]

    # Combine units into sites for the project table. Operating sites show the year they first
    # appeared as operating, the rest show AEMO's expected full commercial use year.
    latest["year"] = [first_seen[k].year if s == "Operating" and k in first_seen else f
                      for k, s, f in zip(latest.key, latest.status, latest.fcu)]
    sites = (latest.groupby(["name", "tech", "status"], as_index=False)
             .agg(mw=("mw", "sum"), year=("year", "min")).sort_values("mw", ascending=False))
    projects = [{"name": r.name, "tech": r.tech, "status": r.status, "mw": int(round(r.mw)),
                 "year": int(r.year) if pd.notna(r.year) else None} for r in sites.itertuples() if r.mw >= 0.5]
    counts["projects"] = len(projects)
    operating_sites = [p for p in projects if p["status"] == "Operating"]
    coal = frames[-1][1].attrs["coal"]
    coal = (coal.groupby("name", as_index=False).agg(mw=("mw", "sum"), year=("year", "max"), date=("date", "max"),
                                                    owner=("owner", "first"), units=("mw", "size"))
            .sort_values("year"))
    coal = [{"name": r.name, "owner": r.owner, "units": int(r.units), "mw": int(round(r.mw)),
             "year": int(r.year) if pd.notna(r.year) else None,
             "date": r.date.strftime("%Y-%m-%d") if pd.notna(r.date) else None} for r in coal.itertuples()]

    data = {"updated": latest_date.isoformat(), "source_file": os.path.basename(files[-1]),
            "baseline": frames[0][0].isoformat(), "targets": TARGETS, "aemo_total": aemo_total, "counts": counts, "summary": summarise(latest),
            "by_year": by_year, "by_year_names": by_year_names, "history": history,
            "projects": projects, "coal": coal}
    s = data["summary"]
    print(f"\nLatest release {latest_date}. New since {data['baseline']}:")
    for st in s: print(f"  {st:11s} " + ", ".join(f"{t} {v:,} MW" for t, v in s[st].items()))
    if inspect:
        print("\nCoal:", coal)
        print("\nLargest new operating sites:")
        for p in operating_sites[:15]: print(f"  {p['name']} ({p['tech']}) {p['mw']} MW")
        print("\nLooks fine? Run again without --inspect to write", OUT); return
    os.makedirs("data", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("window.ROADMAP = " + json.dumps(data) + ";\n")
    print("Wrote", OUT)

if __name__ == "__main__":
    main()
