"""
Pulls Maldives public debt series from the MMA Statistics Database
and writes data.json for the debt clock page.

Runs in GitHub Actions. The API token comes from the MMA_TOKEN secret,
so it never appears in the public repo or the website.
"""
import json
import os
import sys
from datetime import datetime, timezone

import requests
import urllib3

urllib3.disable_warnings()  # MMA's own sample code uses verify=False

TOKEN = os.environ.get("MMA_TOKEN")
if not TOKEN:
    sys.exit("MMA_TOKEN is not set. Add it as a repository secret.")

SERIES = {
    4514: "total",            # Public & publicly guaranteed debt, MVR
    4515: "domestic",
    4516: "domestic_cg",
    4517: "domestic_guaranteed",
    4518: "external",
    4519: "external_cg",
    4520: "external_guaranteed",
    4522: "debt_to_gdp",      # percent
    79:   "population",
    4039: "usd_rate",         # MVR per USD
    5226: "ext_interest_q",   # quarterly external interest paid, USD
    4523: "domestic_to_gdp",  # ratio
    4526: "external_to_gdp",  # ratio
    38:   "gdp",              # nominal GDP, MVR, annual
    # monthly government finances, MVR
    1999: "revenue",          # total revenue and grants
    2000: "tax_revenue",
    2034: "expenditure",      # recurrent + capital
    2035: "recurrent_exp",
    2057: "capital_exp",
    2036: "salaries_pensions",
    2049: "interest_costs",   # financing and interest costs
    2050: "subsidies",        # grants, contributions and subsidies
    # prices, for inflation adjustment
    280:  "cpi",              # national consumer price index, monthly
    # fuel imports, US dollars, monthly (Maldives Customs Service)
    3486: "imports_goods",    # all goods imports
    3503: "fuel_imports",     # petroleum products
    3504: "fuel_petrol",
    3505: "fuel_diesel",      # diesel (marine gas oil)
    3507: "fuel_other",
    3787: "crude_price",      # World Bank average of Brent, Dubai and WTI, US$ per barrel
}

URL = "https://database.mma.gov.mv/api/series"


def fetch(ids):
    out, page = [], 1
    while True:
        r = requests.get(
            URL,
            params={"ids": ",".join(map(str, ids)), "page": page},
            headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
            verify=False,
            timeout=60,
        )
        r.raise_for_status()
        body = r.json()
        out.extend(body.get("data", []))
        meta = body.get("meta", {})
        if meta.get("current_page", 1) >= meta.get("last_page", 1):
            return out
        page += 1


def main():
    raw = fetch(list(SERIES))
    series = {}
    for s in raw:
        key = SERIES.get(s["id"])
        if not key:
            continue
        points = sorted(
            [{"date": p["date"], "value": p["amount"]} for p in s.get("data", []) if p.get("amount") is not None],
            key=lambda p: p["date"],
        )
        series[key] = {
            "id": s["id"],
            "name": s.get("name"),
            "unit": s.get("unit"),
            "frequency": s.get("frequency"),
            "last_updated_at": s.get("last_updated_at"),
            "notes": s.get("description") or s.get("definition"),
            "points": points,
        }

    # If the API leaves a series out (or returns it empty), keep the values from the
    # previous run rather than losing that part of the site.
    previous = {}
    if os.path.exists("data.json"):
        try:
            with open("data.json") as f:
                previous = json.load(f).get("series", {})
        except (OSError, ValueError):
            previous = {}
    carried = []
    for key in SERIES.values():
        if (key not in series or not series[key]["points"]) and previous.get(key, {}).get("points"):
            series[key] = previous[key]
            carried.append(key)
    missing = [k for k in SERIES.values() if k not in series or not series[k]["points"]]
    if "total" in missing:
        sys.exit(f"Core series missing and no previous copy: {missing}")
    if carried:
        print(f"Warning: kept previous values for {carried}")
    if missing:
        print(f"Warning: no data at all for {missing}")

    with open("data.json", "w") as f:
        json.dump(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "carried_over": carried,
                "series": series,
            },
            f,
            indent=1,
        )
    t = series["total"]["points"][-1]
    print(f"OK. Latest total debt: MVR {t['value']:,.0f} at {t['date']}")


if __name__ == "__main__":
    main()
