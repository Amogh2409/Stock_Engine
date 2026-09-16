#!/usr/bin/env bash
# Refresh every input the screen depends on, then re-run it.
#
# WHY THIS EXISTS. `npm run screen:offline` reads a CACHED price file. That is
# the right default for reproducing a past run, and the wrong one for looking at
# today's market -- the cache can be days old and nothing on screen says so
# loudly. This script refreshes both inputs and then screens, so "I ran it" and
# "I ran it on current data" stop being different things.
#
# WHAT IT REFRESHES, in dependency order:
#   1. Fundamentals  Yahoo -> data-store/fundamentals/yahoo_fundamentals_<date>.csv
#   2. Prices        Yahoo -> data-store/market_data/price_history_<date>_<hash>.csv
#                    (downloaded by the engine itself, as part of `npm run screen`)
#   3. The screen    -> data-store/reports/watchlist_<timestamp>.csv
#
# Fundamentals first: the engine picks the NEWEST export in the folder, so
# writing them after the screen would leave the run one cycle behind.
#
# Usage:
#   scripts/refresh.sh            # refresh everything and screen
#   scripts/refresh.sh --prices   # skip the fundamentals fetch (much faster)
#
# Cron, weekdays at 18:30 IST after the close:
#   30 18 * * 1-5 cd ~/PersonalResearch/TradeBot && scripts/refresh.sh >> data-store/logs/refresh.log 2>&1
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PARITY_PYTHON:-$ROOT/.venv/bin/python}"

if [ ! -x "$PY" ]; then
  echo "No interpreter at $PY. Create it with:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements-network.txt" >&2
  exit 1
fi

SKIP_FUNDAMENTALS=0
[ "${1:-}" = "--prices" ] && SKIP_FUNDAMENTALS=1

echo "=== $(date '+%Y-%m-%d %H:%M:%S') refresh starting ==="

if [ "$SKIP_FUNDAMENTALS" -eq 0 ]; then
  echo "--- 1/3 fundamentals from Yahoo (100 tickers, ~2 min) ---"
  "$PY" scripts/yahoo_fundamentals.py
else
  echo "--- 1/3 fundamentals SKIPPED (--prices) ---"
fi

echo
echo "--- 2/3/3 prices + screen (networked; the engine downloads prices itself) ---"
npm run screen

echo
echo "=== refresh complete ==="

# Print what the run was actually built on, because a screen that silently used
# stale inputs looks identical to one that did not.
LATEST_PRICES="$(ls -t data-store/market_data/price_history_*.csv 2>/dev/null | head -1 || true)"
LATEST_FUND="$(ls -t data-store/fundamentals/*.csv 2>/dev/null | head -1 || true)"
LATEST_LIST="$(ls -t data-store/reports/watchlist_*.csv 2>/dev/null | head -1 || true)"

if [ -n "$LATEST_PRICES" ]; then
  echo "prices      $(basename "$LATEST_PRICES")  last bar $(tail -1 "$LATEST_PRICES" | cut -d, -f1)"
fi
[ -n "$LATEST_FUND" ] && echo "fundamentals $(basename "$LATEST_FUND")"
[ -n "$LATEST_LIST" ] && echo "watchlist   $(basename "$LATEST_LIST")  $(($(wc -l < "$LATEST_LIST") - 1)) holdings"
