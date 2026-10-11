"""
Builds data/local_economy.js for local-economy.html: what makes your local economy tick?

Reads the files saved by scripts/fetch_local_economy.py in raw/local/ and works out,
for every council area in Australia:

  * what its residents do for a living, and what it specialises in compared with
    Australia (location quotients), from ABS Jobs in Australia
  * five resilience dimensions, each scored 0 to 100 against similar areas only
      diversity     how evenly jobs are spread across industries
      exposure      share of jobs in industries tied to commodity prices and the
                    shift to net zero (mining, manufacturing, energy, farming)
      growth        change in jobs over five years, split into what the industry
                    mix explains and what is local (shift-share)
      business      change in the number of businesses
      income        median employee income
  * how its industries changed over ten years (Census 2011, 2016 and 2021)

Similar areas are grouped by where people live (capital city or not, and the ABS
remoteness of residents' mesh blocks) and by size. Every dimension is tested for
reliability before it is scored (see RELIABLE below).

    python scripts/build_local_economy.py
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw" / "local"
OUT = ROOT / "data" / "local_economy.js"
SUMMARY = ROOT / "data" / "local_economy_summary.js"

MIN_JOBS = 1000        # fewer resident employee jobs than this: too small to score reliably
MIN_PEERS = 8          # smallest peer group allowed
RELIABLE = 0.6         # rank correlation a dimension must reach when its inputs shift by a year
STATES = {"1": "NSW", "2": "Vic", "3": "Qld", "4": "SA", "5": "WA", "6": "Tas", "7": "NT", "8": "ACT", "9": "Other"}

# ANZSIC divisions, in the order of LEED_5..LEED_23 and EMP_IND_2..EMP_IND_20
INDUSTRIES = [
    ("A", "Agriculture, forestry and fishing", "Farming, forestry and fishing"),
    ("B", "Mining", "Mining"),
    ("C", "Manufacturing", "Manufacturing"),
    ("D", "Electricity, gas, water and waste services", "Energy, water and waste"),
    ("E", "Construction", "Construction"),
    ("F", "Wholesale trade", "Wholesale"),
    ("G", "Retail trade", "Retail"),
    ("H", "Accommodation and food services", "Hospitality"),
    ("I", "Transport, postal and warehousing", "Transport and logistics"),
    ("J", "Information media and telecommunications", "Media and telecoms"),
    ("K", "Financial and insurance services", "Finance and insurance"),
    ("L", "Rental, hiring and real estate services", "Real estate and hiring"),
    ("M", "Professional, scientific and technical services", "Professional services"),
    ("N", "Administrative and support services", "Administrative services"),
    ("O", "Public administration and safety", "Government and safety"),
    ("P", "Education and training", "Education"),
    ("Q", "Health care and social assistance", "Health and care"),
    ("R", "Arts and recreation services", "Arts and recreation"),
    ("S", "Other services", "Other services"),
]
LEED_IND = [f"LEED_{i}" for i in range(5, 24)]
CEN_IND = [f"EMP_IND_{i}" for i in range(2, 21)]
EXPOSED = ["A", "B", "C", "D"]

DIMENSIONS = [
    ("diversity", "Diversity", "higher"),
    ("exposure", "Exposure to swings and transition", "lower"),
    ("growth", "Jobs growth", "higher"),
    ("business", "Business growth", "higher"),
    ("income", "Incomes", "higher"),
]


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    reg = pd.read_csv(RAW / "regional.csv.gz", dtype={"LGA_2021": str, "TIME_PERIOD": str})
    reg["OBS_VALUE"] = pd.to_numeric(reg["OBS_VALUE"], errors="coerce")
    reg = reg.dropna(subset=["OBS_VALUE"])
    names = pd.read_csv(RAW / "lga_names.csv", dtype=str)
    remote = pd.read_csv(RAW / "lga_remote.csv", dtype={"LGA_CODE_2021": str})
    return reg, names, remote


def table(reg: pd.DataFrame, measures: list[str]) -> dict[str, pd.DataFrame]:
    """{measure: councils x years}"""
    sub = reg[reg["MEASURE"].isin(measures)]
    return {m: g.pivot_table(index="LGA_2021", columns="TIME_PERIOD", values="OBS_VALUE")
            for m, g in sub.groupby("MEASURE")}


def rank_corr(a: pd.Series, b: pd.Series) -> float:
    d = pd.concat([a, b], axis=1).dropna()
    return float(d.iloc[:, 0].rank().corr(d.iloc[:, 1].rank())) if len(d) > 20 else float("nan")


def main() -> None:
    reg, names, remote = load()
    name = dict(zip(names["code"], names["name"]))
    T = table(reg, ["LEED_24"] + LEED_IND + ["CABEE_5", "CABEE_3", "CABEE_4", "CABEE_38", "ERP_P_20",
                                            "LAND", "INCOME_2", "LF_4"])
    jobs = T["LEED_24"]
    yrs = sorted(c for c in jobs.columns if jobs[c].notna().sum() > 400)
    Y, Y0 = yrs[-1], yrs[-6] if len(yrs) >= 6 else yrs[0]
    last3 = yrs[-3:]
    print(f"Jobs years {yrs[0]} to {Y}; growth {Y0} to {Y}; structure from {last3}")

    ind = {code: T[m] for (code, _, _), m in zip(INDUSTRIES, LEED_IND)}
    nat = {k: v.sum() for k, v in ind.items()}           # Australia, by year
    nat_total = sum(nat.values())

    def shares(cols) -> pd.DataFrame:
        s = pd.DataFrame({k: ind[k][cols].sum(axis=1) for k in ind})
        return s.div(s.sum(axis=1), axis=0)

    sh = shares(last3)
    nat_sh = pd.Series({k: nat[k][last3].sum() for k in ind}) / sum(nat[k][last3].sum() for k in ind)

    # ---- dimensions (raw values) ----
    def diversity(s):  # effective number of industries, 1 / Herfindahl
        return 1 / (s ** 2).sum(axis=1)

    raw = pd.DataFrame(index=jobs.index)
    raw["diversity"] = diversity(sh)
    raw["exposure"] = sh[EXPOSED].sum(axis=1)
    raw["growth"] = jobs[Y] / jobs[Y0] - 1
    biz = T["CABEE_5"]
    byrs = sorted(c for c in biz.columns if biz[c].notna().sum() > 400)
    B, B0 = byrs[-1], byrs[0]
    raw["business"] = biz[B] / biz[B0] - 1
    inc = T["INCOME_2"]
    iyrs = sorted(c for c in inc.columns if inc[c].notna().sum() > 400)
    raw["income"] = inc[iyrs[-1]]
    print(f"Businesses {B0} to {B}; incomes {iyrs[-1]}")

    # ---- reliability: does each dimension hold up when its inputs move by a year? ----
    alt = pd.DataFrame(index=jobs.index)
    # level measures: one year against the year before (no overlap); growth: the
    # window moved by a year at each end
    one, prev = shares([Y]), shares([yrs[-2]])
    raw_one = pd.DataFrame({"diversity": diversity(one), "exposure": one[EXPOSED].sum(axis=1)})
    alt["diversity"] = diversity(prev)
    alt["exposure"] = prev[EXPOSED].sum(axis=1)
    alt["growth"] = jobs[yrs[-2]] / jobs[yrs[0]] - 1
    alt["growth_late"] = jobs[Y] / jobs[yrs[1]] - 1
    alt["business"] = biz[byrs[-2]] / biz[B0] - 1
    alt["business_late"] = biz[B] / biz[byrs[1]] - 1
    alt["income"] = inc[iyrs[-2]]
    big = jobs[Y] >= MIN_JOBS
    reliability = {d: round(rank_corr(raw.loc[big, d], alt.loc[big, d]), 2) for d, _, _ in DIMENSIONS}
    for d in ("diversity", "exposure"):
        reliability[d] = round(rank_corr(raw_one.loc[big, d], alt.loc[big, d]), 2)
    reliability["growth"] = round(rank_corr(alt.loc[big, "growth"], alt.loc[big, "growth_late"]), 2)
    reliability["business"] = round(rank_corr(alt.loc[big, "business"], alt.loc[big, "business_late"]), 2)
    print("reliability (rank correlation, inputs moved back a year):", reliability)

    # ---- shift-share ----
    base = pd.DataFrame({k: ind[k][Y0] for k in ind})
    nat_g = {k: nat[k][Y] / nat[k][Y0] - 1 for k in ind}
    expected = sum(base[k].fillna(0) * nat_g[k] for k in ind) / base.sum(axis=1)
    aus_g = nat_total[Y] / nat_total[Y0] - 1
    mix = expected - aus_g
    local = raw["growth"] - expected

    # ---- peer groups ----
    rem = remote.copy()
    rem["cap"] = rem["GCCSA"].str.startswith("Greater") | rem["GCCSA"].str.contains("Capital Territory")
    tot = rem.groupby("LGA_CODE_2021")["persons"].sum()
    cap = rem[rem["cap"]].groupby("LGA_CODE_2021")["persons"].sum().reindex(tot.index).fillna(0) / tot
    ra = rem.pivot_table(index="LGA_CODE_2021", columns="RA", values="persons", aggfunc="sum").fillna(0)
    ra = ra.div(ra.sum(axis=1), axis=0)
    print("remoteness areas:", list(ra.columns))
    main_ra = ra.idxmax(axis=1)
    pop = T["ERP_P_20"]
    pop = pop[pop.columns.max()]
    land = T["LAND"]
    land = land[land.columns.max()] / 100            # hectares to km2
    density = pop / land

    def group(c: str) -> str | None:
        if c not in tot.index or tot[c] == 0:
            return None
        r = str(main_ra.get(c, ""))
        if cap.get(c, 0) >= 0.5:
            return "cap_inner" if density.get(c, 0) >= 1500 else "cap_outer"
        if "Remote" in r:
            return "remote"
        if r.startswith("Major") or pop.get(c, 0) >= 50000:
            return "regional_city"
        if r.startswith("Inner"):
            return "inner_regional"
        return "outer_regional"

    GROUPS = {
        "cap_inner": ("Established capital city suburbs", "Council areas in a capital city with at least 1,500 residents per square kilometre"),
        "cap_outer": ("Capital city growth and fringe areas", "Council areas in a capital city with fewer than 1,500 residents per square kilometre, mostly on the growing edge"),
        "regional_city": ("Regional cities", "Council areas outside the capitals that are classed as major cities, or have at least 50,000 residents"),
        "inner_regional": ("Inner regional towns and shires", "Smaller council areas where most residents live in inner regional Australia"),
        "outer_regional": ("Outer regional towns and shires", "Smaller council areas where most residents live in outer regional Australia"),
        "remote": ("Remote and very remote areas", "Council areas where most residents live in remote or very remote Australia"),
    }

    # ---- assemble councils ----
    codes = [c for c in jobs.index if c in name and jobs.loc[c, Y] == jobs.loc[c, Y] and group(c)]
    codes = [c for c in codes if not name[c].startswith(("Unincorporated", "No usual", "Migratory"))]
    df = pd.DataFrame(index=codes)
    df["group"] = [group(c) for c in codes]
    df["scored"] = jobs.loc[codes, Y] >= MIN_JOBS
    for g, n in df[df["scored"]].groupby("group").size().items():
        print(f"  {g}: {n} scored")

    scores = pd.DataFrame(index=codes)
    for d, _, better in DIMENSIONS:
        for g, idx in df[df["scored"]].groupby("group").groups.items():
            v = raw.loc[idx, d]
            p = v.rank(pct=True, method="average")
            # percentile on a 0 to 100 scale, so the middle council scores about 50
            p = (v.rank(method="average") - 0.5) / v.notna().sum() * 100
            scores.loc[idx, d] = p if better == "higher" else 100 - p

    census = census_shares()
    links = council_page_names()
    out = []
    for c in codes:
        rec = {
            "code": c, "name": name[c], "state": STATES.get(c[0], ""), "group": df.loc[c, "group"],
            "scored": bool(df.loc[c, "scored"]),
            "pop": _int(pop.get(c)), "km2": _int(land.get(c)),
            "jobs": _int(jobs.loc[c, Y]),
            "jobs_hist": {y: _int(jobs.loc[c, y]) for y in yrs if jobs.loc[c, y] == jobs.loc[c, y]},
            "biz_hist": {y: _int(biz.loc[c, y]) for y in byrs if c in biz.index and biz.loc[c, y] == biz.loc[c, y]},
            "share": [round(float(sh.loc[c, k]) * 100, 2) if sh.loc[c, k] == sh.loc[c, k] else None for k, _, _ in INDUSTRIES],
            "raw": {d: _r(raw.loc[c, d], 4) for d, _, _ in DIMENSIONS},
            "score": {d: _r(scores.loc[c, d], 1) for d, _, _ in DIMENSIONS} if df.loc[c, "scored"] else None,
            "mix": _r(mix.get(c), 4), "local": _r(local.get(c), 4), "expected": _r(expected.get(c), 4),
            "unemp": _r(T["LF_4"].loc[c].dropna().iloc[-1] if "LF_4" in T and c in T["LF_4"].index and T["LF_4"].loc[c].notna().any() else None, 1),
            "ra": {k: round(float(v) * 100) for k, v in ra.loc[c].items() if v >= 0.005} if c in ra.index else {},
        }
        # Census industry shares by year (residents' main job), for the ten-year view
        rec["census"] = {y: [_r(census.loc[(c, y), k] * 100, 1) if (c, y) in census.index else None
                             for k, _, _ in INDUSTRIES]
                         for y in ("2011", "2016", "2021") if (c, y) in census.index}
        st = {"NSW": "nsw", "Vic": "vic"}.get(rec["state"])
        if st and _norm(name[c]) in links.get(st, {}):
            rec["link"] = [st, links[st][_norm(name[c])]]
        out.append(rec)
    for st in ("vic", "nsw"):
        got = {r["link"][1] for r in out if r.get("link", [None])[0] == st}
        miss = sorted(set(links.get(st, {}).values()) - got)
        print(f"{st}: {len(got)} linked to councils.html; not linked {miss}")

    data = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "years": {"jobs": [Y0, Y], "jobs_all": yrs, "structure": last3, "business": [B0, B], "income": iyrs[-1]},
        "industries": [{"code": k, "name": n, "short": s} for k, n, s in INDUSTRIES],
        "exposed": EXPOSED,
        "australia": {"share": [round(float(nat_sh[k]) * 100, 2) for k, _, _ in INDUSTRIES],
                      "growth": round(float(aus_g), 4),
                      "jobs_hist": {y: _int(nat_total[y]) for y in yrs},
                      "growth_by_industry": [round(float(nat_g[k]), 4) for k, _, _ in INDUSTRIES]},
        "dimensions": [{"id": d, "label": l, "better": b, "reliability": reliability[d]} for d, l, b in DIMENSIONS],
        "groups": {k: {"label": a, "about": b, "n": int((df["group"] == k).sum()),
                       "scored": int(((df["group"] == k) & df["scored"]).sum())} for k, (a, b) in GROUPS.items()},
        "min_jobs": MIN_JOBS, "councils": out,
    }
    OUT.write_text("// Built by scripts/build_local_economy.py from ABS data\nwindow.LOCAL_ECONOMY = "
                   + json.dumps(data, separators=(",", ":"), allow_nan=False) + ";\n", encoding="utf-8")
    SUMMARY.write_text("window.LOCAL_ECONOMY_SUMMARY = " + json.dumps(
        {"councils": len(out), "scored": int(df["scored"].sum()), "generated": data["generated"]}) + ";\n", encoding="utf-8")
    print(f"Wrote {OUT.name}: {len(out)} council areas, {int(df['scored'].sum())} scored, "
          f"{OUT.stat().st_size / 1e3:.0f} kB")


def census_shares() -> pd.DataFrame:
    """Census T34, persons, share of employed residents who stated an industry,
    indexed by (council, year), one column per ANZSIC division."""
    t = pd.read_csv(RAW / "census_ind.csv.gz", dtype=str)
    t = t[(t["SEXP"] == "3") & t["INDP"].isin([k for k, _, _ in INDUSTRIES])]
    t["OBS_VALUE"] = pd.to_numeric(t["OBS_VALUE"], errors="coerce")
    p = t.pivot_table(index=["REGION", "TIME_PERIOD"], columns="INDP", values="OBS_VALUE", aggfunc="sum")
    return p.div(p.sum(axis=1), axis=0)


def _norm(n: str) -> str:
    """Council names as both pages can agree on them: no 'Shire', 'City', or state tag."""
    n = re.sub(r"\s*\((NSW|Vic\.?|Qld|SA|WA|Tas\.?|NT|ACT|[A-Z]+\.?)\)", "", n)
    n = re.sub(r"^Borough of\s+", "", n)
    n = {"Moreland": "Merri-bek"}.get(n.strip(), n)  # renamed in 2022
    n = re.sub(r"\b(Shire|City|Rural City|Borough|Council|Regional|Municipal)\b", "", n, flags=re.I)
    return re.sub(r"[^a-z]", "", n.lower())


def council_page_names() -> dict[str, dict[str, str]]:
    """Names used on councils.html, so each Victorian and NSW area can link to it."""
    p = ROOT / "data" / "councils.js"
    if not p.exists():
        return {}
    t = p.read_text(encoding="utf-8")
    d = json.loads(t[t.index("{"): t.rindex("}") + 1])
    return {s: {_norm(c["name"]): c["name"] for c in d["states"][s]["councils"]} for s in d["states"]}


def _int(v):
    return None if v is None or v != v else int(round(float(v)))


def _r(v, n):
    return None if v is None or v != v else round(float(v), n)


if __name__ == "__main__":
    main()
