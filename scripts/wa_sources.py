"""
Data sources for the WA economy nowcast (wa-economy.html).

ABS series are pulled from the ABS Data API (SDMX) with every dimension
wildcarded except state and frequency, then picked out by matching the
human-readable labels. That way a changed code inside the ABS codelists
does not silently break the pull: if a filter matches zero or several
series, the script stops (or skips, for optional series) and prints the
candidate labels so the filter can be fixed.

Commodity prices and the exchange rate come from FRED (no API key needed).

Every raw download is saved under raw/wa/ so there is a local archive
of exactly what each model run was trained on.
"""
from __future__ import annotations

import io
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import requests

ABS_BASE = "https://data.api.abs.gov.au/rest/data"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
START = "1990-01"
UA = {"User-Agent": "wa-economy-model/1.0 (personal research project)"}


@dataclass
class AbsSeries:
    name: str               # short column name used in the model
    label: str              # plain-English name for the site
    flow: str               # ABS dataflow id
    key: str                # SDMX key, wildcards as empty slots
    match: dict             # dimension id -> regex matched on the label text
    freq: str               # "Q" or "M"
    optional: bool = True
    how: str = "last"       # monthly -> quarterly aggregation: mean | sum | last
    file: str = ""          # raw file name, when one dataflow is downloaded with two keys
    model: bool = True      # False: downloaded for the site only, not a model input

    @property
    def stem(self) -> str:
        return self.file or self.flow


# Each loaded series is (quarterly, label, source, monthly or None). The model
# builds its features from the monthly data where there is some, so a quarter
# with only one or two months in is handled consistently (see wa_model).


@dataclass
class FredSeries:
    name: str
    label: str
    sid: str
    how: str = "mean"


# WA is code 5 in the ABS state codelist (CL_STATE) and in the GCCSA list.
ABS_SERIES = [
    AbsSeries(
        name="sfd", label="WA State Final Demand, chain volume, seasonally adjusted",
        flow="ANA_SFD", key="VCH.SFD.SSS.20.5.Q", freq="Q", optional=False,
        match={"MEASURE": r"^chain volume measures$", "DATA_ITEM": r"^state final demand$",
               "SECTOR": r"^all sectors$",
               "TSEST": r"^seasonally adjusted$"},
    ),
    # LF series share one download, so they must share one key
    AbsSeries(
        name="unemp", label="WA unemployment rate", flow="LF", key=".3.1599.20.5.M", freq="M", how="mean",
        match={"MEASURE": r"^unemployment rate$", "SEX": r"^persons$",
               "AGE": r"^total \(age\)$", "TSEST": r"^seasonally adjusted$"},
    ),
    AbsSeries(
        name="emp", label="WA employed persons", flow="LF", key=".3.1599.20.5.M", freq="M", how="mean",
        match={"MEASURE": r"^employed persons$", "SEX": r"^persons$",
               "AGE": r"^total \(age\)$", "TSEST": r"^seasonally adjusted$"},
    ),
    # state hours are not in LF; they sit in LF_HOURS (dims MEASURE.SEX.AGE.HOURS.TSEST.REGION.FREQ)
    AbsSeries(
        name="hours", label="WA monthly hours worked", flow="LF_HOURS", key="M18.3.1599.TOT.20.5.M", freq="M", how="sum",
        match={"MEASURE": r"^employed persons - monthly hours worked in all jobs$", "SEX": r"^persons$",
               "AGE": r"^total \(age\)$", "HOURS": r"^industry total$", "TSEST": r"^seasonally adjusted$"},
    ),
    AbsSeries(
        name="cpi", label="Perth CPI, all groups", flow="CPI", key="1.10001.10.5.Q", freq="Q",
        match={"MEASURE": r"^index numbers$", "INDEX": r"^all groups cpi$",
               "TSEST": r"^original$"},
    ),
    # quarterly surveys that come out a few days before State Final Demand
    AbsSeries(
        name="cwd", label="WA construction work done, volume", flow="CWD", key="M1.CVM.9.TOT.20.5.Q", freq="Q",
        match={"MEASURE": r"^value of work done$", "PRICE_ADJUSTMENT": r"^chain volume measures$",
               "SECTOR_OWN": r"^total sectors$", "CONSTRUCTION_TYPE": r"^total construction$",
               "TSEST": r"^seasonally adjusted$"},
    ),
    AbsSeries(
        name="capex", label="WA private business investment, volume", flow="CAPEX", key="M1.CVM.TOT.TOT.20.5.Q",
        freq="Q",
        match={"MEASURE": r"^actual expenditure$", "PRICE_ADJUSTMENT": r"^chain volume measures$",
               "ASSET": r"^total$", "INDUSTRY": r"^total, including education and health$",
               "TSEST": r"^seasonally adjusted$"},
    ),
    # monthly Perth CPI (the ABS's main inflation measure since late 2025), for the
    # inflation tracker on the page; the quarterly series above stays the model input
    AbsSeries(
        name="cpi_m", label="Perth CPI, all groups, monthly", flow="CPI", key="1.10001.10.5.M", freq="M",
        file="CPI_M", model=False,
        match={"MEASURE": r"^index numbers$", "INDEX": r"^all groups cpi$", "TSEST": r"^original$"},
    ),
    AbsSeries(
        name="wpi", label="WA wage price index", flow="WPI", key="1.THRPEB.7.TOT.10.5.Q", freq="Q",
        match={"MEASURE": r"^quarterly index$", "INDEX": r"^total hourly rates of pay excluding bonuses$",
               "SECTOR": r"^private and public$", "INDUSTRY": r"^all industries$",
               "TSEST": r"^original$"},
    ),
    # BA_GCCSA has a VALUE dimension, and for WA only original (not seasonally adjusted) data
    AbsSeries(
        name="dwell", label="WA new dwelling approvals", flow="BA_GCCSA", key="1.1.9.1.100.10.5.M", freq="M", how="sum",
        match={"MEASURE": r"^number of dwelling units$", "VALUE": r"^total$", "SECTOR": r"^total sectors$",
               "WORK_TYPE": r"^new$", "BUILDING_TYPE": r"^total residential$", "TSEST": r"^original$"},
    ),
]

FRED_SERIES = [
    FredSeries("iron", "Iron ore price, USD per tonne", "PIORECRUSDM"),
    FredSeries("brent", "Brent crude oil, USD per barrel", "POILBREUSDM"),
    FredSeries("audusd", "US dollars per Australian dollar", "EXUSAL"),
]


# downloaded for the site only, not model inputs
SITE_ONLY = {s.name for s in ABS_SERIES if not s.model}


# ---------------------------------------------------------------- helpers

def _get(url: str, tries: int = 2, headers: dict | None = UA) -> str:
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=headers, timeout=(20, 90))
            if r.status_code == 200 and r.text.strip():
                return r.text
            last = f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(5)
    raise RuntimeError(f"Download failed for {url}\n{last}")


def _split(cell) -> tuple[str, str]:
    """ABS 'labels=both' cells look like 'M13: Unemployment rate'."""
    s = "" if pd.isna(cell) else str(cell)
    if ": " in s:
        code, lab = s.split(": ", 1)
        return code.strip(), lab.strip()
    return s.strip(), s.strip()


def _period_index(s: pd.Series, freq: str) -> pd.PeriodIndex:
    s = s.astype(str).str.replace("-Q", "Q", regex=False)
    return pd.PeriodIndex(s, freq=freq)


def parse_abs_csv(text: str) -> pd.DataFrame:
    """Turn an ABS csvfilewithlabels download into a tidy frame.

    Output columns are the dimension ids (holding label text), plus
    <DIM>__code, TIME_PERIOD and OBS_VALUE.
    """
    raw = pd.read_csv(io.StringIO(text), dtype=str)
    # Some ABS exports give each dimension two columns ("MEASURE" then
    # "Measure") instead of one "MEASURE: Measure" column. Fold those into
    # the "code: label" form so the rest of the code sees one layout.
    cols = list(raw.columns)
    if not any(": " in c for c in cols):
        # ABS csvfilewithlabels gives a code column (upper case id, such as
        # TSEST) followed by its label column (such as "Adjustment Type").
        merged = pd.DataFrame(index=raw.index)
        i = 0
        while i < len(cols):
            c = cols[i]
            nxt = cols[i + 1] if i + 1 < len(cols) else None
            if c.isupper() and nxt is not None and not nxt.isupper():
                merged[f"{c}: {nxt}"] = raw[c].fillna("") + ": " + raw[nxt].fillna("")
                i += 2
            else:
                merged[c] = raw[c]
                i += 1
        raw = merged
    out = pd.DataFrame(index=raw.index)
    for col in raw.columns:
        dim = col.split(":")[0].strip()
        if dim in ("DATAFLOW", "STRUCTURE", "STRUCTURE_ID", "STRUCTURE_NAME", "ACTION", "OBS_VALUE", "UNIT_MEASURE", "UNIT_MULT",
                   "OBS_STATUS", "OBS_COMMENT", "DECIMALS"):
            if dim == "OBS_VALUE":
                out["OBS_VALUE"] = pd.to_numeric(raw[col].map(lambda c: _split(c)[0]), errors="coerce")
            continue
        if dim == "TIME_PERIOD":
            out["TIME_PERIOD"] = raw[col].map(lambda c: _split(c)[0])
            continue
        parts = raw[col].map(_split)
        out[dim] = parts.map(lambda p: p[1])
        out[dim + "__code"] = parts.map(lambda p: p[0])
    return out


def pick_series(df: pd.DataFrame, spec: AbsSeries) -> pd.Series:
    mask = pd.Series(True, index=df.index)
    for dim, pattern in spec.match.items():
        if dim not in df.columns:
            raise KeyError(f"{spec.name}: dimension {dim} not in {spec.flow} download")
        mask &= df[dim].str.contains(pattern, flags=re.I, regex=True, na=False)
    sub = df[mask]
    dims = [c for c in df.columns if c.endswith("__code") is False
            and c not in ("TIME_PERIOD", "OBS_VALUE")]
    groups = sub.groupby(dims, dropna=False)
    if groups.ngroups != 1:
        cands = (df.groupby(list(spec.match.keys())).size().reset_index().iloc[:, :-1]
                 .drop_duplicates().head(40).to_string(index=False))
        raise LookupError(
            f"{spec.name}: filter matched {groups.ngroups} series in {spec.flow} "
            f"(need exactly 1). Some label combinations available:\n{cands}")
    sub = sub.dropna(subset=["OBS_VALUE"])
    s = pd.Series(sub["OBS_VALUE"].values,
                  index=_period_index(sub["TIME_PERIOD"], spec.freq)).sort_index()
    return s[~s.index.duplicated(keep="last")]


def to_quarter(s: pd.Series, how: str) -> pd.Series:
    if s.index.freqstr.startswith("Q"):
        return s
    q = s.groupby(s.index.asfreq("Q"))
    n = q.count()
    agg = {"mean": q.mean, "sum": q.sum, "last": q.last}[how]()
    # A quarter with only one or two months in so far: keep it (it is the
    # nowcast quarter) but scale sums so they stay comparable.
    if how == "sum":
        agg = agg * 3 / n
    return agg


# ---------------------------------------------------------------- loaders

def load_abs(raw_dir: Path, offline: bool) -> tuple[dict, list[str]]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    notes: list[str] = []
    # 1. download every dataflow first, so one run archives all of them.
    # Try the narrow key first; if the ABS rejects it, fall back to
    # wildcarding everything except state and frequency.
    if not offline:
        for stem, (flow, key) in dict((s.stem, (s.flow, s.key)) for s in ABS_SERIES).items():
            broad = "." * (key.count(".") - 1) + ".".join(key.split(".")[-2:])
            for k in dict.fromkeys([key, broad]):
                url = f"{ABS_BASE}/ABS,{flow},/{k}?startPeriod={START}&format=csvfilewithlabels"
                t0 = time.time()
                try:
                    text = _get(url)
                    (raw_dir / f"abs_{stem}.csv").write_text(text, encoding="utf-8")
                    print(f"  {flow} [{k}] {len(text) / 1e6:.1f} MB in {time.time() - t0:.0f}s", flush=True)
                    break
                except RuntimeError as e:
                    print(f"  {flow} [{k}] failed after {time.time() - t0:.0f}s: {str(e)[-160:]}", flush=True)
                    notes.append(f"Download failed for {flow} [{k}]")
    # 2. pick the series out of the saved files
    cache: dict[str, pd.DataFrame] = {}
    series, errors = {}, []
    for spec in ABS_SERIES:
        f = raw_dir / f"abs_{spec.stem}.csv"
        try:
            if spec.stem not in cache:
                if not f.exists() and f.with_suffix(".csv.gz").exists():
                    import gzip
                    text = gzip.open(f.with_suffix(".csv.gz"), "rt", encoding="utf-8").read()
                else:
                    text = f.read_text(encoding="utf-8")
                cache[spec.stem] = parse_abs_csv(text)
            s = pick_series(cache[spec.stem], spec)
            series[spec.name] = (to_quarter(s, spec.how), spec.label, f"ABS {spec.flow}",
                                 s if spec.freq == "M" else None)
        except (LookupError, KeyError, FileNotFoundError) as e:
            (errors if not spec.optional else notes).append(f"{spec.name}: {e}")
    if errors:
        raise SystemExit("Required series missing:\n" + "\n".join(errors + notes))
    return series, notes


def load_fred(raw_dir: Path, offline: bool) -> tuple[dict, list[str]]:
    series, notes = {}, []
    for spec in FRED_SERIES:
        f = raw_dir / f"fred_{spec.sid}.csv"
        try:
            if not offline:
                # FRED stalls on custom User-Agent headers but answers requests' default one
                f.write_text(_get(FRED_CSV.format(sid=spec.sid), headers=None), encoding="utf-8")
            d = pd.read_csv(f if f.exists() else f.with_suffix(".csv.gz"))
            d.columns = ["date", "value"]
            d["value"] = pd.to_numeric(d["value"], errors="coerce")
            d = d.dropna()
            s = pd.Series(d["value"].values,
                          index=pd.PeriodIndex(pd.to_datetime(d["date"]), freq="M"))
            series[spec.name] = (to_quarter(s, spec.how), spec.label, f"FRED {spec.sid}", s)
        except Exception as e:  # noqa: BLE001 - every FRED series is optional
            notes.append(f"Skipped {spec.sid}: {e}")
    return series, notes
