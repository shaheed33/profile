# Council fiscal stress: research specification

The first release is a working **conditional scenario tool** for NSW councils and a reproducible panel/modelling pipeline. It does not issue early-warning forecasts. The existing files cannot support the proposed research claim yet.

## Current evidence

The checked-in OLG Your Council workbooks cover 2022–23, 2023–24 and 2024–25. Each has 128 council records; 127 report revenue and expense totals. Operating performance, unrestricted current and cash expense cover ratios are explicitly **not collected** in the 2024–25 file. This leaves two observed operating-performance years and no two- or three-year outcome pairs. Models must not train on invented, forward-filled or substitute targets.

The official data index is https://www.yourcouncil.nsw.gov.au/data/. The claim that the archive extends to 1994 has not been independently verified in this environment: the official host was blocked by the network policy at implementation time. The project must inspect the historical archive before asserting a continuous comparable series. File hashes and exact headers are included in the downloadable JSON. A hash establishes which input was used, not the publisher's authenticity or historical publication date.

## Reproduce

Use Python 3.12 and the environment's pandas, numpy, openpyxl and scikit-learn dependencies:

```sh
python scripts/build_council_stress.py
python -m unittest discover -s tests -p 'test_council_stress.py'
node --test tests/council-stress.test.cjs
python -m http.server 8000
```

The build writes `data/council_stress_panel.csv`, `data/council_stress.json` and `data/council_stress.js`. Use `--output-dir /tmp/council-stress` to validate without replacing website data. The JSON and JS contain the same payload. The website needs only the JS and existing static server; no API or browser packages are required in production.

Optional browser regression checks use Playwright and an installed Chromium:
`python tests/council-stress.browser.py`. Set `CHROMIUM_EXECUTABLE` if Chromium
is not at `/usr/bin/chromium`. The test starts its own local HTTP server and
checks all 128 councils, missing-data behaviour, controls, CSV export, deep
links, mobile widths, dark mode and homepage navigation. It deliberately blocks
external fonts and CSS to check that the tool remains usable without them.

## Panel and units

One observation is a council and financial-year ending year. The explicit source manifest is `data/lookups/council_stress_sources.json`. Annual workbook headers are checked before reading. 2022–23 totals are multiplied by 1,000 to produce AUD; later totals already use dollars. Percentage conversion factors are reviewed per file, including the renewal ratio's return to 0–100 units in 2024–25. There is no median-based scale guessing. Missing, nonfinite and "not collected" values remain missing. Invalid grant/own-source shares and nonpositive financial totals are excluded and counted in source coverage.

Council names identify entities only within this initial three-year panel. Earlier files need a reviewed concordance of council identifiers, renames, boundary changes and amalgamations. Do not join amalgamated councils to predecessor entities based on similar names. Population and five-year population growth are ABS fields reproduced in OLG, with potentially different reference dates. The changing socioeconomic rank field is deliberately excluded: it is not a stable cardinal socioeconomic score. Payroll, liquid asset stocks, liabilities and recurring versus capital grant amounts are not observed here.

## Econometric target and comparisons

The proposed target is `OPR(council, t+h) − OPR(council, t)` for h = 2 and 3. A negative change is deterioration in this particular indicator, not evidence of insolvency. Exact year joins prevent gaps from masquerading as a forecast horizon.

Candidate predictors: current operating ratio, its previous one-year change, total grant/contribution share, unrestricted current ratio, renewal/depreciation ratio, five-year population growth and log population. Total grant share is only a proxy for grant exposure; a proper recurrent-grant dependence measure requires more detailed accounts.

The econometric benchmark is OLS with council intercepts (fixed effects), without future year effects. Dynamic short-panel bias remains a concern; a longer panel and a correlated-random-effects specification are follow-up research, not completed results. The nonlinear challenger is histogram gradient boosting with 100 iterations, seven leaves and regularisation; hyperparameters are fixed in advance. This is a prediction comparison, not causal identification. The no-change forecast is the persistence benchmark. Training-only median imputation handles missing covariates, never outcomes; training-only scaling is used for the linear model. A council absent from training is excluded from that evaluation fold.

## Backtesting and publication gate

Use expanding chronological splits, not random rows. For test origin t, training labels must end strictly before t. This imposes a conservative reporting-year embargo, but without source publication dates it is not proof of real-time availability. Require at least three training origin years and 100 training rows. Report every eligible fold, training/test sizes and last training target. Evaluate held-out MAE and RMSE in percentage points, alongside persistence. Empirical held-out residual quantiles are descriptive error summaries, not calibrated future uncertainty intervals. Fewer than three test years is flagged as limited evidence.

**Public forecasts are disabled even if the pipeline later produces retrospective scores.** Before enabling them:

1. Verify historical indicator definitions, units, source release dates and council boundary continuity. Preserve point-in-time source vintages and avoid using later revisions as if available earlier.
2. Expand the panel and enrich it with consistently mapped ABS demographic and socioeconomic data available at each forecast origin.
3. Separate model development, interval calibration and an untouched final time-based evaluation. Check prediction stability and subgroup performance against persistence, particularly for councils crossing from positive to negative operating ratios.
4. Assess interval coverage, false alarms, missed deterioration and sensitivity to timing of grants. Use council-clustered resampling for inference; coefficients currently have no inferential confidence intervals.
5. Publish model-specific limitations and dated predictions. Do not convert continuous predictions into uncalibrated distress probabilities. Driver contributions would be associational, not causal scenario effects.

This gate deliberately requires a research review, not merely enough rows. No fitted model, retrospective accuracy, uncertainty band or council risk ranking is claimed from the current inputs.

## Conditional scenario accounting

The scenario uses the latest reported total revenue R, total expenses E and grant/contribution share g. User inputs are the grant cut c, annual wage growth w, assumed payroll share p and extra renewal share a. For year t after the reported base:

```
revenue(t) = R − R × g × c
expenses(t) = E + E × p × ((1 + w)^t − 1)
balance(t) = revenue(t) − expenses(t)
extra_renewal(t) = R × a
additional_funding_pressure(t) = R × g × c + E × p × ((1 + w)^t − 1) + R × a
```

The grant cut is a permanent level reduction, not a repeated compounding cut. Wages compound; staffing, other revenue and other costs are fixed in nominal dollars. The initial 35% payroll share is an editable illustration, not estimated council data. The default 10% grant cut, 3% wage growth and 2% additional renewal are starter assumptions, not predictions. Zero shocks reproduce the base accounting balance in every scenario year.

Revenue minus expenses includes capital grants and is **not** the official OLG operating performance ratio or the reported net result before capital. Extra capital renewal adds funding pressure but is not expensed immediately. Its future depreciation, financing, asset benefits and cash timing are omitted. Total grant contributions can be restricted or non-cash, so the funding-pressure measure is an accounting exposure proxy, not a projected cash shortfall. Historical cash cover is displayed with its source year and is never treated as an available cash balance. There are no probability bands on this deterministic calculation.

## Extending data

Retrieve older workbooks from the official source after network access is available. Keep raw files and add one reviewed entry per financial year to the source manifest, including per-file conversion factors and a verified publication date when known. The loader deliberately fails on missing/ambiguous required headers; do not silently rename a different historical concept to make it fit. Older schema variants need explicit adapters and unit/definition tests. Rebuild to inspect coverage and eligible temporal folds. This step alone does not enable public forecasts.
