"""
Builds the data for maldives-grants.html: who gives Maldives grants, and for what?

Reads the OECD Creditor Reporting System (CRS) for Maldives
(data/raw/oecd_crs_maldives.csv.gz, downloaded from the OECD Data Explorer API
with every donor, every sector, all channels and modalities as totals, current
and constant prices, commitments and disbursements, 1995 onwards).

China does not report to the OECD, so its grants come from AidData's Global
Chinese Development Finance Dataset 3.0 (commitments from 2000 to 2021, rows
AidData recommends for aggregates, nominal US dollars), mapped to goals through
data/lookups/aiddata_sector_sdg.csv. AidData records commitments only.

Grants come from the CRS and AidData. Loans are left to the Ministry of Finance register
(scripts/build_maldives_loans.py), which also covers lenders that do not report
to the OECD, such as China and India, so nothing is counted twice.

  data/lookups/crs_donor_groups.csv   donor codes, display names and groups (edit by hand)
  data/lookups/crs_purpose_sdg.csv    OECD purpose codes mapped to goals (edit by hand)

  data/processed/grants_tagged.csv    grants by year, donor and purpose, with goals (download)
  data/maldives_grants.json           what the page reads

    python scripts/build_maldives_grants.py
"""
from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "oecd_crs_maldives.csv.gz"
CHINA = ROOT / "data" / "raw" / "aiddata_gcdf3_maldives.csv"   # AidData Global Chinese Development Finance Dataset 3.0, Maldives rows
LOOKUPS = ROOT / "data" / "lookups"
OUT_CSV = ROOT / "data" / "processed" / "grants_tagged.csv"
OUT_JSON = ROOT / "data" / "maldives_grants.json"
RETRIEVED = "2026-10-13"
LAST_FULL_YEAR = 2024      # later years hold only a few early reports
SHARE_FROM = 2015          # grant share of each lender is measured from this year

# CRS codes used below
GRANTS, LOANS = "11", "13"             # MEASURE: ODA grants, ODA loans
COMMIT, DISB = "C", "D"                # FLOW_TYPE
CURRENT = "V"                          # PRICE_BASE: current prices

GROUPS = [("bilateral", "Bilateral"), ("multilateral", "Multilateral"), ("un", "UN agencies")]
GOALS = [f"SDG {i}" for i in range(1, 18)] + ["General", "Humanitarian", "Multisector", "Unclassified"]
SDG_NAMES = {
    "SDG 1": "No poverty", "SDG 2": "Zero hunger", "SDG 3": "Good health and well-being", "SDG 4": "Quality education",
    "SDG 5": "Gender equality", "SDG 6": "Clean water and sanitation", "SDG 7": "Affordable and clean energy",
    "SDG 8": "Decent work and economic growth", "SDG 9": "Industry, innovation and infrastructure",
    "SDG 10": "Reduced inequalities", "SDG 11": "Sustainable cities and communities",
    "SDG 12": "Responsible consumption and production", "SDG 13": "Climate action", "SDG 14": "Life below water",
    "SDG 15": "Life on land", "SDG 16": "Peace, justice and strong institutions", "SDG 17": "Partnerships for the goals",
    "General": "General budget and import support", "Humanitarian": "Emergency and humanitarian response",
    "Multisector": "Several goals at once", "Unclassified": "Sector not specified",
}


def fail(msg: str, items) -> None:
    print(f"\nSTOPPED: {msg}", file=sys.stderr)
    for i in items:
        print(f"  {i}", file=sys.stderr)
    sys.exit(1)


def read_lookup(path: Path) -> pd.DataFrame:
    with path.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if not (r[next(iter(r))] or "").lstrip().startswith("#")]
    return pd.DataFrame(rows).fillna("")


def read_china() -> tuple[pd.DataFrame, int]:
    """China's grants from AidData, shaped like the OECD rows."""
    c = pd.read_csv(CHINA, dtype=str)
    c = c[(c["Recommended For Aggregates"] == "Yes") & (c["Flow Type Simplified"] == "Grant")]
    c["usd"] = pd.to_numeric(c["Amount (Nominal USD)"], errors="coerce")
    unpriced = int(c["usd"].isna().sum())
    c = c[c["usd"] > 0]
    sectors = read_lookup(LOOKUPS / "aiddata_sector_sdg.csv")
    bad = sectors[~sectors["primary_sdg"].isin(GOALS)]
    if len(bad):
        fail("invalid goal in aiddata_sector_sdg.csv", bad["aiddata_sector_code"])
    missing = sorted(set(c["Sector Code"]) - set(sectors["aiddata_sector_code"]))
    if missing:
        fail("AidData sector codes not in data/lookups/aiddata_sector_sdg.csv", missing)
    c = c.merge(sectors, left_on="Sector Code", right_on="aiddata_sector_code")
    out = pd.DataFrame({
        "year": c["Commitment Year"].astype(int), "donor": "China", "group": "bilateral",
        "purpose_code": "AidData " + c["Sector Code"], "purpose": c["aiddata_sector"],
        "primary_sdg": c["primary_sdg"], "secondary_sdg": "", "commitments_usd": c["usd"].round(0),
        "disbursements_usd": 0.0, "source": "AidData GCDF 3.0",
    })
    out = out.groupby(["year", "donor", "group", "purpose_code", "purpose", "primary_sdg", "secondary_sdg", "source"], as_index=False)[["commitments_usd", "disbursements_usd"]].sum()
    out.attrs = {}
    out.attrs["grants"] = len(c)
    top = c.sort_values("usd", ascending=False).iloc[0]
    out.attrs["largest"] = {"title": top["Title"], "usd": round(top["usd"]), "year": int(top["Commitment Year"])}
    return out, unpriced


def main() -> None:
    d = pd.read_csv(SRC, dtype=str, usecols=["DONOR", "SECTOR", "MEASURE", "FLOW_TYPE", "PRICE_BASE", "TIME_PERIOD", "OBS_VALUE", "UNIT_MULT"])
    if set(d["UNIT_MULT"].dropna()) != {"6"}:
        fail("expected every value in millions (UNIT_MULT 6)", sorted(set(d["UNIT_MULT"].dropna())))
    d["usd"] = d["OBS_VALUE"].astype(float) * 1e6
    d["year"] = d["TIME_PERIOD"].astype(int)
    d = d[(d["PRICE_BASE"] == CURRENT) & (d["SECTOR"].str.len() == 5)]  # 5-digit purpose codes add up to the all-sector total

    donors = read_lookup(LOOKUPS / "crs_donor_groups.csv")
    bad = donors[~donors["group"].isin([g for g, _ in GROUPS] + ["total", "private"])]
    if len(bad):
        fail("unknown group in crs_donor_groups.csv", bad["donor_code"] + " " + bad["group"])
    missing = sorted(set(d["DONOR"]) - set(donors["donor_code"]))
    if missing:
        fail("donor codes not in data/lookups/crs_donor_groups.csv. Add a row for each", missing)
    purposes = read_lookup(LOOKUPS / "crs_purpose_sdg.csv")
    bad = purposes[~purposes["primary_sdg"].isin(GOALS) | ~purposes["secondary_sdg"].isin(GOALS + [""])]
    if len(bad):
        fail("invalid goal in crs_purpose_sdg.csv", bad["purpose_code"] + " " + bad["primary_sdg"])
    missing = sorted(set(d["SECTOR"]) - set(purposes["purpose_code"]))
    if missing:
        fail("purpose codes not in data/lookups/crs_purpose_sdg.csv. Add a row for each", missing)

    d = d.merge(donors, left_on="DONOR", right_on="donor_code").merge(purposes, left_on="SECTOR", right_on="purpose_code")
    totals = d[d["DONOR"] == "ALLD"]
    d = d[d["group"].isin([g for g, _ in GROUPS])]

    # the individual donors must add up to the OECD's own total for official donors
    for m in (GRANTS, LOANS):
        a = d[(d["MEASURE"] == m) & (d["FLOW_TYPE"] == COMMIT)]["usd"].sum()
        b = totals[(totals["MEASURE"] == m) & (totals["FLOW_TYPE"] == COMMIT)]["usd"].sum()
        if abs(a - b) > 1e5:
            fail(f"donors do not add up to the official donors total for measure {m}", [f"{a:,.0f} against {b:,.0f}"])

    g = d[d["MEASURE"] == GRANTS]
    tidy = (g.pivot_table(index=["year", "donor", "group", "purpose_code", "purpose", "primary_sdg", "secondary_sdg"],
                          columns="FLOW_TYPE", values="usd", aggfunc="sum", fill_value=0)
            .reset_index().rename(columns={COMMIT: "commitments_usd", DISB: "disbursements_usd"}))
    for c in ("commitments_usd", "disbursements_usd"):
        if c not in tidy:
            tidy[c] = 0.0
        tidy[c] = tidy[c].round(0)
    tidy["source"] = "OECD CRS"
    china, china_unpriced = read_china()
    tidy = pd.concat([tidy, china], ignore_index=True)
    tidy = tidy[(tidy["commitments_usd"] != 0) | (tidy["disbursements_usd"] != 0)].sort_values(["year", "donor", "purpose_code"])
    grp_label = dict(GROUPS)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    tidy.assign(donor_group=tidy["group"].map(grp_label)).rename(columns={"primary_sdg": "main_goal", "secondary_sdg": "second_goal"})[
        ["year", "donor", "donor_group", "purpose_code", "purpose", "main_goal", "second_goal", "commitments_usd", "disbursements_usd", "source"]
    ].to_csv(OUT_CSV, index=False)

    # compact rows for the page: one per year, donor and main goal
    rows = tidy.groupby(["year", "donor", "group", "primary_sdg", "source"], as_index=False)[["commitments_usd", "disbursements_usd"]].sum()
    full = rows[rows["year"] <= LAST_FULL_YEAR]

    # how each lender splits its concessional finance between grants and loans
    s = d[(d["FLOW_TYPE"] == COMMIT) & (d["year"].between(SHARE_FROM, LAST_FULL_YEAR)) & d["MEASURE"].isin([GRANTS, LOANS])]
    sp = s.pivot_table(index=["donor", "group"], columns="MEASURE", values="usd", aggfunc="sum", fill_value=0).reset_index()
    sp = sp[(sp.get(LOANS, 0) > 0) & ((sp.get(GRANTS, 0) + sp.get(LOANS, 0)) >= 5e6)]
    share = [{"donor": r["donor"], "group": r["group"], "grants": round(r.get(GRANTS, 0)), "loans": round(r.get(LOANS, 0))}
             for _, r in sp.sort_values(LOANS, ascending=False).iterrows()]

    yearly = d[(d["FLOW_TYPE"] == COMMIT) & d["MEASURE"].isin([GRANTS, LOANS]) & (d["year"] <= LAST_FULL_YEAR)]
    yearly = yearly.pivot_table(index="year", columns="MEASURE", values="usd", aggfunc="sum", fill_value=0)

    out = {
        "meta": {
            "title": "Who gives Maldives grants, and for what?",
            "source": "OECD Creditor Reporting System, flows to Maldives",
            "retrieved": RETRIEVED,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "first_year": int(full["year"].min()), "last_year": LAST_FULL_YEAR, "share_from": SHARE_FROM,
            "grants_committed": round(full["commitments_usd"].sum()),
            "grants_disbursed": round(full.loc[full["source"] == "OECD CRS", "disbursements_usd"].sum()),
            "china": {"committed": round(china["commitments_usd"].sum()), "grants": int(china.attrs["grants"]),
                      "unpriced": china_unpriced, "first_year": int(china["year"].min()), "last_year": int(china["year"].max()),
                      "largest": china.attrs["largest"]},
            "donors": int(full.loc[full["commitments_usd"] > 0, "donor"].nunique()),
            "later_years_left_out": sorted(int(y) for y in rows.loc[rows["year"] > LAST_FULL_YEAR, "year"].unique()),
        },
        "groups": [{"id": k, "label": v} for k, v in GROUPS],
        "goals": [{"id": k, "label": SDG_NAMES[k]} for k in GOALS],
        "rows": [{"y": int(r["year"]), "donor": r["donor"], "group": r["group"], "goal": r["primary_sdg"],
                  "c": round(r["commitments_usd"]), "d": round(r["disbursements_usd"]), "src": "aiddata" if r["source"] != "OECD CRS" else "crs"} for _, r in full.iterrows()],
        "share": share,
        "oda_by_year": [{"y": int(y), "grants": round(r.get(GRANTS, 0)), "loans": round(r.get(LOANS, 0))} for y, r in yearly.iterrows()],
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    m = out["meta"]
    print(f"China (AidData): {m['china']['grants']} grants with amounts, US$ {m['china']['committed'] / 1e6:,.1f} million, "
          f"{m['china']['first_year']} to {m['china']['last_year']}, plus {m['china']['unpriced']} without an amount")
    print(f"Grants committed {m['first_year']} to {m['last_year']}: US$ {m['grants_committed'] / 1e6:,.1f} million "
          f"(disbursed US$ {m['grants_disbursed'] / 1e6:,.1f} million) from {m['donors']} donors")
    if m["later_years_left_out"]:
        print("Left out as incomplete:", ", ".join(map(str, m["later_years_left_out"])))
    by_goal = full.groupby("primary_sdg")["commitments_usd"].sum().sort_values(ascending=False) / 1e6
    print("\nBy main goal, US$ million\n" + by_goal.round(1).to_string())
    print(f"\nGrant share of concessional commitments, {SHARE_FROM} to {LAST_FULL_YEAR}")
    for r in share:
        print(f"  {r['donor'][:34]:34} {r['grants'] / (r['grants'] + r['loans']) * 100:5.0f}%  of US$ {(r['grants'] + r['loans']) / 1e6:,.0f}m")


if __name__ == "__main__":
    main()
