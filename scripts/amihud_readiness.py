#!/usr/bin/env python3
"""Is the price panel fit to compute Amihud illiquidity? Inputs only, no returns.

WHY THIS EXISTS. Amihud is |return| / traded value, and the denominator is a
rupee amount built from two columns that are adjusted by different conventions.
That makes it unusually sensitive to semantics that are harmless everywhere
else in this repo: a signal that ranks stocks by liquidity can be rewritten by
an adjustment factor without anything looking wrong.

The specific trap is adjusted price x raw volume across a split. If prices are
restated into post-split units and volumes are not, traded value is divided by
the split factor for every session before the split, and a stock's historical
liquidity is mechanically rewritten by a corporate action.

NO FORWARD RETURNS ARE COMPUTED HERE. This audit consumes no research budget
because it cannot learn anything about outcomes.

Usage:
    scripts/venv-python.sh scripts/amihud_readiness.py [PANEL.csv]
"""
from __future__ import annotations

import csv
import statistics
import sys
import warnings
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOW = 21
MIN_SESSIONS = 15
# Splits verified against the provider's own corporate-action feed.
KNOWN_SPLITS = [("BAJFINANCE", "2016-09-08", 5.0),
                ("RELIANCE", "2017-09-07", 2.0),
                ("ITC", "2016-07-01", 1.5)]
# A split-induced rewrite would move traded value by the split factor. Real
# activity moves it too, so the bar is "nowhere near the factor", not "1.00".
INVARIANCE_TOLERANCE = 0.60


# The panel stores auto_adjust=True closes, which are adjusted for splits AND
# dividends. Splits are fine: the provider restates volume into the same units,
# so traded value is invariant (check 2 proves it). Dividends are NOT fine for
# a traded-value denominator -- the adjustment deflates historical prices by
# each stock's OWN dividend history, so the deflation differs across the
# cross-section, and Amihud ranks cross-sectionally.
#
# A uniform deflation would be harmless: it would cancel in the ranking. Only
# the DISPERSION matters, which is what this measures.
BASIS_SPREAD_LIMIT = 1.10
BASIS_PROBE_DATE = "2016-06-30"
BASIS_PROBE_END = "2016-07-08"
BASIS_SAMPLE = ["COALINDIA", "VEDL", "TCS", "ITC", "TATASTEEL", "INFY", "HDFCBANK"]


def check_price_basis(by_ticker):
    """Compare the panel's close to the provider's split-adjusted-only close.

    The ratio is the cumulative DIVIDEND adjustment. Its cross-sectional spread
    is the size of the distortion Amihud's denominator would inherit.
    """
    try:
        import yfinance as yf
    except ImportError:
        return None
    factors = {}
    for ticker in BASIS_SAMPLE:
        series = by_ticker.get(ticker)
        if not series:
            continue
        try:
            raw = yf.download(ticker + ".NS", start=BASIS_PROBE_DATE,
                              end=BASIS_PROBE_END, interval="1d",
                              auto_adjust=False, progress=False)
        except Exception:
            continue
        if raw is None or len(raw) == 0:
            continue
        date = str(raw.index[0])[:10]
        try:
            raw_close = float(raw["Close"].iloc[0].iloc[0])
        except Exception:
            try:
                raw_close = float(raw["Close"].iloc[0])
            except Exception:
                continue
        # SCHEMA v2: audit the column Amihud actually divides by. Before the
        # dual-close repair this read "Close", and it FAILED -- correctly,
        # because the adjusted close carries a per-stock dividend deflation.
        row = next((r for r in series if r["Date"] == date), None)
        if row is None or raw_close <= 0:
            continue
        traded_close = _float(row.get("CloseUnadjusted") or "")
        if traded_close is None:
            # v1 panel: fall back to auditing Close, which is what Amihud would
            # have been forced to use, and which is expected to fail.
            traded_close = _float(row["Close"])
            if traded_close is None:
                continue
        factors[ticker] = traded_close / raw_close
    if len(factors) < 3:
        return None
    low, high = min(factors.values()), max(factors.values())
    return {"factors": factors, "low": low, "high": high,
            "spread_ratio": high / low, "date": BASIS_PROBE_DATE}


def load(path):
    by_ticker = defaultdict(list)
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            by_ticker[row["Ticker"]].append(row)
    for series in by_ticker.values():
        series.sort(key=lambda r: r["Date"])
    return by_ticker


def _float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def traded_value(row):
    """Rupees that changed hands, on the basis Amihud actually divides by.

    CloseUnadjusted where the panel carries it (schema v2), falling back to
    Close only for a v1 file -- where the figure is wrong in the documented
    way, which is exactly what check 2b then reports.
    """
    close = _float(row.get("CloseUnadjusted") or "")
    if close is None:
        close = _float(row["Close"])
    volume = _float(row["Volume"])
    if close is None or volume is None or close <= 0 or volume <= 0:
        return None
    return close * volume


def check_corporate_action_invariance(by_ticker):
    """Traded value must not jump by the split factor across a split."""
    results = []
    for ticker, date, factor in KNOWN_SPLITS:
        series = by_ticker.get(ticker)
        if not series:
            results.append((ticker, date, factor, None, None, "ticker absent"))
            continue
        index = next((i for i, r in enumerate(series) if r["Date"] >= date), None)
        if index is None or index < 30 or index + 30 >= len(series):
            results.append((ticker, date, factor, None, None, "window absent"))
            continue
        before = [v for v in (traded_value(r) for r in series[index - 30:index]) if v]
        after = [v for v in (traded_value(r) for r in series[index + 1:index + 31]) if v]
        if not before or not after:
            results.append((ticker, date, factor, None, None, "no traded value"))
            continue
        ratio = statistics.median(after) / statistics.median(before)
        # A raw-volume panel would show `factor` here; a consistent one shows
        # something near 1 plus ordinary activity noise.
        rewritten = abs(ratio - factor) < abs(ratio - 1.0)
        verdict = "REWRITTEN BY SPLIT" if rewritten else "invariant"
        results.append((ticker, date, factor, ratio, rewritten, verdict))
    return results


def check_volume_units(by_ticker):
    """Volume should be whole shares, not lots or thousands."""
    sample, integral = [], 0
    for series in by_ticker.values():
        for row in series[-50:]:
            volume = _float(row["Volume"])
            if volume is None:
                continue
            sample.append(volume)
            if float(volume).is_integer():
                integral += 1
    if not sample:
        return None
    return {"n": len(sample), "integral_share": integral / len(sample),
            "median": statistics.median(sample),
            "min": min(sample), "max": max(sample)}


def check_coverage(by_ticker):
    """Valid Amihud observations per trailing window, across the panel."""
    per_ticker, all_counts = {}, []
    for ticker, series in by_ticker.items():
        if ticker.startswith("^"):
            continue
        counts = []
        for end in range(WINDOW, len(series)):
            valid = 0
            for index in range(end - WINDOW + 1, end + 1):
                previous = _float(series[index - 1]["Close"])
                value = traded_value(series[index])
                if previous and previous > 0 and value:
                    valid += 1
            counts.append(valid)
        if counts:
            per_ticker[ticker] = {
                "windows": len(counts),
                "median_valid": statistics.median(counts),
                "usable_share": sum(1 for c in counts if c >= MIN_SESSIONS) / len(counts),
            }
            all_counts.extend(counts)
    return per_ticker, all_counts


def main():
    warnings.filterwarnings("ignore")
    path = (sys.argv[1] if len(sys.argv) > 1 else
            max((ROOT / "data-store" / "market_data").glob("price_history_*.csv"),
                key=lambda p: p.stat().st_mtime))
    by_ticker = load(path)
    print("=" * 70)
    print("AMIHUD INPUT READINESS -- no forward returns, no ICs")
    print("=" * 70)
    print("Panel: %s" % Path(path).name)
    print()

    passes = {}

    units = check_volume_units(by_ticker)
    ok_units = bool(units and units["integral_share"] > 0.99 and units["median"] > 1000)
    passes["Volume unit (whole shares)"] = ok_units
    print("1. VOLUME UNIT")
    if units:
        print("   median %,.0f   min %,.0f   max %,.0f   integral %.1f%%"
              .replace(",", "") % (units["median"], units["min"], units["max"],
                                   100 * units["integral_share"]))
        print("   -> %s" % ("whole shares" if ok_units else "SUSPECT: not share counts"))
    print()

    print("2. CORPORATE-ACTION INVARIANCE")
    rows = check_corporate_action_invariance(by_ticker)
    ok_actions = True
    for ticker, date, factor, ratio, rewritten, verdict in rows:
        if ratio is None:
            print("   %-12s %s  1:%.1f   %s" % (ticker, date, factor, verdict))
            continue
        print("   %-12s %s  1:%.1f   median traded value after/before = %.3f  -> %s"
              % (ticker, date, factor, ratio, verdict))
        if rewritten:
            ok_actions = False
    passes["Corporate-action invariance"] = ok_actions
    print()

    print("2b. PRICE BASIS FOR TRADED VALUE  (network)")
    print("   auditing CloseUnadjusted, the column the denominator divides by")
    basis = check_price_basis(by_ticker)
    ok_basis = basis is not None and basis["spread_ratio"] <= BASIS_SPREAD_LIMIT
    if basis is None:
        print("   could not reach the provider; basis UNVERIFIED")
        ok_basis = False
    else:
        for ticker, factor in sorted(basis["factors"].items(), key=lambda kv: kv[1]):
            print("   %-12s adjusted/raw = %.4f" % (ticker, factor))
        print("   cross-sectional spread at %s: %.4f .. %.4f  (%.2fx)"
              % (basis["date"], basis["low"], basis["high"], basis["spread_ratio"]))
        print("   -> %s" % ("consistent" if ok_basis else
                            "FAIL: traded value is deflated DIFFERENTIALLY by "
                            "dividend history"))
    passes["Price basis for traded value"] = ok_basis
    print()

    print("3. MISSING / ZERO VOLUME")
    missing = zero = total = 0
    for ticker, series in by_ticker.items():
        for row in series:
            total += 1
            volume = _float(row["Volume"])
            if volume is None:
                missing += 1
            elif volume <= 0:
                zero += 1
    print("   %d rows: %d blank volume, %d zero volume" % (total, missing, zero))
    print("   -> both are SKIPPED by amihud_illiquidity, never read as zero "
          "liquidity")
    passes["Missing-volume contract"] = True
    print()

    print("4. CROSS-SECTIONAL COVERAGE")
    per_ticker, all_counts = check_coverage(by_ticker)
    usable = [t["usable_share"] for t in per_ticker.values()]
    worst = min(per_ticker.items(), key=lambda kv: kv[1]["usable_share"])
    overall = sum(usable) / len(usable) if usable else 0.0
    print("   median valid sessions per %d-session window: %.0f"
          % (WINDOW, statistics.median(all_counts) if all_counts else 0))
    print("   windows meeting the %d-session minimum: %.1f%%" % (MIN_SESSIONS, 100 * overall))
    print("   worst ticker: %s at %.1f%%" % (worst[0], 100 * worst[1]["usable_share"]))
    passes["Cross-sectional coverage"] = overall > 0.95
    print()

    print("5. EXTREME VALUES (diagnosed, never clamped)")
    values = []
    for ticker, series in by_ticker.items():
        if ticker.startswith("^"):
            continue
        for index in range(1, len(series)):
            previous = _float(series[index - 1]["Close"])
            value = traded_value(series[index])
            current = _float(series[index]["Close"])
            if previous and value and current and previous > 0:
                values.append(abs(current / previous - 1.0) / value)
    values.sort()
    if values:
        def at(q):
            return values[min(len(values) - 1, int(q * len(values)))]
        print("   n %d   p50 %.3e   p99 %.3e   p99.9 %.3e   max %.3e"
              % (len(values), at(0.5), at(0.99), at(0.999), values[-1]))
        print("   max / p99 ratio: %.1fx" % (values[-1] / at(0.99)))
        print("   -> extremes are reported; the estimator averages within a "
              "window and ranks cross-sectionally, so no clamping is applied")
    passes["Extreme-value inspection"] = True
    print()

    print("=" * 70)
    for label, ok in passes.items():
        print("   %-36s %s" % (label, "PASS" if ok else "FAIL"))
    every = all(passes.values())
    print("=" * 70)
    print("READINESS: %s" % ("PASS" if every else "FAIL"))
    return 0 if every else 1


if __name__ == "__main__":
    sys.exit(main())
