"""
Builds the "What is under way now" list on maldives-grants.html from IATI.

Reads the current activities for Maldives exported from d-portal
(data/raw/iati_dportal_current_activities.csv, the "Present" list at
https://d-portal.iatistandard.org/ctrack.html?country_code=MV).

IATI mixes grants, loans, trade finance and private investment, and overlaps
with the OECD and Ministry of Finance figures, so this list is shown on its own
and never added to the totals on either page.

  data/lookups/iati_orgs.csv             short names and groups for reporting organisations
  data/lookups/iati_activity_kinds.csv   rules marking trade finance and private investment

  data/maldives_iati.json                what the page reads

    python scripts/build_maldives_iati.py
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "iati_dportal_current_activities.csv"
LOOKUPS = ROOT / "data" / "lookups"
OUT = ROOT / "data" / "maldives_iati.json"
EXPORTED = "2026-10-13"
GROUPS = {"bilateral", "multilateral", "un", "other"}
KINDS = {"project", "trade_finance", "private_investment"}
STATUS = {"1": "Pipeline", "2": "Under way", "3": "Finishing", "4": "Closed", "5": "Cancelled", "6": "Suspended"}


def fail(msg: str, items) -> None:
    print(f"\nSTOPPED: {msg}", file=sys.stderr)
    for i in items:
        print(f"  {i}", file=sys.stderr)
    sys.exit(1)


def read_lookup(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if not (r[next(iter(r))] or "").lstrip().startswith("#")]


def money(v) -> float:
    return float(str(v).replace(",", "") or 0) if str(v).strip() not in ("", "nan") else 0.0


def main() -> None:
    d = pd.read_csv(SRC, dtype=str).fillna("")
    if set(d["currency"]) - {"USD"}:
        fail("expected every amount in US dollars", sorted(set(d["currency"]) - {"USD"}))

    orgs = {r["reporting_org"]: r for r in read_lookup(LOOKUPS / "iati_orgs.csv")}
    bad = [k for k, r in orgs.items() if r["group"] not in GROUPS]
    if bad:
        fail("unknown group in iati_orgs.csv", bad)
    missing = sorted(set(d["reporting-org"]) - orgs.keys())
    if missing:
        fail("reporting organisations not in data/lookups/iati_orgs.csv. Add a row for each", missing)
    rules = read_lookup(LOOKUPS / "iati_activity_kinds.csv")
    bad = [r["pattern"] for r in rules if r["kind"] not in KINDS or r["field"] not in ("reporting_org", "title")]
    if bad:
        fail("invalid row in iati_activity_kinds.csv", bad)

    acts = []
    for _, r in d.iterrows():
        kind = "project"
        for rule in rules:
            text = r["reporting-org"] if rule["field"] == "reporting_org" else r["title"]
            if re.search(rule["pattern"], text, re.I):
                kind = rule["kind"]
                break
        o = orgs[r["reporting-org"]]
        acts.append({
            "id": r["iati-identifier"], "title": re.sub(r"\s+", " ", r["title"]).strip(),
            "org": o["organisation"], "group": o["group"], "kind": kind,
            "c": round(money(r["total-commitment"])), "s": round(money(r["total-spend"])),
            "status": STATUS.get(r["activity-status"], ""), "link": r["link"],
        })
    acts.sort(key=lambda a: (a["kind"] != "project", -a["c"]))

    out = {"meta": {"source": "IATI, through d-portal", "exported": EXPORTED,
                    "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "activities": len(acts)},
           "activities": acts}
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    df = pd.DataFrame(acts)
    print(f"{len(acts)} current activities from {df['org'].nunique()} organisations")
    print(df.groupby("kind").agg(n=("id", "size"), committed_m=("c", lambda s: round(s.sum() / 1e6, 1))).to_string())
    p = df[df["kind"] == "project"]
    print("\nDevelopment projects by group\n" + p.groupby("group").size().to_string())


if __name__ == "__main__":
    main()
