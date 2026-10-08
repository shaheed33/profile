# shaheed.work

Personal site of Shaheed, served at https://shaheed.work through Cloudflare

## Pages

- `index.html` about, projects, work and contact
- `simulator.html` NEM storage simulator, based on Andrew Grogan's Open Electricity Simulation spreadsheet
- `replication.html` October 2024 replication for the simulator
- `prices.html` NEM wholesale price patterns
- `wa-economy.html` WA economy nowcast. `scripts/build_wa_economy.py` downloads ABS and FRED data into `raw/wa/`, backtests the machine learning models (`scripts/wa_model.py`, `scripts/wa_sources.py`) and writes `data/wa_economy.js`. Runs on the 20th of each month through `.github/workflows/wa-economy.yml`, and `raw/wa/build.log` keeps the last run's output
- `roadmap.html` NSW Roadmap tracker. `scripts/download_aemo.py` fetches the AEMO files into `raw/` and `scripts/build_roadmap.py` turns them into `data/roadmap.js`

## Other files

- `css/theme.css` site theme (Bootswatch Litera and Public Sans)
- `data/` NEM data used by the simulator and price pages
- `scripts/prepare_data.py` builds `data/nem_data.js` from the spreadsheet
- `docs/` CV and MSc dissertation
- `images/profile.jpg` profile photo

## Run locally

```
python -m http.server
```
Then open http://localhost:8000
