#!/usr/bin/env python3
"""What are the zero-volume bars in the price panel, and are they real sessions?

WHY THIS EXISTS. A price panel that contains rows which were never trading
sessions is upstream of every measurement built on it. A forward-filled holiday
inserts an artificial 0% daily return, which understates realised volatility,
changes covariance, pads the windows that SMA/RSI/MACD average over, and counts
toward any gate phrased as "200 sessions" when it is really counting rows.

So the question is not "how many zero-volume rows are there" but "which of them
were never sessions at all". Those are different defects with different fixes,
and deleting on `volume > 0` would conflate them:

  SYNTHETIC SESSION   volume 0, OHLC all equal, close equal to the previous
                      close, and essentially nobody in the universe traded that
                      day. A market holiday the provider filled forward. The
                      row is not a session and must not be one.

  MISSING VOLUME      volume 0 but the price MOVED. The price is real and the
                      volume is absent. Dropping the row would discard good
                      price data; keeping the zero would feed a fake denominator
                      to anything volume-based.

  NO-TRADE SESSION    volume 0, flat, on a day the rest of the universe traded.
                      A halt or an untraded listing. Carries no information.

Usage:
    scripts/venv-python.sh scripts/diagnose_price_panel.py [PANEL.csv]
"""
from __future__ import annotations

import csv
import datetime as dt
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A date on which this share of the universe fails to trade is a market
# holiday, not a hundred simultaneous halts.
UNIVERSE_WIDE = 0.80


def load(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def is_zero_volume(row):
    return row.get("Volume", "") in ("0", "0.0", "")


def classify(rows):
    """Split the zero-volume rows into the three populations above."""
    by_ticker = defaultdict(list)
    for row in rows:
        by_ticker[row["Ticker"]].append(row)
    for series in by_ticker.values():
        series.sort(key=lambda r: r["Date"])

    traded_per_date = Counter()
    for row in rows:
        if not is_zero_volume(row):
            traded_per_date[row["Date"]] += 1
    tickers = {row["Ticker"] for row in rows}
    wide = {date for date in {r["Date"] for r in rows}
            if traded_per_date.get(date, 0) < (1.0 - UNIVERSE_WIDE) * len(tickers)}

    buckets = {"synthetic_session": [], "missing_volume": [], "no_trade": []}
    for ticker, series in by_ticker.items():
        for index, row in enumerate(series):
            if not is_zero_volume(row):
                continue
            flat = row["Open"] == row["High"] == row["Low"] == row["Close"]
            same = (index > 0 and row["Close"] == series[index - 1]["Close"])
            if row["Date"] in wide and flat and same:
                buckets["synthetic_session"].append(row)
            elif flat and same:
                buckets["no_trade"].append(row)
            else:
                buckets["missing_volume"].append(row)
    return buckets, wide, by_ticker


def main():
    path = (sys.argv[1] if len(sys.argv) > 1 else
            max((ROOT / "data-store" / "market_data").glob("price_history_*.csv"),
                key=lambda p: p.stat().st_mtime))
    rows = load(path)
    tickers = {r["Ticker"] for r in rows}
    dates = {r["Date"] for r in rows}
    zero = [r for r in rows if is_zero_volume(r)]
    buckets, wide, by_ticker = classify(rows)

    print("=" * 66)
    print("PRICE PANEL DIAGNOSTIC")
    print("=" * 66)
    print("File            %s" % Path(path).name)
    print("Rows            %d over %d tickers and %d dates"
          % (len(rows), len(tickers), len(dates)))
    print()
    print("Zero-volume rows:               %d" % len(zero))
    print("Unique dates:                   %d" % len({r["Date"] for r in zero}))
    print("Affected symbols:               %d / %d"
          % (len({r["Ticker"] for r in zero}), len(tickers)))
    print()
    print("  synthetic sessions (holiday): %4d  on %d universe-wide date(s)"
          % (len(buckets["synthetic_session"]),
             len({r["Date"] for r in buckets["synthetic_session"]})))
    print("  no-trade (halt / unlisted):   %4d  flat, on days others traded"
          % len(buckets["no_trade"]))
    print("  missing volume, price MOVED:  %4d  real price, absent volume"
          % len(buckets["missing_volume"]))
    print()
    flat_all = sum(1 for r in rows
                   if r["Open"] == r["High"] == r["Low"] == r["Close"])
    print("Flat OHLC rows (any volume):    %d" % flat_all)
    print()

    print("Universe-wide non-trading dates present in the panel:")
    for date in sorted(wide):
        weekday = dt.date.fromisoformat(date).strftime("%a")
        n = sum(1 for r in rows if r["Date"] == date)
        print("   %s  %s   %3d rows" % (date, weekday, n))
    print()

    # Does a synthetic row ever become a month-end, and so a rebalance date?
    month_last = {}
    for date in sorted(dates):
        month_last[date[:7]] = date
    contaminated = sorted(set(month_last.values()) & wide)
    print("Month-end rebalance dates falling on a synthetic session: %d"
          % len(contaminated))
    for date in contaminated:
        print("   %s  <-- a rebalance would price off a carried-forward close" % date)
    print()

    # A gate phrased as "200 sessions" counts rows unless these are removed.
    inflated = Counter()
    for row in buckets["synthetic_session"] + buckets["no_trade"]:
        inflated[row["Ticker"]] += 1
    if inflated:
        worst = inflated.most_common(1)[0]
        print("Session counts inflated by non-sessions:")
        print("   %d ticker(s) affected; worst is %s with %d phantom session(s)"
              % (len(inflated), worst[0], worst[1]))
        print("   A gate reading 'needs >= 200 sessions' counts these as sessions.")
    weekend = [r for r in rows
               if dt.date.fromisoformat(r["Date"]).weekday() >= 5]
    print()
    print("Weekend rows: %d %s" % (len(weekend),
                                   "" if weekend else "(none -- not calendar-day expansion)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
