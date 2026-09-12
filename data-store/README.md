# data-store

Everything this engine reads or writes at runtime lives here. Nothing is
scattered across the working directory.

| Folder | Contents | Written by |
|---|---|---|
| `fundamentals/` | **Your Screener.in CSV exports.** Drop them here. | you |
| `config/` | `config.json` — optional saved settings, exported from the web app's *Universe & config* tab | you |
| `reports/` | `watchlist_<stamp>.csv`, `rejected_<stamp>.csv`, `ranking_changes.csv` | each run |
| `watchlists/` | `latest_watchlist.json` — the snapshot the next run compares against | each run |
| `logs/` | `run_<stamp>.log` (full console transcript) and `run_<stamp>.json` (machine-readable summary) | each run |
| `cache/` | Cached NSE Nifty 100 constituent CSV | live refresh |
| `market_data/` | `price_history_<date>_<key>.csv` — daily prices (`Date,Ticker,Close,Volume`) for the screened tickers | runs with technical confirmation |

## Getting started

1. On Screener.in, run your query and **Export to CSV**.
2. Save the file into `fundamentals/`.
3. From the project root: `npm run screen` (or `npm run screen:offline`).

The newest CSV in `fundamentals/` is the one used. Older exports are kept, not
deleted, so you can roll back by removing the newer file.

## Settings

If `config/config.json` exists, every run uses it; `--config FILE` overrides
it. A file with an unknown key, a wrong type or an out-of-range value stops the
run with exit code 2 and the log lists every problem — settings are never
silently clamped or ignored.

## Price history

Networked runs download 18 months of daily prices into `market_data/`. A second
run the same day reuses the file if it prices every ticker; otherwise the next
networked run downloads again. Offline runs, failed downloads and partial
(rate-limited) downloads use the newest earlier file for the same set of
tickers whenever it covers more of them. Upload that file into the web app
(**Upload prices**) to see the same technical scores there.

## Choosing a different location

Precedence, highest first:

1. `python3 python/engine.py --data-dir /some/path`
2. `TRADEBOT_DATA_DIR=/some/path npm run screen`
3. Google Drive, when running inside Colab
4. this folder (`<project>/data-store`)

## Retention

Nothing here is pruned automatically. `reports/` and `logs/` grow by two to
three files per run and `market_data/` by one file per day; delete old files
whenever you like. Deleting `watchlists/latest_watchlist.json` resets delta
tracking, so the next run reports every candidate as `NEW_ENTRY`.
