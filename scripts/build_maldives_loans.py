"""
Builds the data for maldives-loans.html: who lends to Maldives, and for what?

Reads the Ministry of Finance register of active external borrowings
(data/raw/active_external_loans_ministry_of_finance.xlsx, as at 30 June 2026),
cleans it, converts each committed amount to US dollars at 30 June 2026 rates,
classifies each creditor and tags each loan to Sustainable Development Goals.

  data/lookups/creditor_categories.csv   creditor name patterns and categories (edit by hand)
  data/lookups/sdg_rules.csv             project name keywords and goals (edit by hand)

  data/processed/loans_clean.csv         the cleaned register
  data/processed/sdg_tags.csv            one tag per loan, with rule_used and confidence.
                                         Fill in manual_primary / manual_secondary to
                                         override the rules; they are kept on every rerun.
                                         Write "none" in manual_secondary to clear it.
  data/processed/sdg_review.csv          low-confidence and untagged loans to check by hand
  data/processed/loans_tagged.csv        the tagged dataset offered for download on the page
  data/maldives_loans.json               what the page reads

    python scripts/build_maldives_loans.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "raw" / "active_external_loans_ministry_of_finance.xlsx"
LOOKUPS = ROOT / "data" / "lookups"
PROC = ROOT / "data" / "processed"
OUT_JSON = ROOT / "data" / "maldives_loans.json"
AS_OF = "2026-06-30"
HEADER_ROW = 3

# Exchange rates at 30 June 2026, as US dollars per one unit of each currency.
# ECB rates are euro reference rates (Official Journal C/2026/2951) crossed through
# EUR/USD 1.1394. SAR and AED are fixed pegs. Change a number here and rerun.
ECB_PER_EUR = {"USD": 1.1394, "JPY": 185.08, "CNY": 7.7314, "GBP": 0.86178, "INR": 107.8565}
FX_TO_USD = {
    # code: (US dollars per unit, source, checked against an official source)
    "USD": (1.0, "US dollar", True),
    "XDR": (1.3561, "IMF, US dollars per SDR, 30 Jun 2026", True),
    "EUR": (ECB_PER_EUR["USD"], "ECB reference rate, 30 Jun 2026", True),
    "JPY": (ECB_PER_EUR["USD"] / ECB_PER_EUR["JPY"], "ECB reference rates, EUR/USD over EUR/JPY, 30 Jun 2026", True),
    "CNY": (ECB_PER_EUR["USD"] / ECB_PER_EUR["CNY"], "ECB reference rates, EUR/USD over EUR/CNY, 30 Jun 2026", True),
    "GBP": (ECB_PER_EUR["USD"] / ECB_PER_EUR["GBP"], "ECB reference rates, EUR/USD over EUR/GBP, 30 Jun 2026", True),
    "INR": (ECB_PER_EUR["USD"] / ECB_PER_EUR["INR"], "ECB reference rates, EUR/USD over EUR/INR, 30 Jun 2026", True),
    "SAR": (1 / 3.75, "Fixed peg, 3.75 riyals per US dollar", True),
    "AED": (1 / 3.6725, "Fixed peg, 3.6725 dirhams per US dollar", True),
    "KWD": (3.228, "Market rate near 30 Jun 2026", False),  # not yet checked against the Central Bank of Kuwait
}
# spellings seen in registers, mapped to ISO codes
CURRENCY_ALIASES = {
    "US$": "USD", "US DOLLAR": "USD", "US DOLLARS": "USD", "DOLLAR": "USD",
    "SDR": "XDR", "SDRS": "XDR",
    "EURO": "EUR", "EUROS": "EUR",
    "KD": "KWD", "KUWAITI DINAR": "KWD",
    "SR": "SAR", "SAUDI RIYAL": "SAR", "SRL": "SAR",
    "DH": "AED", "DHS": "AED", "UAE DIRHAM": "AED", "DIRHAM": "AED",
    "RMB": "CNY", "YUAN": "CNY", "RENMINBI": "CNY",
    "YEN": "JPY", "JPN": "JPY",
    "RS": "INR", "INDIAN RUPEE": "INR",
    "STG": "GBP", "POUND": "GBP",
}

CATEGORIES = [
    ("multilateral", "Multilateral"),
    ("bilateral", "Bilateral"),
    ("export_credit", "Export credit"),
    ("commercial", "Commercial"),
]
SDGS = [
    ("SDG 1", "No poverty"), ("SDG 2", "Zero hunger"), ("SDG 3", "Good health and well-being"),
    ("SDG 4", "Quality education"), ("SDG 5", "Gender equality"), ("SDG 6", "Clean water and sanitation"),
    ("SDG 7", "Affordable and clean energy"), ("SDG 8", "Decent work and economic growth"),
    ("SDG 9", "Industry, innovation and infrastructure"), ("SDG 10", "Reduced inequalities"),
    ("SDG 11", "Sustainable cities and communities"), ("SDG 12", "Responsible consumption and production"),
    ("SDG 13", "Climate action"), ("SDG 14", "Life below water"), ("SDG 15", "Life on land"),
    ("SDG 16", "Peace, justice and strong institutions"), ("SDG 17", "Partnerships for the goals"),
    ("General", "General budget and balance of payments support"),
    ("Unclassified", "Not enough detail in the project name"),
]
GOALS = {g for g, _ in SDGS}
CONF_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}


def fail(msg: str, items: list[str]) -> None:
    print(f"\nSTOPPED: {msg}", file=sys.stderr)
    for i in items:
        print(f"  {i}", file=sys.stderr)
    sys.exit(1)


def read_lookup(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if not (r[next(iter(r))] or "").lstrip().startswith("#")]


# ---------- reading the register ----------

def parse_date(v) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)) and 1000 < v < 80000:  # Excel serial day
        return (datetime(1899, 12, 30) + timedelta(days=float(v))).date()
    s = str(v).strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y.%m.%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_amount(v) -> float | None:
    if isinstance(v, (int, float)):
        return float(v)
    if v is None:
        return None
    s = re.sub(r"[,\s]", "", str(v))
    try:
        return float(s)
    except ValueError:
        return None


def norm_currency(v) -> str:
    s = re.sub(r"\s+", " ", str(v or "").strip().upper())
    return CURRENCY_ALIASES.get(s, s)


def read_register() -> list[dict]:
    if not SRC.exists():
        fail("the register is missing", [str(SRC.relative_to(ROOT))])
    wb = openpyxl.load_workbook(SRC, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    head = [re.sub(r"\s+", " ", str(h or "")).strip().lower() for h in rows[HEADER_ROW - 1]]
    want = {"no": "#", "date": "loan date", "creditor": "creditor", "project": "project",
            "currency": "currency", "amount": "amount", "status": "implementation status"}
    col = {}
    for k, name in want.items():
        hits = [i for i, h in enumerate(head) if h == name] or [i for i, h in enumerate(head) if h.startswith(name)]
        if not hits:
            fail(f"column '{name}' not found on row {HEADER_ROW}", [repr(h) for h in head])
        col[k] = hits[0]

    out, problems = [], []
    for r_i, r in enumerate(rows[HEADER_ROW:], start=HEADER_ROW + 1):
        get = lambda k: r[col[k]] if col[k] < len(r) else None
        creditor = str(get("creditor") or "").strip()
        no = get("no")
        if not creditor or not isinstance(no, (int, float)) and not str(no or "").strip().isdigit():
            continue  # blank, subtotal or note rows
        d, amt = parse_date(get("date")), parse_amount(get("amount"))
        cur = norm_currency(get("currency"))
        if d is None:
            problems.append(f"row {r_i}: date {get('date')!r} not understood")
        if amt is None:
            problems.append(f"row {r_i}: amount {get('amount')!r} not understood")
        out.append({
            "row": r_i, "no": int(float(no)), "date": d, "creditor_raw": re.sub(r"\s+", " ", creditor),
            "project": re.sub(r"\s+", " ", str(get("project") or "").strip()),
            "currency": cur, "amount": amt, "status": str(get("status") or "").strip(),
        })
    if problems:
        fail("some rows could not be read", problems)
    return out


def loan_key(r: dict) -> str:
    raw = f"{r['date']}|{r['creditor_raw'].lower()}|{r['project'].lower()}|{r['currency']}|{r['amount']:.2f}"
    return hashlib.sha1(raw.encode()).hexdigest()[:10]


# ---------- creditors ----------

def classify_creditors(loans: list[dict]) -> list[str]:
    rules = read_lookup(LOOKUPS / "creditor_categories.csv")
    valid = {c for c, _ in CATEGORIES}
    bad = [f"{r['pattern']} -> {r['category']}" for r in rules if r["category"] not in valid]
    if bad:
        fail("unknown category in creditor_categories.csv", bad)
    compiled = [(re.compile(r["pattern"], re.I), r) for r in rules]
    unmatched, check = set(), set()
    for l in loans:
        hit = next((r for p, r in compiled if p.search(l["creditor_raw"])), None)
        if hit is None:
            unmatched.add(l["creditor_raw"])
            continue
        l["creditor"], l["category"] = hit["creditor"], hit["category"]
        if "check" in (hit.get("note") or "").lower():
            check.add(f"{l['creditor_raw']}  ->  {hit['creditor']} ({hit['category']})")
    if unmatched:
        fail("creditors not in data/lookups/creditor_categories.csv. Add a row for each", sorted(unmatched))
    return sorted(check)


# ---------- SDG tags ----------

def rule_tags(project: str, rules: list[tuple]) -> dict:
    hits = []
    for pat, r in rules:
        m = pat.search(project)
        if m:
            hits.append((int(r["tier"]), m.start(), r))
    if not hits:
        return {"rule_primary": "Unclassified", "rule_secondary": "", "rule_used": "no keyword matched", "confidence": "none"}
    hits.sort(key=lambda h: (h[0], h[1]))
    tier, _, best = hits[0]
    primary, secondary, conf = best["primary_sdg"], best["secondary_sdg"], best["confidence"]
    used = [best["rule"]]
    others = [h for h in hits[1:] if h[2]["primary_sdg"] != primary]
    if others:
        o = others[0][2]
        if not secondary:
            secondary = o["primary_sdg"]
        used.append(f"also {o['rule']}")
        if others[0][0] == tier and conf == "high":
            conf = "medium"  # two different goals named with equal weight
    if primary == "General":
        secondary = "" if secondary == "General" else secondary
    return {"rule_primary": primary, "rule_secondary": secondary if secondary != primary else "",
            "rule_used": "; ".join(used), "confidence": conf}


def tag_loans(loans: list[dict]) -> None:
    raw_rules = read_lookup(LOOKUPS / "sdg_rules.csv")
    bad = [f"{r['rule']}: {r['primary_sdg']!r} / {r['secondary_sdg']!r}" for r in raw_rules
           if r["primary_sdg"] not in GOALS or (r["secondary_sdg"] and r["secondary_sdg"] not in GOALS)
           or r["confidence"] not in CONF_ORDER]
    if bad:
        fail("invalid goal or confidence in sdg_rules.csv", bad)
    rules = [(re.compile(r["pattern"], re.I), r) for r in raw_rules]

    # keep manual corrections from the previous run
    manual = {}
    tag_file = PROC / "sdg_tags.csv"
    if tag_file.exists():
        with tag_file.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if any((r.get(k) or "").strip() for k in ("manual_primary", "manual_secondary", "manual_note")):
                    manual[r["loan_key"]] = {k: (r.get(k) or "").strip() for k in ("manual_primary", "manual_secondary", "manual_note")}
    bad = [f"{k}: {v['manual_primary']!r} / {v['manual_secondary']!r}" for k, v in manual.items()
           if (v["manual_primary"] and v["manual_primary"] not in GOALS)
           or (v["manual_secondary"] and v["manual_secondary"].lower() != "none" and v["manual_secondary"] not in GOALS)]
    if bad:
        fail("manual tags in sdg_tags.csv must be written like 'SDG 6' or 'General'", bad)
    keys = {l["key"] for l in loans}
    lost = [k for k in manual if k not in keys]
    if lost:
        print(f"Note: {len(lost)} manual tag(s) belong to loans no longer in the register: {', '.join(lost)}")

    for l in loans:
        l.update(rule_tags(l["project"], rules))
        m = manual.get(l["key"], {})
        l["manual_primary"] = m.get("manual_primary", "")
        l["manual_secondary"] = m.get("manual_secondary", "")
        l["manual_note"] = m.get("manual_note", "")
        l["sdg"] = l["manual_primary"] or l["rule_primary"]
        if l["manual_secondary"]:
            l["sdg2"] = "" if l["manual_secondary"].lower() == "none" else l["manual_secondary"]
        else:
            l["sdg2"] = "" if l["manual_primary"] else l["rule_secondary"]
        if l["sdg2"] == l["sdg"]:
            l["sdg2"] = ""
        l["tag_source"] = "manual" if (l["manual_primary"] or l["manual_secondary"]) else "rule"


# ---------- writing ----------

def write_csv(path: Path, rows: list[dict], cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    loans = read_register()

    missing = sorted({l["currency"] for l in loans} - FX_TO_USD.keys())
    if missing:
        fail("no exchange rate for these currencies. Add them to FX_TO_USD", missing)

    seen = {}
    for l in loans:
        k = loan_key(l)
        seen[k] = seen.get(k, 0) + 1
        l["key"] = k if seen[k] == 1 else f"{k}-{seen[k]}"
        l["fx"] = FX_TO_USD[l["currency"]][0]
        l["usd"] = round(l["amount"] * l["fx"], 2)
        l["loan_date"] = l["date"].isoformat()
        l["year"] = l["date"].year

    check = classify_creditors(loans)
    tag_loans(loans)
    loans.sort(key=lambda l: (l["date"], l["no"]))

    clean_cols = ["key", "no", "loan_date", "year", "creditor_raw", "creditor", "category", "project", "currency", "amount", "fx", "usd", "status"]
    write_csv(PROC / "loans_clean.csv", [{c: l[c] for c in clean_cols} for l in loans], clean_cols)

    tag_cols = ["loan_key", "no", "loan_date", "creditor", "project", "usd", "rule_primary", "rule_secondary", "rule_used",
                "confidence", "manual_primary", "manual_secondary", "manual_note", "final_primary", "final_secondary", "tag_source"]
    tag_rows = [{**l, "loan_key": l["key"], "final_primary": l["sdg"], "final_secondary": l["sdg2"]} for l in loans]
    write_csv(PROC / "sdg_tags.csv", tag_rows, tag_cols)

    review = [r for r in tag_rows if r["tag_source"] == "rule" and r["confidence"] in ("low", "none")]
    review.sort(key=lambda r: (-CONF_ORDER[r["confidence"]], -float(r["usd"])))
    write_csv(PROC / "sdg_review.csv", review, ["loan_key", "no", "loan_date", "creditor", "project", "usd",
                                                "rule_primary", "rule_secondary", "rule_used", "confidence"])

    cat_label = dict(CATEGORIES)
    dl_cols = ["loan_date", "creditor_as_registered", "creditor", "creditor_category", "project", "currency",
               "amount_committed", "usd_per_unit_30jun2026", "amount_usd", "primary_sdg", "secondary_sdg",
               "tag_confidence", "tag_source", "implementation_status"]
    write_csv(PROC / "loans_tagged.csv", [{
        "loan_date": l["loan_date"], "creditor_as_registered": l["creditor_raw"], "creditor": l["creditor"],
        "creditor_category": cat_label[l["category"]], "project": l["project"], "currency": l["currency"],
        "amount_committed": l["amount"], "usd_per_unit_30jun2026": round(l["fx"], 8), "amount_usd": l["usd"],
        "primary_sdg": l["sdg"], "secondary_sdg": l["sdg2"],
        "tag_confidence": "manual" if l["tag_source"] == "manual" else l["confidence"],
        "tag_source": l["tag_source"], "implementation_status": l["status"],
    } for l in loans], dl_cols)

    out = {
        "meta": {
            "title": "Who lends to Maldives, and for what?",
            "source": "Ministry of Finance, Maldives. Active External Borrowings",
            "as_of": AS_OF,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "loans": len(loans),
            "total_usd": round(sum(l["usd"] for l in loans), 2),
            "first_year": min(l["year"] for l in loans),
            "last_year": max(l["year"] for l in loans),
            "manual_tags": sum(l["tag_source"] == "manual" for l in loans),
            "confidence": {c: sum(l["tag_source"] == "rule" and l["confidence"] == c for l in loans) for c in CONF_ORDER},
            "fx": [{"currency": c, "usd_per_unit": round(v[0], 8), "source": v[1], "checked": v[2],
                    "loans": sum(l["currency"] == c for l in loans)}
                   for c, v in FX_TO_USD.items() if any(l["currency"] == c for l in loans)],
        },
        "categories": [{"id": c, "label": lab} for c, lab in CATEGORIES],
        "sdgs": [{"id": g, "label": lab} for g, lab in SDGS],
        "loans": [{
            "date": l["loan_date"], "year": l["year"], "creditor": l["creditor"], "creditor_raw": l["creditor_raw"],
            "category": l["category"], "project": l["project"], "currency": l["currency"], "amount": l["amount"],
            "usd": l["usd"], "sdg": l["sdg"], "sdg2": l["sdg2"],
            "conf": "manual" if l["tag_source"] == "manual" else l["confidence"], "status": l["status"],
        } for l in loans],
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ---------- report ----------
    print(f"{len(loans)} loans, {out['meta']['first_year']} to {out['meta']['last_year']}, "
          f"US$ {out['meta']['total_usd'] / 1e6:,.1f} million committed at 30 Jun 2026 rates")
    print("Currencies:", ", ".join(f"{f['currency']} {f['loans']}" for f in out["meta"]["fx"]))
    unchecked = [f["currency"] for f in out["meta"]["fx"] if not f["checked"]]
    if unchecked:
        print("Rates still to check:", ", ".join(unchecked))
    if check:
        print("\nCreditors matched only by a catch-all row (check these):")
        for c in check:
            print("  " + c)
    conf = out["meta"]["confidence"]
    print(f"\nTags from rules: high {conf['high']}, medium {conf['medium']}, low {conf['low']}, none {conf['none']}. "
          f"Manual: {out['meta']['manual_tags']}")
    print(f"For review: {len(review)} loans in {(PROC / 'sdg_review.csv').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
