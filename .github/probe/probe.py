"""Temporary probe: dump real ABS label combinations and test FRED access."""
import io, re, sys, time, gzip
import pandas as pd, requests
sys.path.insert(0, "scripts")
import wa_sources as w

UA = w.UA
def get(url, headers=UA, timeout=60):
    t0 = time.time()
    try:
        r = requests.get(url, headers=headers, timeout=(15, timeout))
        return r.status_code, r.text, time.time() - t0
    except Exception as e:
        return None, str(e), time.time() - t0

print("=== dataflows")
s, t, _ = get("https://data.api.abs.gov.au/rest/dataflow/ABS", {**UA, "Accept": "application/vnd.sdmx.structure+json"})
try:
    import json
    j = json.loads(t)
    for f in j["data"]["dataflows"]:
        if re.search(r"^(LF|BA|WPI|CPI)", f["id"]) or re.search(r"hours", f["name"], re.I):
            print(f["id"], "|", f["name"])
except Exception as e:
    print("dataflow list failed", s, t[:300], e)

for flow in ["LF", "LF_HOURS", "BA_GCCSA", "WPI"]:
    s, t, _ = get(f"https://data.api.abs.gov.au/rest/datastructure/ABS/{flow}", {**UA, "Accept": "application/vnd.sdmx.structure+json"})
    try:
        j = json.loads(t)
        dims = j["data"]["dataStructures"][0]["dataStructureComponents"]["dimensionList"]["dimensions"]
        print(flow, "dims:", [d["id"] for d in sorted(dims, key=lambda d: d.get("position", 0))])
    except Exception as e:
        print(flow, "structure failed", s, t[:200])

def dump(flow, key, filt=None, cols=None):
    url = f"{w.ABS_BASE}/ABS,{flow},/{key}?startPeriod=2024-01&format=csvfilewithlabels"
    s, t, dt = get(url, timeout=120)
    print(f"\n=== {flow} [{key}] HTTP {s} {len(t)/1e6:.1f}MB {dt:.0f}s")
    if s != 200:
        print(t[:300]); return
    df = w.parse_abs_csv(t)
    dims = [c for c in df.columns if not c.endswith("__code") and c not in ("TIME_PERIOD", "OBS_VALUE")]
    if filt is not None:
        df = df[filt(df)]
    g = df.groupby([c for d in dims for c in (d + "__code", d)]).agg(last=("TIME_PERIOD", "max")).reset_index()
    g = g[[c for c in g.columns if (cols is None or any(c.startswith(x) for x in cols)) or c == "last"]].drop_duplicates()
    with pd.option_context("display.width", 300, "display.max_colwidth", 70, "display.max_rows", 400):
        print(g.to_string(index=False))

dump("LF", ".3..20.5.M", cols=["MEASURE", "AGE", "TSEST"])
dump("LF_HOURS", "....5.M")
dump("LF_HOURS", "")
dump("CPI", "1.10001.10.5.Q")
dump("WPI", "1....10.5.Q")
dump("BA_GCCSA", "......5.M",
     filt=lambda d: d["WORK_TYPE"].str.contains("new", case=False) & d["BUILDING_TYPE"].str.contains("total|houses", case=False)
                    & d["MEASURE"].str.contains("number", case=False))
dump("BA_GCCSA", "......5.M", cols=["TSEST", "REGION"])

print("\n=== FRED")
browser = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36",
           "Accept": "text/csv,text/plain,*/*"}
for name, h in [("script UA", UA), ("browser UA", browser), ("no UA", {})]:
    s, t, dt = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=EXUSAL", h, timeout=40)
    print(name, s, f"{dt:.0f}s", t[:80].replace("\n", " | "))
for sid in ["PIORECRUSDM", "POILBREUSDM", "EXUSAL"]:
    for u in [f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}",
              f"https://fred.stlouisfed.org/series/{sid}/downloaddata/{sid}.csv"]:
        s, t, dt = get(u, browser, timeout=40)
        print(sid, u.split("/")[3], s, f"{dt:.0f}s", t[:60].replace("\n", " | "), "...", t.strip()[-40:].replace("\n", " | "))
