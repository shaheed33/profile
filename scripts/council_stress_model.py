"""Retrospective, expanding-window council models. No random train/test split.

Predict the h-year change in the published operating performance ratio.
Council fixed effects are estimated with OLS council intercepts. The challenger
is a small gradient-boosting model. Persistence predicts zero change.
All preprocessing is fit separately inside each temporal training fold.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

FEATURES = ['operating_ratio', 'past_change', 'grant_share', 'liquidity',
            'renewal_ratio', 'population_growth_5y', 'log_population']
MIN_TRAIN_YEARS = 3
MIN_TRAIN_ROWS = 100
MIN_TEST_YEARS = 3


def features(panel: pd.DataFrame) -> pd.DataFrame:
    p = panel.copy().sort_values(['council', 'year'])
    if p.duplicated(['council', 'year']).any():
        raise ValueError('Duplicate council-year rows')
    # Exact calendar-year join: a gap must never become a one-year lag.
    lag = p[['council', 'year', 'operating_ratio']].copy()
    lag['year'] += 1
    lag = lag.rename(columns={'operating_ratio': 'lag_ratio'})
    p = p.merge(lag, on=['council', 'year'], how='left', validate='one_to_one')
    p['past_change'] = p['operating_ratio'] - p['lag_ratio']
    p['log_population'] = np.log(p['population'].where(p['population'] > 0))
    return p


def supervised(panel: pd.DataFrame, horizon: int) -> pd.DataFrame:
    if horizon not in (2, 3):
        raise ValueError('Supported horizons are two and three years')
    p = features(panel)
    future = p[['council', 'year', 'operating_ratio']].rename(
        columns={'year': 'target_year', 'operating_ratio': 'future_ratio'})
    future['year'] = future['target_year'] - horizon
    pairs = p.merge(future, on=['council', 'year'], validate='one_to_one')
    pairs = pairs.dropna(subset=['operating_ratio', 'future_ratio']).copy()
    pairs['change'] = pairs['future_ratio'] - pairs['operating_ratio']
    return pairs


def folds(pairs: pd.DataFrame):
    for origin in sorted(pairs['year'].unique()):
        # Conservative one-reporting-year embargo: even labels for the
        # origin year are not available to the training model at that origin.
        train = pairs[pairs['target_year'] < origin]
        test = pairs[pairs['year'] == origin]
        if len(train) >= MIN_TRAIN_ROWS and train['year'].nunique() >= MIN_TRAIN_YEARS:
            yield int(origin), train, test


def estimators():
    numeric = make_pipeline(SimpleImputer(strategy='median', keep_empty_features=True), StandardScaler())
    fixed = ColumnTransformer([
        ('numeric', numeric, FEATURES),
        ('council', OneHotEncoder(drop='first', handle_unknown='ignore', sparse_output=False), ['council'])
    ])
    return {
        'fixed_effects': make_pipeline(fixed, LinearRegression()),
        'gradient_boosting': make_pipeline(
            ColumnTransformer([('numeric', SimpleImputer(strategy='median', keep_empty_features=True), FEATURES)]),
            HistGradientBoostingRegressor(max_iter=100, max_leaf_nodes=7,
                                          min_samples_leaf=20, l2_regularization=10, random_state=42))
    }


def evaluate(panel: pd.DataFrame, horizon: int) -> dict:
    pairs = supervised(panel, horizon)
    result = {'horizon': horizon, 'pairs': len(pairs), 'folds': [], 'predictions': [],
              'status': 'insufficient_history', 'metrics': {}, 'forecast_enabled': False}
    for origin, train, test in folds(pairs):
        # A council not seen in training cannot have an estimated fixed effect.
        test = test[test.council.isin(train.council)].copy()
        if test.empty:
            continue
        forecasts = {'persistence': np.zeros(len(test))}
        for name, model in estimators().items():
            model.fit(train[FEATURES + ['council']], train['change'])
            forecasts[name] = model.predict(test[FEATURES + ['council']])
        result['folds'].append({'origin': origin, 'train_rows': len(train), 'test_rows': len(test),
                                'last_training_target': int(train.target_year.max())})
        for j, row in enumerate(test.itertuples()):
            result['predictions'].append({'council': row.council, 'origin': origin,
                'target': int(row.target_year), 'actual_change': float(row.change),
                'baseline_ratio': float(row.operating_ratio),
                **{name: float(pred[j]) for name, pred in forecasts.items()}})
    if result['predictions']:
        p = pd.DataFrame(result['predictions'])
        for name in ('persistence', 'fixed_effects', 'gradient_boosting'):
            error = p.actual_change - p[name]
            result['metrics'][name] = {
                'mae_pp': float(mean_absolute_error(p.actual_change, p[name]) * 100),
                'rmse_pp': float(np.sqrt(np.mean(error ** 2)) * 100),
                # Reported as an empirical retrospective error range, never a
                # calibrated future interval or probability of council distress.
                'error_p10_pp': float(np.quantile(error, .1) * 100),
                'error_p90_pp': float(np.quantile(error, .9) * 100)}
        result['status'] = 'limited_backtest' if len(result['folds']) < MIN_TEST_YEARS else 'retrospective_only'
    # Publication dates, definition continuity and an untouched final holdout
    # still need review before any model can produce a public risk forecast.
    result['reason'] = ('No eligible chronological test folds. More historical workbooks are needed.'
                        if not result['folds'] else
                        'Retrospective evaluation only; publication vintages, boundary changes and a final untouched holdout need review.')
    return result
