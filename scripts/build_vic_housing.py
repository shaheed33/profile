"""
Builds data/vic_housing.js for vic-housing.html: is Victoria building enough homes?

Downloads ABS building approvals (by council and for the state), dwellings
started, finished and under construction, and Victoria's population, into
raw/vic/, then compares them with two government targets:

  * the Housing Statement: 800,000 homes in the ten years from 2024, and
  * Plan for Victoria: 2.24 million more homes by 2051, split by council
    (data/vic_targets.csv, made by scripts/fetch_vic_static.py).

    python scripts/build_vic_housing.py              # live download
    python scripts/build_vic_housing.py --offline    # reuse files in raw/vic/
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from wa_sources import ABS_BASE, _get, parse_abs_csv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "vic"
OUT = ROOT / "data" / "vic_housing.js"
TARGETS = ROOT / "data" / "vic_targets.csv"

STATEMENT_TOTAL = 800_000          # Housing Statement, homes in the decade from 2024
STATEMENT_START = pd.Period("2024Q1", "Q")
STATEMENT_YEARS = 10
PLAN_START, PLAN_END = 2024, 2051  # council targets: additional homes from 2023 levels by 2051
PEOPLE_PER_HOME = 2.5              # Victoria's average household size, 2021 Census

# file stem -> (dataflow, key, start). Approvals by council come in one dataflow per
# council boundary year, each covering a financial year; the newest are tried first.
DOWNLOADS = {
    "activity": ("BUILDING_ACTIVITY", ".2......Q", "1990-01"),
    "approvals_state": ("BA_GCCSA", "1.1.9.TOT.100.10..M", "2000-01"),
    "lga2023": ("BA_LGA2023", "1.9.TOT.100.LGA2023..M", "2023-01"),
    "lga2024": ("BA_LGA2024", "1.9.TOT.100.LGA2024..M", "2024-01"),
    "lga2025": ("BA_LGA2025", "1.9.TOT.100.LGA2025..M", "2025-01"),
    "lga2026": ("BA_LGA2026", "1.9.TOT.100.LGA2026..M", "2026-01"),
    "erp": ("ERP_Q", "1.3.TOT.2.Q", "2015-01"),
}
OPTIONAL = {"lga2026", "erp"}


def r(x, n=0):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), n) if n else int(round(float(x)))


def qlabel(p: pd.Period) -> str:
    return ["Jan to Mar", "Apr to Jun", "Jul to Sep", "Oct to Dec"][p.quarter - 1] + f" {p.year}"


def load(stem: str, offline: bool) -> pd.DataFrame | None:
    flow, key, start = DOWNLOADS[stem]
    f = RAW / f"{stem}.csv"
    if not offline:
        url = f"{ABS_BASE}/ABS,{flow},/{key}?startPeriod={start}&format=csvfilewithlabels"
        t0 = time.time()
        try:
            text = _get(url)
            f.write_text(text, encoding="utf-8")
            print(f"  {flow} [{key}] {len(text) / 1e6:.1f} MB in {time.time() - t0:.0f}s", flush=True)
        except RuntimeError as e:
            print(f"  {flow} [{key}] failed: {str(e)[-150:]}", flush=True)
            if stem not in OPTIONAL:
                raise SystemExit(f"Required download failed: {flow}")
    gz = f.with_suffix(".csv.gz")
    if f.exists():
        text = f.read_text(encoding="utf-8")
    elif gz.exists():
        text = gzip.open(gz, "rt", encoding="utf-8").read()
    else:
        return None
    return parse_abs_csv(text).dropna(subset=["OBS_VALUE"])


def pick(df: pd.DataFrame, freq: str, **match) -> pd.Series:
    """One series from a parsed ABS file, matched on label text; fails loudly if
    the filter does not single out exactly one series."""
    m = pd.Series(True, index=df.index)
    for dim, pat in match.items():
        m &= df[dim].str.contains(pat, case=False, regex=True, na=False)
    sub = df[m]
    dims = [c for c in df.columns if not c.endswith("__code") and c not in ("TIME_PERIOD", "OBS_VALUE")]
    n = sub.groupby(dims).ngroups
    if n != 1:
        raise LookupError(f"{match} matched {n} series")
    idx = pd.PeriodIndex(sub["TIME_PERIOD"].str.replace("-Q", "Q", regex=False), freq=freq)
    return pd.Series(sub["OBS_VALUE"].values, index=idx).sort_index()


def norm(name: str) -> str:
    """Council names as the ABS writes them ('Kingston (Vic.)') matched to the targets list."""
    name = re.sub(r"\s*\(Vic\.?\)", "", name)
    return re.sub(r"[^a-z]", "", name.lower())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use files already in raw/vic")
    args = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    data = {k: load(k, args.offline) for k in DOWNLOADS}
    notes = [f"{DOWNLOADS[k][0]} not available" for k, v in data.items() if v is None and k in OPTIONAL]

    # ---------------------------------------------------------- the state
    act = data["activity"]
    base = dict(BLD_WORK_TYPE="^total work$", SECTOR_OWN="^total sectors$", TYPE_BLDG="^all buildings$",
                TSEST="^original$", PRICE_ADJ="current")
    done = pick(act, "Q", MEASURE="^dwelling units completed$", **base)
    started = pick(act, "Q", MEASURE="^dwelling units commenced$", **base)
    building = pick(act, "Q", MEASURE="^dwelling units under construction$", **base)
    last_q = done.index[-1]

    st = data["approvals_state"]
    appr = {lab: pick(st, "M", MEASURE="^number of dwelling units$", VALUE="^total$", SECTOR="^total sectors$",
                      WORK_TYPE="^total work$", BUILDING_TYPE="^total residential$", TSEST="^original$",
                      REGION=pat)
            for lab, pat in [("vic", "^victoria$"), ("melb", "^greater melbourne$"), ("rest", "^rest of vic")]}
    last_m = appr["vic"].index[-1]
    appr12 = {k: v.rolling(12).sum() for k, v in appr.items()}

    # progress against 800,000 in ten years from 2024
    since = done[done.index >= STATEMENT_START]
    built = float(since.sum())
    nq = len(since)
    path_now = STATEMENT_TOTAL * nq / (STATEMENT_YEARS * 4)
    pace = float(done.iloc[-4:].sum())                  # homes finished in the latest four quarters
    left = STATEMENT_TOTAL - built
    years_more = left / pace if pace > 0 else np.nan
    end_of_last = last_q.end_time
    finish = end_of_last + pd.Timedelta(days=365.25 * years_more)
    deadline = (STATEMENT_START + STATEMENT_YEARS * 4 - 1).end_time
    need_rest = left / max((deadline - end_of_last).days / 365.25, 0.25)
    cum = since.cumsum()
    yearly = done.groupby(done.index.year).sum()
    full_years = yearly[[y for y in yearly.index if (done.index.year == y).sum() == 4]]
    fy = done.groupby((done.index + 2).year).sum()      # financial years (Jul to Jun), by the year they end
    fy = fy[[y for y in fy.index if ((done.index + 2).year == y).sum() == 4]]

    # share of approved homes that end up finished, over the past five years
    # (approvals lead completions by about a year)
    a_q = appr["vic"].groupby(appr["vic"].index.asfreq("Q")).sum()
    win = done.index[-20:]
    conv = float(done[win].sum() / a_q.reindex(win - 4).sum())

    # ---------------------------------------------------------- councils
    with open(TARGETS, encoding="utf-8") as fh:
        targets = {norm(row["council"]): row for row in csv.DictReader(fh)}
    frames = []
    for stem in ("lga2023", "lga2024", "lga2025", "lga2026"):
        df = data.get(stem)
        if df is None:
            continue
        df = df[df["REGION__code"].str.match(r"^2\d{4}$") & df["MEASURE"].str.match("Number of dwelling units")]
        frames.append(df.assign(src=stem)[["REGION__code", "REGION", "TIME_PERIOD", "OBS_VALUE", "src"]])
    lga = pd.concat(frames)
    # where boundary years overlap, keep the newest dataflow for each month
    lga = lga.sort_values("src").drop_duplicates(["REGION__code", "TIME_PERIOD"], keep="last")
    lga["key"] = lga["REGION"].map(norm)
    lga["month"] = pd.PeriodIndex(lga["TIME_PERIOD"], freq="M")
    lga = lga[lga["month"] <= last_m]
    lga_last = lga["month"].max()
    months_since = (lga_last - pd.Period("2024-01", "M")).n + 1
    plan_years = PLAN_END - PLAN_START + 1
    councils, unmatched = [], []
    for key, g in lga.groupby("key"):
        t = targets.get(key)
        if t is None:
            unmatched.append(g["REGION"].iloc[0])
            continue
        tgt = int(t["target_2051"])
        per_year = tgt / plan_years
        a12 = float(g[g["month"] > lga_last - 12]["OBS_VALUE"].sum())
        a_since = float(g[g["month"] >= pd.Period("2024-01", "M")]["OBS_VALUE"].sum())
        councils.append({
            "code": g.sort_values("src")["REGION__code"].iloc[-1], "name": t["council"], "region": t["region"],
            "homes_2023": int(t["homes_2023"]), "target": tgt,
            "greenfield": int(t["greenfield"]) if t["greenfield"] else None,
            "per_year": r(per_year), "approved_12m": r(a12), "approved_since_2024": r(a_since),
            "pace": r(a12 / per_year, 3) if per_year else None,
            "pace_since_2024": r(a_since / (per_year * months_since / 12), 3) if per_year else None,
            "growth_pct": r(100 * tgt / int(t["homes_2023"]), 1),
        })
    missing = sorted(set(t["council"] for t in targets.values()) - {c["name"] for c in councils})
    if unmatched:
        notes.append("ABS areas without a target: " + ", ".join(sorted(unmatched)))
    if missing:
        notes.append("Targets without ABS approvals: " + ", ".join(missing))
    print(f"{len(councils)} councils matched; unmatched ABS areas {unmatched}; targets missing {missing}")

    def region_sum(pred):
        cs = [c for c in councils if pred(c["region"])]
        return {"per_year": r(sum(c["target"] for c in cs) / plan_years),
                "approved_12m": r(sum(c["approved_12m"] for c in cs)), "councils": len(cs)}

    split = {"melbourne": region_sum(lambda x: x.startswith("Metropolitan")),
             "regional": region_sum(lambda x: x == "Regional Victoria")}

    # ---------------------------------------------------------- population (optional)
    people = None
    erp = data.get("erp")
    if erp is not None:
        try:
            pop = pick(erp, "Q", MEASURE="estimated resident population", SEX="^persons$", AGE="total|all ages",
                       REGION="^victoria$")
            grow = float(pop.iloc[-1] - pop.iloc[-5])
            people = {"q": qlabel(pop.index[-1]), "population": r(pop.iloc[-1]), "added": r(grow),
                      "homes_worth": r(grow / PEOPLE_PER_HOME)}
        except (LookupError, KeyError) as e:
            notes.append(f"Population skipped: {e}")

    # ---------------------------------------------------------- write
    per_day_needed = STATEMENT_TOTAL / STATEMENT_YEARS / 365.25
    per_day_built = pace / 365.25
    out = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
        "statement": {
            "total": STATEMENT_TOTAL, "per_year": STATEMENT_TOTAL // STATEMENT_YEARS,
            "start": str(STATEMENT_START), "end_label": "Dec 2033",
            "built": r(built), "on_track_by_now": r(path_now), "gap": r(path_now - built),
            "quarters": nq, "through": qlabel(last_q),
            "share_done": r(built / STATEMENT_TOTAL, 4), "share_time": r(nq / (STATEMENT_YEARS * 4), 4),
            "pace_per_year": r(pace), "per_day_needed": r(per_day_needed, 1), "per_day_built": r(per_day_built, 1),
            "minutes_needed": r(1440 / per_day_needed, 1), "minutes_built": r(1440 / per_day_built, 1),
            "finish_year": int(finish.year) if pd.notna(finish) else None,
            "needed_per_year_from_now": r(need_rest),
            "cumulative": [[str(p), r(v)] for p, v in cum.items()],
        },
        "history": {
            "completed": [[str(p), r(v)] for p, v in done[done.index >= pd.Period("2000Q1", "Q")].items()],
            "started": [[str(p), r(v)] for p, v in started[started.index >= pd.Period("2000Q1", "Q")].items()],
            "approved_12m": [[str(p), r(v)] for p, v in appr12["vic"].dropna().items() if p.month in (3, 6, 9, 12)],
            "best_year": {"year": int(full_years.idxmax()), "homes": r(full_years.max())},
            "best_fy": {"year": f"{int(fy.idxmax()) - 1}-{str(int(fy.idxmax()))[2:]}", "homes": r(fy.max())},
            "years_at_80k": int((full_years >= 80_000).sum()),
        },
        "pipeline": {
            "approved_12m": r(appr12["vic"].iloc[-1]), "approved_through": last_m.strftime("%b %Y"),
            "started_4q": r(started.iloc[-4:].sum()), "completed_4q": r(pace), "quarter": qlabel(last_q),
            "under_construction": r(building.iloc[-1]), "finish_rate": r(conv, 3),
        },
        "plan": {"total": sum(int(t["target_2051"]) for t in targets.values()),
                 "per_year": r(sum(int(t["target_2051"]) for t in targets.values()) / plan_years),
                 "years": plan_years, "approvals_through": lga_last.strftime("%b %Y"),
                 "months_since_2024": months_since, "split": split},
        "councils": sorted(councils, key=lambda c: c["name"]),
        "people": people,
        "notes": notes,
    }
    OUT.write_text("window.VIC_HOUSING = " + json.dumps(out, separators=(",", ":")) + ";\n", encoding="utf-8")
    s = out["statement"]
    print(f"Built since 2024: {s['built']:,} of 800,000 ({s['quarters']} quarters; on-track figure {s['on_track_by_now']:,})")
    print(f"Pace {s['pace_per_year']:,} a year = {s['per_day_built']} a day vs {s['per_day_needed']} needed; "
          f"finish year at this pace {s['finish_year']}")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
