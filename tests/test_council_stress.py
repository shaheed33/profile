"""Source-unit, missingness and chronological leakage regression tests."""
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_council_stress import build, read_source
from council_stress_model import FEATURES, estimators, evaluate, features, folds, supervised


def synthetic_panel():
    """Only used in tests; never written to the production data payload."""
    rng = np.random.default_rng(17)
    rows = []
    for c in range(24):
        for year in range(2000, 2015):
            rows.append({'council': f'Council {c}', 'year': year,
                'operating_ratio': c * .002 + .004 * (year - 2000) + rng.normal(0, .008),
                'grant_share': .2 + c / 100, 'liquidity': 2 + c / 20,
                'renewal_ratio': 1 + rng.normal(0, .1), 'population_growth_5y': .05,
                'population': 10000 + 100 * c + (year - 2000) * 10})
    return pd.DataFrame(rows)


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = ROOT / 'data/lookups/council_stress_sources.json'
        cls.specs = json.loads(cls.manifest.read_text())['sources']
        cls.loaded = {s['year']: read_source(s) for s in cls.specs}

    def test_unit_changes_preserve_real_kiama_values(self):
        r23 = next(r for r in self.loaded[2023][0] if r['council'] == 'Kiama')
        r24 = next(r for r in self.loaded[2024][0] if r['council'] == 'Kiama')
        r25 = next(r for r in self.loaded[2025][0] if r['council'] == 'Kiama')
        self.assertEqual(r23['revenue'], 87011000)
        self.assertEqual(r24['revenue'], 94094000)
        self.assertAlmostEqual(r23['operating_ratio'], -.1001)
        self.assertAlmostEqual(r24['operating_ratio'], -.1757)
        self.assertAlmostEqual(r25['renewal_ratio'], 2.647)
        self.assertAlmostEqual(r24['renewal_ratio'], 1.8475)

    def test_not_collected_is_missing_for_every_council(self):
        rows, source = self.loaded[2025]
        for field in ['operating_ratio', 'liquidity', 'cash_cover']:
            self.assertTrue(all(r[field] is None for r in rows))
            self.assertEqual(source['missing'][field], 128)
        self.assertEqual(len(source['sha256']), 64)

    def test_build_current_panel_withholds_models_and_is_reproducible(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp)
            payload = build(self.manifest, output)
            self.assertEqual(payload['meta']['panel_rows'], 384)
            self.assertEqual(payload['meta']['councils'], 128)
            for model in payload['models']:
                self.assertEqual(model['pairs'], 0)
                self.assertEqual(model['folds'], [])
                self.assertFalse(model['forecast_enabled'])
            before = (output / 'council_stress.json').read_bytes()
            build(self.manifest, output)
            self.assertEqual(before, (output / 'council_stress.json').read_bytes())
            browser = (output / 'council_stress.js').read_text().removeprefix('window.COUNCIL_STRESS = ').strip().removesuffix(';')
            self.assertEqual(json.loads(browser), payload)
            self.assertEqual(len(pd.read_csv(output / 'council_stress_panel.csv')), 384)


class ModelTests(unittest.TestCase):
    def test_gaps_are_not_lags_or_wrong_horizon_targets(self):
        panel = synthetic_panel()
        panel = panel[~panel.year.eq(2001)]
        x = features(panel)
        self.assertTrue(x.loc[x.year.eq(2002), 'past_change'].isna().all())
        pairs = supervised(panel, 2)
        self.assertTrue(((pairs.target_year - pairs.year) == 2).all())
        self.assertFalse(pairs.year.eq(2001).any())

    def test_no_target_imputation(self):
        panel = synthetic_panel()
        panel.loc[panel.year.eq(2014), 'operating_ratio'] = np.nan
        self.assertFalse(supervised(panel, 2).target_year.eq(2014).any())

    def test_future_changes_cannot_change_past_features(self):
        panel = synthetic_panel()
        before = features(panel).query('year <= 2006').reset_index(drop=True)
        panel.loc[panel.year.gt(2006), 'operating_ratio'] = 1000
        after = features(panel).query('year <= 2006').reset_index(drop=True)
        pd.testing.assert_frame_equal(before, after)

    def test_every_fold_purges_labels_at_or_after_test_origin(self):
        pairs = supervised(synthetic_panel(), 3)
        tested = list(folds(pairs))
        self.assertGreaterEqual(len(tested), 3)
        for origin, train, test in tested:
            self.assertLess(train.target_year.max(), origin)
            self.assertTrue(test.year.eq(origin).all())
            self.assertTrue(set(train.index).isdisjoint(test.index))

    def test_preprocessing_uses_training_values_only(self):
        pairs = supervised(synthetic_panel(), 2)
        _, train, test = next(folds(pairs))
        model = estimators()['fixed_effects']
        model.fit(train[FEATURES + ['council']], train.change)
        imputer = model.steps[0][1].named_transformers_['numeric'].steps[0][1]
        stats = imputer.statistics_.copy()
        test = test.copy()
        test['grant_share'] = 10000
        model.predict(test[FEATURES + ['council']])
        np.testing.assert_allclose(stats, imputer.statistics_)
        self.assertAlmostEqual(stats[FEATURES.index('grant_share')], train.grant_share.median())

    def test_both_models_execute_on_temporal_holdouts(self):
        result = evaluate(synthetic_panel(), 2)
        self.assertGreaterEqual(len(result['folds']), 3)
        self.assertTrue(result['predictions'])
        self.assertEqual(set(result['metrics']), {'persistence', 'fixed_effects', 'gradient_boosting'})
        for scores in result['metrics'].values():
            self.assertTrue(all(np.isfinite(v) for v in scores.values()))
        self.assertFalse(result['forecast_enabled'])

    def test_duplicates_fail_instead_of_multiplying_panel_rows(self):
        panel = synthetic_panel()
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            supervised(pd.concat([panel, panel.iloc[:1]]), 2)


if __name__ == '__main__':
    unittest.main()
