"""
Fetches the slow-changing inputs for vic-housing.html and saves them in data/:

  data/vic_targets.csv   council housing targets to 2051, from Plan for Victoria
                         (Engage Victoria, final targets published February 2025)
  data/vic_lga.js        simplified council boundaries (ABS ASGS 2025), for the map

Run it again only if the targets or boundaries change:

    python scripts/fetch_vic_static.py

It checks the result (79 councils, a statewide total close to 2.24 million) and
stops without writing anything if the page has changed shape.
"""
from __future__ import annotations

import csv
import html
import json
import re
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
TARGETS_URL = "https://engage.vic.gov.au/project/developing-a-new-plan-for-Victoria/page/housing-targets-2051"
LGA_URL = ("https://geo.abs.gov.au/arcgis/rest/services/ASGS2025/LGA/MapServer/0/query"
           "?where=state_code_2021%3D%272%27&outFields=LGA_CODE_2025,LGA_NAME_2025,AREA_ALBERS_SQKM"
           "&returnGeometry=true&outSR=4326&maxAllowableOffset=0.004&geometryPrecision=3&f=geojson")
# spellings on the page that differ from the official (ABS) council names
ALIASES = {"Murrundindi": "Murrindindi", "North Grampians": "Northern Grampians"}
BROWSER = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/129.0 Safari/537.36"}


def _num(s: str | None) -> int | None:
    return int(s.replace(",", "")) if s else None


def _clean(name: str) -> str:
    name = re.sub(r"\s+(Shire|City|Rural City|Borough)?\s*Council$", "", name.strip()).strip()
    name = re.sub(r"^Borough of\s+", "", name).rstrip("*").strip()
    return ALIASES.get(name, name)


def fetch_targets() -> list[dict]:
    text = requests.get(TARGETS_URL, headers=BROWSER, timeout=60).text
    page = html.unescape(text).replace("\\/", "/").replace('\\"', '"')
    page = page.replace(" ", " ").replace("&nbsp;", " ")
    rows, region = {}, None
    pat = r'<summary class="details__summary">(.*?)</summary>\s*<div class="details__content">(.*?)</div>'
    for m in re.finditer(pat, page, re.S):
        head = re.sub(r"<[^>]+>", "", m.group(1)).strip()
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", m.group(2))).strip(" |")
        if "targets list" in head:
            # the first council in each list sits under the list heading
            region = "Metropolitan Melbourne" if head.startswith("Metropolitan") else "Regional Victoria"
            name, body = body.split("|", 1)
        elif region is None or "number of" not in body.lower():
            if region is not None:
                print("skipped:", head, "::", body[:120])
            continue
        else:
            name = head
        name = _clean(name)
        # homes in 2023 is the last number before the target (wording varies by council)
        pre = [n for n in re.findall(r"\d[\d,]*", body.split("Additional")[0]) if n != "2023"]
        homes = re.match(r"([\d,]+)", pre[-1]) if pre else None
        target = re.search(r"to 2051\s*-?\s*\+?\s*([\d,]+)", body)
        green = re.search(r"Greenfield target \+?([\d,]+)", body)
        non_green = re.search(r"Non-greenfield target \+?([\d,]+)", body)
        if not (homes and target):
            raise SystemExit(f"Could not read the target for {name}: {body}")
        rec = {"council": name, "region": region, "homes_2023": _num(homes.group(1)),
               "target_2051": _num(target.group(1)),
               "greenfield": _num(green.group(1)) if green else "",
               "non_greenfield": _num(non_green.group(1)) if non_green else ""}
        if name in rows:
            # Mitchell is listed in both: its greenfield part is inside Melbourne's
            # growth boundary and the rest is regional. One target, two home counts.
            prev = rows[name]
            if prev["target_2051"] != rec["target_2051"]:
                raise SystemExit(f"{name} is listed twice with different targets")
            prev["homes_2023"] += rec["homes_2023"]
            prev["region"] = "Metropolitan Melbourne and regional"
        else:
            rows[name] = rec
    # A few councils are missing from the lists but are on the page's map, whose
    # hotspots carry the same text. Use those (final targets only, not drafts).
    for m in re.finditer(r'"title":"([^"]+)"[^{}]*?"description":"(.*?)"\}', page):
        name = _clean(m.group(1))
        body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " | ", m.group(2)))
        if name in rows or "Additional number of homes to 2051" not in body:
            continue
        pre = [n for n in re.findall(r"\d[\d,]*", body.split("Additional")[0]) if n != "2023"]
        target = re.search(r"to 2051\s*-?\s*\+?\s*([\d,]+)", body)
        if not (pre and target):
            continue
        green = re.search(r"Greenfield target \+?([\d,]+)", body)
        non_green = re.search(r"Non-greenfield target \+?([\d,]+)", body)
        rows[name] = {"council": name, "region": "from the map", "homes_2023": _num(pre[-1]),
                      "target_2051": _num(target.group(1)),
                      "greenfield": _num(green.group(1)) if green else "",
                      "non_greenfield": _num(non_green.group(1)) if non_green else ""}
        print("from the map:", rows[name])
    out = sorted(rows.values(), key=lambda r: r["council"])
    total = sum(r["target_2051"] for r in out)
    print(f"{len(out)} councils, {total:,} homes to 2051")
    print(", ".join(r["council"] for r in out))
    if len(out) != 79 or not 2_150_000 <= total <= 2_300_000:
        raise SystemExit("The targets page has changed shape; check it by hand before saving.")
    return out


def fetch_boundaries() -> dict:
    g = requests.get(LGA_URL, headers=BROWSER, timeout=120).json()
    feats = []
    for f in g["features"]:
        p = f["properties"]
        feats.append({"type": "Feature", "geometry": f["geometry"],
                      "properties": {"code": p["LGA_CODE_2025"], "name": p["LGA_NAME_2025"],
                                     "km2": round(p["AREA_ALBERS_SQKM"] or 0)}})
    print(f"{len(feats)} boundary shapes")
    return {"type": "FeatureCollection", "features": feats}


def main() -> None:
    targets = fetch_targets()
    with open(ROOT / "data" / "vic_targets.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(targets[0].keys()))
        w.writeheader()
        w.writerows(targets)
    geo = fetch_boundaries()
    (ROOT / "data" / "vic_lga.js").write_text(
        "// Victorian council boundaries, ABS ASGS 2025, simplified\nwindow.VIC_LGA = "
        + json.dumps(geo, separators=(",", ":")) + ";\n", encoding="utf-8")
    print("Wrote data/vic_targets.csv and data/vic_lga.js")


if __name__ == "__main__":
    main()
