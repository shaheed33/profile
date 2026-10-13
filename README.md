# shaheed.work

Personal site of Shaheed, served at https://shaheed.work through Cloudflare

## Pages

- `index.html` about, projects, work and contact
- `simulator.html` NEM storage simulator, based on Andrew Grogan's Open Electricity Simulation spreadsheet
- `replication.html` October 2024 replication for the simulator
- `prices.html` NEM wholesale price patterns
- `wa-economy.html` WA economy nowcast. `scripts/build_wa_economy.py` downloads ABS and FRED data into `raw/wa/`, backtests the machine learning models (`scripts/wa_model.py`, `scripts/wa_sources.py`) and writes `data/wa_economy.js`. Runs on the 20th of each month through `.github/workflows/wa-economy.yml`, and `raw/wa/build.log` keeps the last run's output
- `vic-housing.html` Victorian housing tracker. `scripts/build_vic_housing.py` downloads ABS building data into `raw/vic/` and compares it with the Housing Statement and the Plan for Victoria council targets (`data/vic_targets.csv` and `data/vic_lga.js`, made by `scripts/fetch_vic_static.py`), writing `data/vic_housing.js`. Runs on the 22nd of each month through `.github/workflows/vic-housing.yml`
- `councils.html` Victorian and NSW council comparisons. `scripts/build_councils.py` reads the official spreadsheets in `raw/councils/` (Know Your Council for Victoria, Your Council for NSW) and writes `data/councils.js`. Refresh by hand once a year: download the new spreadsheets into `raw/councils/` and run the script
- `local-economy.html` What makes your local economy tick, for every council area in Australia: industry mix, shift-share jobs growth, ten-year change and a resilience score against similar areas. `scripts/fetch_local_economy.py` downloads ABS Data by Region, the Census T34 time series and the ASGS remoteness and mesh block files into `raw/local/`, and `scripts/build_local_economy.py` writes `data/local_economy.js`. The GitHub Action `.github/workflows/local-economy.yml` refreshes both each month
- `maldives-loans.html` Who lends to Maldives, and for what? An SDG financing map of the government's active external loans. `scripts/build_maldives_loans.py` reads the Ministry of Finance register in `data/raw/`, groups lenders using `data/lookups/creditor_categories.csv`, tags goals using `data/lookups/sdg_rules.csv`, and writes `data/processed/` and `data/maldives_loans.json`. Exchange rates are in the `FX_TO_USD` table at the top of the script. Hand corrections go in the `manual_primary` and `manual_secondary` columns of `data/processed/sdg_tags.csv` and are kept on every rerun. Refresh by hand when a new register is published
- `maldives-grants.html` Who gives Maldives grants, and for what? The companion to the loans map, from the OECD Creditor Reporting System. `scripts/build_maldives_grants.py` reads `data/raw/oecd_crs_maldives.csv.gz` (downloaded from the OECD Data Explorer API for recipient Maldives, every donor and sector, channels and modalities as totals), groups donors with `data/lookups/crs_donor_groups.csv`, maps OECD purpose codes to goals with `data/lookups/crs_purpose_sdg.csv`, and writes `data/processed/grants_tagged.csv` and `data/maldives_grants.json`. Grants come from the OECD and loans from the Ministry register, so nothing is counted twice. Both Maldives pages share `css/maldives.css`
- `roadmap.html` NSW Roadmap tracker. `scripts/download_aemo.py` fetches the AEMO files into `raw/` and `scripts/build_roadmap.py` turns them into `data/roadmap.js`

## Other files

- `css/theme.css` site theme (Bootswatch Litera and Public Sans)
- `data/` NEM data used by the simulator and price pages
- `scripts/prepare_data.py` builds `data/nem_data.js` from the spreadsheet
- `docs/` MSc dissertation
- `images/profile.jpg` profile photo

## Run locally

```
python -m http.server
```
Then open http://localhost:8000
