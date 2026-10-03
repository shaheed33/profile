# Abdulla Shaheed: profile and energy market side projects

Live site: https://shaheed33.github.io/profile/

## Pages
* `index.html` About, with CV and MSc dissertation (`docs/`)
* `simulator.html` NEM storage simulator. Choose a future grid of wind, solar and storage and test it against five years of real weather (August 2021 to July 2026), every half hour.
* `replication.html` Replication of Andrew Grogan's Open Electricity Simulation spreadsheet for October 2024, comparing his data with a rebuild from AEMO data.
* `prices.html` NEM price patterns by hour, season and region, 2021 to 2026.

## Data
* `data/nem_aug20XX_jul20XX.js` half hourly NEM generation by fuel, one file per 12 months, built from AEMO data with NEMOSIS.
* `data/nem_2024-10.js` the October 2024 replication month (AEMO rebuild).
* `data/nem_data.js` Andrew Grogan's October 2024 data (Open Electricity), from his spreadsheet.
* `data/prices_data.js` price summaries for the price patterns page.
* `css/theme.css` the site theme.

Original data from the Australian Energy Market Operator (AEMO). Inspired by Andrew Grogan's Open Electricity Simulation spreadsheet (2024).
