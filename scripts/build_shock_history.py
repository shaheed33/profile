"""Size the stress-test shocks from history, so they are evidence rather than guesses.

Reads official history saved in data/raw/history/:
  abs_5506_taxation_2014-15.xls   ABS Taxation Revenue, Australia, 2014-15 (years 2005-06 to 2014-15)
  abs_5506_taxation_2024-25.xlsx  ABS Taxation Revenue, Australia, 2024-25 (years 2015-16 to 2024-25)
  abs_5512_gfs_2024-25_DO0nn.xlsx ABS Government Finance Statistics, state general government (2015-16 to 2024-25)
  abs_wpi_public_sector_index.csv ABS Wage Price Index, public sector, by state (quarterly index, filtered from
                                  https://data.api.abs.gov.au/rest/data/ABS,WPI/all ; total hourly rates excluding bonuses, original)
  rba_f2.1_government_bond_yields.csv  RBA F2.1, 10-year Australian Government bond yield, monthly

For each state and each revenue line it measures, year by year, how far growth fell short of that
line's normal (median) growth:  shortfall = (1 + growth) / (1 + median growth) - 1.
A budget assumes roughly normal growth, so the shortfall is how far a repeat of that year would leave
revenue below the budget. "Worst year" is the largest shortfall on record; "bad year" is the 20th
percentile, a year as bad as roughly one year in five; "good year" is the 80th percentile, a year as
good as roughly one in five. Wages and interest rates use the excess over
their median change, in percentage points.

Writes data/shock_history.json and data/shock_history.js.

    python scripts/build_shock_history.py
"""
import csv
import json
import pathlib
import statistics
import sys

import openpyxl
import xlrd

ROOT = pathlib.Path(__file__).resolve().parent.parent
H = ROOT / "data" / "raw" / "history"

STATES = [  # id, ABS name, 5506 table number (both releases), GFS workbook
    ("nsw", "New South Wales", 2, "003"), ("vic", "Victoria", 3, "004"), ("qld", "Queensland", 4, "005"),
    ("sa", "South Australia", 5, "006"), ("wa", "Western Australia", 6, "007"), ("tas", "Tasmania", 7, "008"),
    ("nt", "Northern Territory", 8, "009"), ("act", "Australian Capital Territory", 9, "010"),
]
PAYROLL = ("taxes on employers", "employers' payroll taxes")  # label differs between releases
CONVEY = "stamp duties on conveyances"


def norm(s):
    return " ".join(str(s).replace("’", "'").split()).lower()


def rows_xls(path, sheet):
    sh = xlrd.open_workbook(path).sheet_by_name(sheet)
    return [sh.row_values(i) for i in range(sh.nrows)]


def rows_xlsx(path, sheet):
    return [list(r) for r in openpyxl.load_workbook(path, read_only=True, data_only=True)[sheet].iter_rows(values_only=True)]


def table_series(rows, label_start):
    """Years from the header row and the values of the first row whose label starts with label_start."""
    years = None
    for r in rows:
        cells = [c for c in r if c not in (None, "")]
        if years is None and cells and all(isinstance(c, str) and len(c) == 7 and c[4] == "-" for c in cells) and len(cells) >= 5:
            years = cells
            continue
        starts = label_start if isinstance(label_start, tuple) else (label_start,)
        if years and len(cells) > 1 and isinstance(cells[0], str) and norm(cells[0]).startswith(starts):
            vals = [float(v) for v in cells[1:1 + len(years)]]
            if len(vals) != len(years):
                raise ValueError(f"row {label_start!r} has {len(vals)} values for {len(years)} years")
            return dict(zip(years, vals))
    raise ValueError(f"row starting {label_start!r} not found")


def splice(old, new):
    out = dict(old)
    out.update(new)
    return dict(sorted(out.items()))


def growth(series):
    ys = sorted(series)
    return {b: series[b] / series[a] - 1 for a, b in zip(ys, ys[1:]) if series[a] > 0 and series[b] >= 0}


def percentile(values, q):
    v = sorted(values)
    pos = (len(v) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (pos - lo)


def revenue_measure(series, source):
    g = growth(series)
    m = statistics.median(g.values())
    short = {y: (1 + v) / (1 + m) - 1 for y, v in g.items()}
    worst_year = min(short, key=short.get)
    return {
        "unit": "share", "source": source,
        "years": [min(series), max(series)], "observations": len(short),
        "median_growth": round(m, 4),
        "worst": round(short[worst_year], 4), "worst_year": worst_year, "worst_growth": round(g[worst_year], 4),
        "bad_year": round(percentile(short.values(), 0.2), 4),
        "good_year": round(percentile(short.values(), 0.8), 4),
        "history": {y: round(series[y], 1) for y in sorted(series)},
    }


def excess_measure(changes, source, unit):
    m = statistics.median(changes.values())
    exc = {y: v - m for y, v in changes.items()}
    worst_year = max(exc, key=exc.get)
    return {
        "unit": unit, "source": source, "years": [min(changes), max(changes)], "observations": len(exc),
        "median_change": round(m, 4), "worst": round(exc[worst_year], 4), "worst_year": worst_year,
        "worst_change": round(changes[worst_year], 4), "bad_year": round(percentile(exc.values(), 0.8), 4),
        "good_year": round(percentile(exc.values(), 0.2), 4),
    }


def fy_label(end_year):
    return f"{end_year - 1}-{str(end_year)[2:]}"


def main():
    t14 = H / "abs_5506_taxation_2014-15.xls"
    t24 = H / "abs_5506_taxation_2024-25.xlsx"
    out = {"method": __doc__.split("\n\n")[1].strip().replace("\n", " "), "states": {}, "national": {}}

    # GST: national collections from the Commonwealth table (Table 1) of both releases.
    gst = splice(table_series(rows_xls(t14, "Table_1"), "goods and services tax"),
                 table_series(rows_xlsx(t24, "Table_1"), "goods and services tax"))
    out["national"]["gst"] = revenue_measure(gst, "ABS Taxation Revenue, Australia (5506.0), 2014-15 and 2024-25 releases, Table 1: goods and services tax collected")

    # Interest rates: change in the financial-year average 10-year yield.
    yields = {}
    with open(H / "rba_f2.1_government_bond_yields.csv", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    col = next(r for r in rows if r and r[0] == "Series ID").index("FCMYGBAG10")
    for r in rows:
        if len(r) > col and r[0][:2].isdigit() and r[col]:
            d, mon, y = r[0].split("-")
            m = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].index(mon) + 1
            fy = int(y) + (1 if m >= 7 else 0)
            yields.setdefault(fy, []).append(float(r[col]))
    fy_avg = {fy: sum(v) / len(v) for fy, v in yields.items() if len(v) == 12}
    changes = {fy_label(b): (fy_avg[b] - fy_avg[b - 1]) / 100 for b in sorted(fy_avg) if b - 1 in fy_avg}
    out["national"]["rates"] = excess_measure(changes, "RBA statistical table F2.1, 10-year Australian Government bond yield, financial-year averages", "rate")

    # Wages: public sector Wage Price Index by state, financial-year average index.
    idx = {}
    with open(H / "abs_wpi_public_sector_index.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            y, q = r["quarter"].split("-Q")
            fy = int(y) + (1 if int(q) >= 3 else 0)
            idx.setdefault(r["region"], {}).setdefault(fy, []).append(float(r["index"]))

    for sid, name, tno, gfs in STATES:
        s = {}
        payroll = splice(table_series(rows_xls(t14, f"Table_{tno}"), PAYROLL), table_series(rows_xlsx(t24, f"Table_{tno}"), PAYROLL))
        convey = splice(table_series(rows_xls(t14, f"Table_{tno}"), CONVEY), table_series(rows_xlsx(t24, f"Table_{tno}"), CONVEY))
        src = f"ABS Taxation Revenue, Australia (5506.0), 2014-15 and 2024-25 releases, Table {tno} ({name})"
        s["payroll"] = revenue_measure(payroll, src + ": taxes on employers' payroll and labour force")
        s["duty"] = revenue_measure(convey, src + ": stamp duties on conveyances")
        roy = table_series(rows_xlsx(H / f"abs_5512_gfs_2024-25_DO{gfs}.xlsx", "Table_1"), "royalty income")
        if sid != "act":  # the ACT budget has no mining royalties (its GFS royalty line is land-related and tiny)
            s["royalties"] = revenue_measure(roy, f"ABS Government Finance Statistics (5512.0), 2024-25 release, state general government operating statement ({name}): royalty income")
        w = {fy: sum(v) / 4 for fy, v in idx[name].items() if len(v) == 4}
        wch = {fy_label(b): w[b] / w[b - 1] - 1 for b in sorted(w) if b - 1 in w}
        s["wages"] = excess_measure(wch, f"ABS Wage Price Index (6345.0), public sector, {name}, total hourly rates excluding bonuses, financial-year averages", "rate")
        out["states"][sid] = s

    out["sensitivities"] = json.loads((ROOT / "data" / "raw" / "budget_sensitivities.json").read_text(encoding="utf-8"))

    # Sanity checks: refuse to publish nonsense.
    for sid, s in out["states"].items():
        for k in ("payroll", "duty", "royalties"):
            if k in s:
                m = s[k]
                assert m["observations"] >= 8, (sid, k)
                assert -0.9 < m["worst"] <= m["bad_year"] <= 0.05, (sid, k, m["worst"], m["bad_year"])
        for k in ("payroll", "duty", "royalties"):
            if k in out["states"][sid]:
                assert out["states"][sid][k]["good_year"] >= 0 >= out["states"][sid][k]["bad_year"] - 1e-9, (sid, k)
        assert out["states"][sid]["wages"]["good_year"] <= 0 <= out["states"][sid]["wages"]["bad_year"]
        assert 0 <= out["states"][sid]["wages"]["bad_year"] <= out["states"][sid]["wages"]["worst"] < 0.1
    assert out["national"]["gst"]["observations"] >= 15

    (ROOT / "data" / "shock_history.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (ROOT / "data" / "shock_history.js").write_text(
        "// Built by scripts/build_shock_history.py. Do not edit by hand.\nwindow.SHOCK_HISTORY = "
        + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    print("Shock sizes from history (shortfall against normal growth):")
    g = out["national"]["gst"]
    print(f"  GST (national): worst {g['worst']:+.1%} in {g['worst_year']}, bad year {g['bad_year']:+.1%}, n={g['observations']}")
    r = out["national"]["rates"]
    print(f"  10-year yield: worst +{r['worst']*100:.2f} pts in {r['worst_year']}, bad year +{r['bad_year']*100:.2f} pts, n={r['observations']}")
    for sid, s in out["states"].items():
        parts = [f"{k} {v['worst']*(100 if v['unit']=='rate' else 100):+.1f}{'pts' if v['unit']=='rate' else '%'} ({v['worst_year']}) / {v['bad_year']*100:+.1f}" for k, v in s.items()]
        print(f"  {sid}: " + "; ".join(parts))


if __name__ == "__main__":
    try:
        main()
    except (AssertionError, ValueError) as e:
        print(f"History check failed: {e}", file=sys.stderr)
        sys.exit(1)
