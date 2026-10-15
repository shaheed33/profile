"""Build the State Budget Resilience Monitor data from the curated budget figures.

Input:  data/raw/state_budgets_2026-27.json
        Figures copied from each jurisdiction's 2026-27 budget papers, general
        government sector, with the table and PDF page for every line. Values
        printed in $'000 were converted to $ million when recorded.

Output: data/state_budget.json  full dataset with sources and checks
        data/state_budget.js    the same, as window.STATE_BUDGET for the page
        data/state_budget.csv   long table: one row per jurisdiction, item, year

The build stops with an error if any accounting check fails, so a typo in the
raw file cannot reach the website.

    python scripts/build_state_budget.py
    python scripts/build_state_budget.py --out-dir /tmp/check   # leave published data alone
"""
import argparse
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "state_budgets_2026-27.json"

ITEMS = [
    # key, label used in the CSV
    ("revenue", "Total revenue"),
    ("taxation", "Taxation revenue"),
    ("payroll_tax", "Payroll tax"),
    ("transfer_duty", "Transfer (stamp) duty on property"),
    ("grants", "Grant revenue"),
    ("gst", "GST revenue"),
    ("royalties", "Mining and petroleum royalties"),
    ("expenses", "Total expenses"),
    ("employee", "Employee and superannuation expenses"),
    ("interest", "Interest expense"),
    ("nob", "Net operating balance"),
    ("capex", "Purchases of non-financial assets"),
    ("net_debt", "Net debt (30 June)"),
]
DERIVED_SIGNS = {"net_debt_parts": lambda name: -1 if name.startswith("less") else 1}


class CheckFailed(Exception):
    pass


def combine(parts, sign=lambda name: 1):
    """Add component lines year by year. A missing component makes the year missing."""
    names = list(parts)
    years = len(parts[names[0]]["values"])
    out = []
    for i in range(years):
        vals = [parts[n]["values"][i] for n in names]
        out.append(None if any(v is None for v in vals) else round(sum(sign(n) * v for n, v in zip(names, vals)), 3))
    sources = "; ".join(f"{n}: {p['table']}" + (f" (PDF p. {p['pdf_page']})" if p.get("pdf_page") else "") for n, p in parts.items())
    return {"values": out, "table": "Sum of components", "components": sources}


def resolve(items):
    """Turn the recorded lines (some split into components) into one series per item."""
    series = {}
    for key, _ in ITEMS:
        if key in items:
            series[key] = items[key]
        elif f"{key}_parts" in items:
            series[key] = combine(items[f"{key}_parts"], DERIVED_SIGNS.get(f"{key}_parts", lambda n: 1))
        else:
            raise CheckFailed(f"missing item {key}")
    return series


def close(a, b, tol):
    return abs(a - b) <= tol


def check(j, s, years):
    """Accounting checks. Rounded published figures may differ by a few million."""
    problems = []
    for i, year in enumerate(years):
        v = {k: s[k]["values"][i] for k in s}
        if any(v[k] is None for k in v if k != "capex"):
            problems.append(f"{year}: a required figure is missing")
            continue
        tol = max(3.0, abs(v["revenue"]) * 0.0005)
        if not close(v["revenue"] - v["expenses"], v["nob"], tol):
            problems.append(f"{year}: revenue less expenses ({v['revenue'] - v['expenses']:.1f}) does not equal the net operating balance ({v['nob']:.1f})")
        for part, whole in [("gst", "grants"), ("payroll_tax", "taxation"), ("transfer_duty", "taxation"),
                            ("taxation", "revenue"), ("grants", "revenue"), ("royalties", "revenue"),
                            ("employee", "expenses"), ("interest", "expenses")]:
            # NT payroll and property taxes are published on a slightly wider basis, so allow 2%.
            slack = 1.02 if j["id"] == "nt" else 1.0005
            if v[part] < 0 or v[part] > v[whole] * slack + 1:
                problems.append(f"{year}: {part} ({v[part]}) is outside 0 to {whole} ({v[whole]})")
        if v["payroll_tax"] + v["transfer_duty"] > v["taxation"] * 1.02:
            problems.append(f"{year}: payroll tax plus transfer duty exceeds total taxation")
        if v["revenue"] <= 0 or v["expenses"] <= 0:
            problems.append(f"{year}: revenue and expenses must be positive")
        if v["capex"] is not None and v["capex"] < 0:
            problems.append(f"{year}: capital purchases are negative")
    budget_years = [i for i, y in enumerate(years) if y != years[0]]
    if any(s["capex"]["values"][i] is None for i in budget_years):
        problems.append("capital purchases are missing for a budget or forward-estimate year")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--raw", type=pathlib.Path, default=RAW, help="curated figures (JSON)")
    ap.add_argument("--out-dir", type=pathlib.Path, default=ROOT / "data", help="where to write the outputs")
    args = ap.parse_args(argv)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = json.loads(args.raw.read_text(encoding="utf-8"))
    years = raw["years"]
    out = {"meta": {k: raw[k] for k in ("years", "currency", "unit", "sector", "budget_round")}, "jurisdictions": []}
    rows = []
    failures = []
    for j in raw["jurisdictions"]:
        series = resolve(j["items"])
        problems = check(j, series, years)
        if problems:
            failures.extend(f"{j['short']}: {p}" for p in problems)
        record = {k: j[k] for k in ("id", "name", "short", "kind", "document", "first_year_label")}
        record["series"] = {k: series[k]["values"] for k, _ in ITEMS}
        record["sources"] = {k: {x: series[k][x] for x in ("table", "pdf_page", "note", "components", "file") if x in series[k]} for k, _ in ITEMS}
        if "own_net_debt" in j["items"]:
            record["own_net_debt"] = {"values": j["items"]["own_net_debt"]["values"], **{x: j["items"]["own_net_debt"][x] for x in ("table", "note")}}
        out["jurisdictions"].append(record)
        for key, label in ITEMS:
            for year, value in zip(years, series[key]["values"]):
                src = series[key]
                where = src.get("components") or (src["table"] + (f" (PDF p. {src['pdf_page']})" if src.get("pdf_page") else ""))
                rows.append([j["name"], key, label, year, "" if value is None else value, j["document"]["title"], where])
    if failures:
        print("Data checks failed:\n  " + "\n  ".join(failures), file=sys.stderr)
        sys.exit(1)
    out["meta"]["checks"] = ("For every jurisdiction and year: revenue less expenses equals the net operating balance "
                             "within rounding; each revenue component is no larger than its total; employee and interest "
                             "expenses are no larger than total expenses.")
    (out_dir / "state_budget.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "state_budget.js").write_text(
        "// Built by scripts/build_state_budget.py from data/raw/state_budgets_2026-27.json. Do not edit by hand.\n"
        "window.STATE_BUDGET = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    with open(out_dir / "state_budget.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["jurisdiction", "item", "item_label", "financial_year", "value_aud_million", "budget_paper", "source_table"])
        w.writerows(rows)
    print(f"Built {len(out['jurisdictions'])} jurisdictions, {len(rows)} figures. All checks passed.")


if __name__ == "__main__":
    try:
        main()
    except CheckFailed as e:
        print(f"Data error: {e}", file=sys.stderr)
        sys.exit(1)
