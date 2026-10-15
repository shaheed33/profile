"""Build the NSW council-year panel and website payload from reviewed OLG files.

    python scripts/build_council_stress.py
    python scripts/build_council_stress.py --output-dir /tmp/council-stress

No downloading or heuristic rescaling. Source-file checksums, units, missing
values and model eligibility are exported with the data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd
import openpyxl

from build_councils import norm_cols, num
from council_stress_model import evaluate

ROOT = Path(__file__).resolve().parent.parent
FIELDS = {
    'operating_ratio': ('Operating Performance Ratio', 'percent_scale'),
    'liquidity': ('Unrestricted Current Ratio', None),
    'cash_cover': ('Cash Expense Cover Ratio', None),
    'grant_share': ('Grants & Contributions Revenue', 'percent_scale'),
    'own_source_share': ('Own Source Revenue', 'percent_scale'),
    'renewal_ratio': ('Building & Infrastructure Renewal Ratio', 'renewal_scale'),
    'population_growth_5y': ('Population Change over 5 years', 'percent_scale'),
    'revenue': ('Total Revenue from Continuing Operations', 'money_scale'),
    'expenses': ('Total Expenses from Continuing Operations', 'money_scale'),
    'net_result_before_capital': ('Net Operating Result Before Capital', 'money_scale'),
}


def read_source(spec: dict, root: Path = ROOT) -> tuple[list, dict]:
    path = root / spec['file']
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        raw_rows = list(workbook.worksheets[0].iter_rows(values_only=True))
    finally:
        workbook.close()
    header_row = next(i for i, row in enumerate(raw_rows[:8])
                      if row[0] and str(row[0]).startswith('Council'))
    headers = [norm_cols(value) for value in raw_rows[header_row]]
    council_rows = [row for row in raw_rows[header_row + 1:] if row[0] and num(row[1]) is not None]
    councils = {str(row[0]).strip(): row for row in council_rows}
    if len(councils) != len(council_rows):
        raise ValueError(f'{path.name}: duplicate council rows')
    columns = {}
    for name, (prefix, _) in FIELDS.items():
        found = [i for i, h in enumerate(headers) if h.lower().startswith(prefix.lower())]
        if len(found) != 1:
            raise ValueError(f'{path.name}: expected one {prefix} column, got {len(found)}')
        columns[name] = found[0]
    if not headers[4].lower().startswith('population'):
        raise ValueError(f'{path.name}: population column changed')
    records, missing = [], {f: 0 for f in FIELDS}
    for council, row in sorted(councils.items()):
        record = {'council': council, 'year': spec['year'], 'group': str(row[2]).strip(),
                  'population': num(row[4]), 'source_file': spec['file']}
        for field, (_, scale) in FIELDS.items():
            column = columns[field]
            value = None if 'not collected' in headers[column].lower() else num(row[column])
            if value is not None:
                value *= spec[scale] if scale else 1
                if not math.isfinite(value):
                    value = None
                if value is not None and (field in ('grant_share', 'own_source_share') and not 0 <= value <= 1):
                    value = None
                if value is not None and field in ('revenue', 'expenses') and value <= 0:
                    value = None
            record[field] = value
            missing[field] += value is None
        records.append(record)
    provenance = {**spec, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'councils': len(records), 'missing': missing,
                  'headers': {f: headers[i] for f, i in columns.items()}}
    return records, provenance


def build(manifest: Path, output_dir: Path, root: Path = ROOT) -> dict:
    specs = json.loads(manifest.read_text())['sources']
    if len({s['year'] for s in specs}) != len(specs):
        raise ValueError('Only one reviewed source per financial year is supported')
    records, sources = [], []
    for spec in sorted(specs, key=lambda s: s['year']):
        rows, provenance = read_source(spec, root)
        records.extend(rows)
        sources.append(provenance)
    if not records:
        raise ValueError('No council records')
    panel = pd.DataFrame(records).sort_values(['council', 'year'])
    if panel.duplicated(['council', 'year']).any():
        raise ValueError('Duplicate council-year')
    results = [evaluate(panel, h) for h in (2, 3)]
    latest_year = int(panel.year.max())
    councils = []
    # Latest-year membership; do not silently merge renamed/amalgamated entities.
    for name in sorted(panel.loc[panel.year == latest_year, 'council']):
        history = [r for r in records if r['council'] == name]
        councils.append({'name': name, 'group': history[-1]['group'], 'history': history})
    payload = {'meta': {'title': 'NSW Council Fiscal Stress Research',
                'years': sorted(int(y) for y in panel.year.unique()),
                'latest_year': latest_year, 'councils': len(councils), 'panel_rows': len(panel),
                'status': 'scenario_only', 'sources': sources,
                'target': 'Change in published operating performance ratio over two or three years',
                'units': 'Money in AUD; percentage fields stored as fractions; years are financial-year ending years',
                'demographics': 'ABS population and five-year population change as reproduced in each OLG workbook; source vintages may differ from the financial year.',
                'limitations': [
                    '2024–25 does not collect operating performance, unrestricted current or cash expense cover ratios.',
                    'Grant shares include capital grants and contributions; they are not recurrent-grant dependence.',
                    'Payroll shares and extra renewal spending are user assumptions, not observed council budget lines.',
                    'No public risk scores, statistical forecast intervals or liquidity forecasts are available.',
                    'Historical publication dates, council boundary continuity and a longer panel need verification.'
                ]}, 'models': results, 'councils': councils}
    output_dir.mkdir(parents=True, exist_ok=True)
    panel.to_csv(output_dir / 'council_stress_panel.csv', index=False)
    (output_dir / 'council_stress.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False,
                                                            separators=(',', ':')) + '\n')
    (output_dir / 'council_stress.js').write_text('window.COUNCIL_STRESS = ' + json.dumps(
        payload, ensure_ascii=False, allow_nan=False, separators=(',', ':')) + ';\n')
    print(f'{len(panel)} council-years, {len(councils)} councils; ' +
          ', '.join(f"{r['horizon']}y: {r['pairs']} pairs / {len(r['folds'])} test folds" for r in results))
    return payload


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifest', type=Path, default=ROOT / 'data/lookups/council_stress_sources.json')
    ap.add_argument('--output-dir', type=Path, default=ROOT / 'data')
    args = ap.parse_args()
    build(args.manifest, args.output_dir)
