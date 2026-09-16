#!/usr/bin/env python3
"""Verify what Yahoo's fields actually MEAN, against the statements they came from.

WHY THIS EXISTS. `scripts/yahoo_fundamentals.py` normalises Yahoo into a
Screener-shaped CSV, and every one of those normalisations is a guess about a
unit until something checks it. The guesses were originally calibrated against
ONE company (TCS). A field name is not a contract: `debtToEquity` could be a
ratio or a percent, `dividendYield` could be 0.0295 or 2.95, and Yahoo ships
BOTH conventions in the same payload -- `dividendYield` 2.95 sits beside
`trailingAnnualDividendYield` 0.0289 for the same stock.

Three layers, per the audit brief, and the third is the one that matters:

  1. SEMANTIC    what the field is supposed to mean
  2. SCALING     fraction vs percent vs raw currency
  3. RECONSTRUCT rebuild it from the underlying statements and compare

Layer 3 is what catches a field whose NAME is right and whose CONTENT is not.

The sample is chosen for edge cases, not for convenience: a bank and an NBFC
(no "Current Liabilities" row at all), an IT company (net cash), a heavily
leveraged power business, a loss-maker, a high and an unusual dividend payer,
and two companies whose balance sheets changed shape recently through a merger
or a demerger.

Raw responses are snapshotted before anything is derived. That archive is the
point: if a convention is later found to have been misread, historical exports
can be repaired from the snapshot without re-querying Yahoo, which cannot serve
a past vintage at all.

Usage:
    scripts/venv-python.sh scripts/yahoo_contract_audit.py [--out DIR] [--offline]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
DEFAULT_SNAPSHOT = ROOT / "data-store" / "fundamentals" / "raw"

# (symbol, the edge case it is here to cover). Overlap is deliberate: a company
# that is both net-cash and a big dividend payer tests both at once, and a
# disagreement between two cases on one ticker is more informative than two
# tickers that each only exercise the easy path.
SAMPLE = [
    ("HDFCBANK", "bank; balance sheet reshaped by the 2023 HDFC Ltd merger"),
    ("BAJFINANCE", "NBFC"),
    ("TCS", "IT; net cash; the ticker the original conventions were fitted to"),
    ("INFY", "IT; net cash; independent control on TCS"),
    ("ADANIGREEN", "heavily leveraged power"),
    ("VEDL", "leveraged metals; unusually high dividend yield"),
    ("COALINDIA", "high dividend yield; large net cash"),
    ("ETERNAL", "loss-making / recently turned"),
    ("TATASTEEL", "cyclical, has posted losses"),
    ("JIOFIN", "balance sheet created by the 2023 Reliance demerger"),
]

# Where a reconstruction is allowed to land and still count as agreement.
# Generous on purpose: Yahoo's `info` block is TTM and its statements are
# annual, so an exact match is not expected and demanding one would produce
# false alarms. What is being tested is the SCALE -- 100x errors, not 10%ones.
RATIO_TOLERANCE = 0.25      # 25% relative, for like-for-like reconstructions
SCALE_FACTORS = (1.0, 100.0, 0.01)


def _num(value):
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _row(frame, *names, exact_only=False):
    """Statement row by label, returning WHICH label matched.

    Returns (series, matched_label). The label is returned because the matching
    itself is under audit: `_row_from_frame` in the adapter falls back to a
    case-insensitive substring, and "Current Liabilities" is a substring of
    nothing useful but sits near "Total Non Current Liabilities Net Minority
    Interest" in the same index. Any audit that hid which row was used could
    not see that class of error.
    """
    if frame is None or getattr(frame, "empty", True):
        return None, None
    labels = [str(i) for i in frame.index]
    for wanted in names:
        if wanted in labels:
            return frame.loc[wanted], wanted
    if exact_only:
        return None, None
    for wanted in names:
        for label in labels:
            if wanted.lower() in label.lower():
                return frame.loc[label], label
    return None, None


def _first(series):
    if series is None:
        return None
    for value in list(series):
        number = _num(value)
        if number is not None:
            return number
    return None


def _nth(series, index):
    if series is None:
        return None
    values = list(series)
    return _num(values[index]) if len(values) > index else None


def _agree(observed, expected, tolerance=RATIO_TOLERANCE):
    """Do two numbers agree on SCALE, and if not, by what factor do they differ?"""
    if observed is None or expected is None:
        return None, None
    if expected == 0:
        return (abs(observed) < 1e-9), None
    ratio = observed / expected
    for factor in SCALE_FACTORS:
        if abs(ratio - factor) <= tolerance * factor:
            return (factor == 1.0), factor
    return False, ratio


def fetch(yf, symbol):
    """Everything the adapter reads, plus what is needed to re-derive it."""
    ticker = yf.Ticker(symbol + ".NS")
    out = {"symbol": symbol}
    try:
        out["info"] = dict(ticker.info or {})
    except Exception as error:
        return {"symbol": symbol, "error": "info: %s" % error}
    for attribute in ("financials", "balance_sheet", "cashflow"):
        try:
            frame = getattr(ticker, attribute)
            out[attribute] = frame
        except Exception:
            out[attribute] = None
    return out


def snapshot(payload, directory, stamp):
    """Persist the raw response before deriving anything from it."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("%s_%s.json" % (payload["symbol"], stamp))
    body = {"symbol": payload["symbol"], "retrieved": stamp,
            "info": payload.get("info", {})}
    for attribute in ("financials", "balance_sheet", "cashflow"):
        frame = payload.get(attribute)
        if frame is None or getattr(frame, "empty", True):
            body[attribute] = None
            continue
        body[attribute] = {
            "columns": [str(c)[:10] for c in frame.columns],
            "rows": {str(i): [None if v != v else float(v)
                              for v in frame.loc[i].tolist()]
                     for i in frame.index},
        }
    path.write_text(json.dumps(body, indent=1, default=str), encoding="utf-8")
    return path


def audit_one(payload):
    """Every field's three layers, for one company."""
    info = payload.get("info", {})
    fin, bs, cf = (payload.get("financials"), payload.get("balance_sheet"),
                   payload.get("cashflow"))

    equity, equity_label = _row(bs, "Stockholders Equity", "Common Stock Equity",
                                "Total Equity Gross Minority Interest")
    assets, _ = _row(bs, "Total Assets")
    debt, _ = _row(bs, "Total Debt")
    # Exact-only, because this is the label the adapter can mis-resolve.
    current, current_label = _row(bs, "Current Liabilities",
                                  "Total Current Liabilities", exact_only=True)
    loose_current, loose_label = _row(bs, "Current Liabilities",
                                      "Total Current Liabilities")
    revenue, _ = _row(fin, "Total Revenue", "Operating Revenue")
    profit, _ = _row(fin, "Net Income", "Net Income Common Stockholders")
    ebit, ebit_label = _row(fin, "EBIT", "Operating Income")
    interest, _ = _row(fin, "Interest Expense", "Interest Expense Non Operating")
    operating_cash, _ = _row(cf, "Operating Cash Flow")

    equity_v, assets_v, debt_v = _first(equity), _first(assets), _first(debt)
    profit_v, ebit_v = _first(profit), _first(ebit)
    price = _num(info.get("currentPrice"))
    shares = _first(_row(bs, "Ordinary Shares Number")[0])

    checks = {}

    # --- debtToEquity: ratio or percent? ---------------------------------
    rebuilt = (debt_v / equity_v * 100.0) if (debt_v is not None and equity_v
                                              not in (None, 0) and equity_v > 0) else None
    ok, factor = _agree(_num(info.get("debtToEquity")), rebuilt)
    checks["debtToEquity"] = {
        "raw": _num(info.get("debtToEquity")), "rebuilt_as_percent": rebuilt,
        "agrees": ok, "factor": factor,
        "from": "balance sheet Total Debt / Stockholders Equity x100"}

    # --- returnOnEquity / returnOnAssets: fraction or percent? -----------
    for field, base, label in (("returnOnEquity", equity_v, "Stockholders Equity"),
                               ("returnOnAssets", assets_v, "Total Assets")):
        rebuilt = (profit_v / base) if (profit_v is not None and base
                                        not in (None, 0) and base > 0) else None
        ok, factor = _agree(_num(info.get(field)), rebuilt)
        checks[field] = {"raw": _num(info.get(field)), "rebuilt_as_fraction": rebuilt,
                         "agrees": ok, "factor": factor,
                         "from": "FY Net Income / FY %s" % label}

    # --- dividendYield: the field that ships two conventions --------------
    # `dividendRate` is the forward annual rate and is the RELIABLE one.
    # `trailingAnnualDividendRate` is not a usable cross-check: Infosys carries
    # 0.52 there against a real annual dividend of 50.0, so an audit built on
    # it reports a 100x error in a field that is actually correct.
    rate = _num(info.get("dividendRate"))
    if rate is None:
        rate = _num(info.get("trailingAnnualDividendRate"))
    rebuilt = (rate / price * 100.0) if (rate and price) else None
    ok, factor = _agree(_num(info.get("dividendYield")), rebuilt)
    checks["dividendYield"] = {
        "raw": _num(info.get("dividendYield")), "rebuilt_as_percent": rebuilt,
        "sibling_trailingAnnualDividendYield": _num(
            info.get("trailingAnnualDividendYield")),
        "agrees": ok, "factor": factor,
        "from": "trailingAnnualDividendRate / currentPrice x100"}

    # --- growth fields: fraction or percent? ------------------------------
    for field, series in (("revenueGrowth", revenue), ("earningsGrowth", profit)):
        newest, prior = _first(series), _nth(series, 1)
        rebuilt = ((newest / prior - 1.0) if (newest is not None and prior
                                              not in (None, 0) and prior > 0) else None)
        ok, factor = _agree(_num(info.get(field)), rebuilt, tolerance=0.5)
        checks[field] = {"raw": _num(info.get(field)),
                         "rebuilt_as_fraction": rebuilt, "agrees": ok,
                         "factor": factor, "from": "newest vs prior FY column"}

    # --- promoter holding -------------------------------------------------
    held = _num(info.get("heldPercentInsiders"))
    checks["heldPercentInsiders"] = {
        "raw": held, "rebuilt_as_fraction": None,
        "agrees": (held is None or 0.0 <= held <= 1.0), "factor": None,
        "from": "range only: a fraction must sit in [0, 1]"}

    # --- currency scale: is marketCap in the same units as the statements? -
    rebuilt = (price * shares) if (price is not None and shares) else None
    ok, factor = _agree(_num(info.get("marketCap")), rebuilt, tolerance=0.35)
    checks["marketCap"] = {"raw": _num(info.get("marketCap")),
                           "rebuilt_as_rupees": rebuilt, "agrees": ok,
                           "factor": factor,
                           "from": "currentPrice x Ordinary Shares Number"}

    # --- ROCE: the derived one, where period mismatch hides ---------------
    employed = ((assets_v - _first(current)) if (assets_v is not None
                                                 and _first(current) is not None) else None)
    roce = ((ebit_v / employed * 100.0) if (ebit_v is not None and employed
                                            not in (None, 0) and employed > 0) else None)
    checks["ROCE"] = {
        "raw": None, "rebuilt_as_percent": roce, "agrees": None, "factor": None,
        "from": "FY EBIT / (FY Total Assets - FY Current Liabilities) x100",
        "ebit_label": ebit_label, "equity_label": equity_label,
        "current_liabilities_exact": current_label,
        "current_liabilities_loose": loose_label,
        # The bug surface: when no exact row exists, what would a substring
        # match have grabbed instead?
        "loose_would_differ": (current_label != loose_label),
    }

    checks["_context"] = {
        "equity": equity_v, "assets": assets_v, "debt": debt_v,
        "net_income": profit_v, "ebit": ebit_v,
        "operating_cash_flow": _first(operating_cash),
        "interest_expense": _first(interest),
        "currency": info.get("financialCurrency"),
        "equity_is_negative": (equity_v is not None and equity_v < 0),
    }
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--out", default=str(DEFAULT_SNAPSHOT))
    parser.add_argument("--json", default="", help="also write the findings here")
    args = parser.parse_args()

    warnings.filterwarnings("ignore")
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance is not installed.", file=sys.stderr)
        return 1

    stamp = dt.date.today().strftime("%Y%m%d")
    directory = Path(args.out)
    findings = {}
    for symbol, case in SAMPLE:
        payload = fetch(yf, symbol)
        if "error" in payload:
            print("  %-12s FETCH FAILED  %s" % (symbol, payload["error"]))
            continue
        path = snapshot(payload, directory, stamp)
        findings[symbol] = {"case": case, "snapshot": path.name,
                            "checks": audit_one(payload)}
        print("  %-12s ok   %-58s -> %s" % (symbol, case, path.name))

    if args.json:
        Path(args.json).write_text(json.dumps(findings, indent=1, default=str),
                                   encoding="utf-8")
        print("\nfindings written to %s" % args.json)
    return 0 if findings else 1


if __name__ == "__main__":
    sys.exit(main())
