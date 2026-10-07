# shaheed.work

Personal site of Shaheed, served at https://shaheed.work through Cloudflare

## Pages

- `index.html` about, projects, work and contact
- `simulator.html` NEM storage simulator, based on Andrew Grogan's Open Electricity Simulation spreadsheet
- `replication.html` October 2024 replication for the simulator
- `prices.html` NEM wholesale price patterns

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
