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
        flow="ANA_SFD", key="....5.Q", freq="Q", optional=False,
        match={"MEASURE": r"^chain volume measures$", "DATA_ITEM": r"^state final demand$",
               "SECTOR": r"^all sectors$",
               "TSEST": r"^seasonally adjusted$"},
    ),
    AbsSeries(
        name="unemp", label="WA unemployment rate", flow="LF", key="....5.M", freq="M", how="mean",
        match={"MEASURE": r"^unemployment rate$", "SEX": r"^persons$",
               "AGE": r"^15 years and over$", "TSEST": r"^seasonally adjusted$"},
    ),
    AbsSeries(
        name="emp", label="WA employed persons", flow="LF", key="....5.M", freq="M", how="mean",
        match={"MEASURE": r"^employed total$", "SEX": r"^persons$",
               "AGE": r"^15 years and over$", "TSEST": r"^seasonally adjusted$"},
    ),
    AbsSeries(
        name="hours", label="WA monthly hours worked", flow="LF", key="....5.M", freq="M", how="sum",
        match={"MEASURE": r"hours worked", "SEX": r"^persons$",
               "AGE": r"^15 years and over$", "TSEST": r"^seasonally adjusted$"},
    ),
    AbsSeries(
        name="cpi", label="Perth CPI, all groups", flow="CPI", key="...5.Q", freq="Q",
        match={"MEASURE": r"^index numbers$", "INDEX": r"^all groups cpi$",
               "TSEST": r"^original$"},
    ),
    AbsSeries(
        name="wpi", label="WA wage price index", flow="WPI", key=".....5.Q", freq="Q",
        match={"MEASURE": r"^index numbers$", "INDEX": r"excluding bonuses",
               "SECTOR": r"private and public", "INDUSTRY": r"all industries",
               "TSEST": r"^original$"},
    ),
    AbsSeries(
        name="dwell", label="WA dwelling approvals", flow="BA_GCCSA", key="......5.M", freq="M", how="sum",
        match={"MEASURE": r"number", "SECTOR": r"^total", "WORK_TYPE": r"new",
               "BUILDING_TYPE": r"total (?:dwelling|residential)", "TSEST": r"^seasonally adjusted$"},
    ),
]

FRED_SERIES = [
    FredSeries("iron", "Iron ore price, USD per tonne", "PIORECRUSDM"),
    FredSeries("brent", "Brent crude oil, USD per barrel", "POILBREUSDM"),
    FredSeries("audusd", "US dollars per Australian dollar", "EXUSAL"),
]


# ---------------------------------------------------------------- helpers

def _get(url: str, tries: int = 4) -> str:
    last = None
    for i in range(tries):
        try:
            r = requests.get(url, headers=UA, timeout=120)
            if r.status_code == 200 and r.text.strip():
                return r.text
            last = f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.RequestException as e:
            last = str(e)
        time.sleep(3 * (i + 1))
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
    # 1. download every dataflow first, so one run archives all of them
    if not offline:
        for flow, key in dict((s.flow, s.key) for s in ABS_SERIES).items():
            url = f"{ABS_BASE}/ABS,{flow},/{key}?startPeriod={START}&format=csvfilewithlabels"
            try:
                (raw_dir / f"abs_{flow}.csv").write_text(_get(url), encoding="utf-8")
            except RuntimeError as e:
                notes.append(f"Download failed for {flow}: {e}")
    # 2. pick the series out of the saved files
    cache: dict[str, pd.DataFrame] = {}
    series, errors = {}, []
    for spec in ABS_SERIES:
        f = raw_dir / f"abs_{spec.flow}.csv"
        try:
            if spec.flow not in cache:
                cache[spec.flow] = parse_abs_csv(f.read_text(encoding="utf-8"))
            s = pick_series(cache[spec.flow], spec)
            series[spec.name] = (to_quarter(s, spec.how), spec.label, f"ABS {spec.flow}")
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
                f.write_text(_get(FRED_CSV.format(sid=spec.sid)), encoding="utf-8")
            d = pd.read_csv(f)
            d.columns = ["date", "value"]
            d["value"] = pd.to_numeric(d["value"], errors="coerce")
            d = d.dropna()
            s = pd.Series(d["value"].values,
                          index=pd.PeriodIndex(pd.to_datetime(d["date"]), freq="M"))
            series[spec.name] = (to_quarter(s, spec.how), spec.label, f"FRED {spec.sid}")
        except Exception as e:  # noqa: BLE001 - every FRED series is optional
            notes.append(f"Skipped {spec.sid}: {e}")
    return series, notes
