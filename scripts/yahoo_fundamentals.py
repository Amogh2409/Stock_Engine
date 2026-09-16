#!/usr/bin/env python3
"""Build a Screener-shaped fundamentals CSV from Yahoo Finance.

WHY THIS EXISTS. The engine reads fundamentals from a Screener.in CSV export,
which is a manual step: log in, build a screen, set columns, download. Worse, a
free Screener account cannot actually supply what the engine wants --

  * the column list caps at 15 and the engine reads 19;
  * "Gross NPA %", "Net NPA %" and "Capital adequacy ratio" are NOT in
    Screener's ratio library at all (searching `npa` and `capital adequacy`
    returns "Can't find the ratio you are looking for"), so three of the four
    bank metrics cannot be exported through the column picker;
  * at the 15-column cap "Cash flow from operations" does not fit, and its
    absence is a HARD RED FLAG for every non-financial company.

This script fills 15 of the 19 columns with no login and no manual step. It does
NOT replace the Screener export for backtesting -- see THE LIMIT THAT MATTERS.

WHAT IT CANNOT FILL, and why they are left EMPTY rather than defaulted:

    Pledged percentage        no free source; an India-only disclosure
    Gross NPA %               bank-only, not published by Yahoo
    Net NPA %                 bank-only, not published by Yahoo
    Capital adequacy ratio    bank-only, not published by Yahoo

An empty cell means "not measured". A zero would mean "measured, and it is
zero" -- and for `Pledged percentage` a defaulted 0 would silently award the
governance points that a real pledge is supposed to remove, and suppress a hard
red flag. The engine already reports a lender with missing bank metrics as
"not scored" rather than scoring it wrongly, which is the correct degradation.

THE LIMIT THAT MATTERS. Yahoo serves only CURRENT values and four annual
periods. There is no vintage axis and no filing date, so this file describes
today and cannot be used to backtest the fundamental half -- applying today's
balance sheet to 2016 is look-ahead. Point-in-time history still requires an
accumulating archive of dated exports; see knowledge/blocked.md.

Usage:
    scripts/venv-python.sh scripts/yahoo_fundamentals.py [--out DIR] [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import sys
import time
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNIVERSE = ROOT / "data" / "nifty100_source.csv"
DEFAULT_OUT = ROOT / "data-store" / "fundamentals"

# The export contract, in order. Matches the header of a real Screener export
# and of data-store/fundamentals/sample_screener_export.csv exactly; the engine
# matches on these strings, so do not rename them.
COLUMNS = [
    "Name", "NSE code", "BSE code", "Current Price", "Market Capitalization",
    "Sales growth 3Years", "Profit growth 3Years", "ROCE", "Return on equity",
    "Debt to equity", "Interest Coverage", "Cash flow from operations",
    "Promoter holding", "Pledged percentage", "Price to Earning",
    "Price to book value", "Dividend yield", "Industry",
    # Financial-company block. Only the first is obtainable.
    "Return on assets", "Gross NPA %", "Net NPA %", "Capital adequacy ratio",
]

# Yahoo reports market cap and cash flow in rupees; Screener reports crore.
RUPEES_PER_CRORE = 1e7

# THE FIELD CONTRACT.
#
# Every entry was verified by `scripts/yahoo_contract_audit.py` against ten
# companies chosen for edge cases -- a bank, an NBFC, two IT firms, a leveraged
# power business, a leveraged metals firm, a high-dividend miner, a loss-maker,
# a cyclical, and a demerged entity -- by REBUILDING the field from the
# underlying statements, not by trusting its name. `verified` records how many
# of those ten the reconstruction agreed with on scale.
#
# The conventions are genuinely inconsistent and Yahoo ships more than one in
# the same payload: `dividendYield` is 2.95 for TCS while its neighbour
# `trailingAnnualDividendYield` is 0.0289 for the same stock, the same day.
# Do not infer a unit from a name.
FIELD_CONTRACTS = {
    "debtToEquity": {
        "raw_unit": "percent of equity", "internal_unit": "ratio",
        "transform": "divide_by_100",
        "semantics": "gross debt / shareholders equity",
        "verified": "8/8 available; ADANIGREEN and VEDL differ ~30% because "
                    "Yahoo's denominator includes minority interest -- a "
                    "definition gap, not a scale error",
        "absent_for": "banks (HDFCBANK returns None)",
    },
    "returnOnEquity": {
        "raw_unit": "fraction", "internal_unit": "percent",
        "transform": "multiply_by_100", "semantics": "TTM net income / equity",
        "verified": "3/3 available agree on scale",
        "absent_for": "7 of 10 sampled -- most rows come from _derive_return",
    },
    "returnOnAssets": {
        "raw_unit": "fraction", "internal_unit": "percent",
        "transform": "multiply_by_100", "semantics": "TTM net income / assets",
        "verified": "3/3 available agree on scale",
        "absent_for": "8 of 10 sampled; REQUIRED for banks, so the fallback "
                      "matters more than the field",
    },
    "dividendYield": {
        "raw_unit": "percent", "internal_unit": "percent", "transform": "none",
        "semantics": "trailing dividend / price",
        "verified": "4/4 reconstructible agree. Its siblings do NOT: INFY "
                    "carries trailingAnnualDividendRate 0.52 against a real "
                    "dividendRate of 50.0, so those fields are not a "
                    "cross-check and must not be substituted.",
    },
    "heldPercentInsiders": {
        "raw_unit": "fraction", "internal_unit": "percent",
        "transform": "multiply_by_100",
        "semantics": "US-style INSIDER holding, which is NOT the Indian "
                     "promoter concept the engine scores. Right for TCS "
                     "(0.718 vs a real 71.8% Tata Sons holding); wrong in kind "
                     "for a company with no promoter -- HDFCBANK returns "
                     "0.0015 where the true promoter holding is nil.",
        "verified": "10/10 lie in [0,1], so the SCALE is certain; the "
                    "SEMANTICS are approximate for professionally-managed firms",
    },
    "marketCap": {
        "raw_unit": "rupees", "internal_unit": "crore",
        "transform": "divide_by_1e7",
        "semantics": "quoted market capitalisation",
        "verified": "10/10 agree with currentPrice x Ordinary Shares Number",
    },
    "revenueGrowth": {
        "raw_unit": "fraction", "internal_unit": "NOT USED",
        "transform": "n/a",
        "semantics": "MOST RECENT QUARTER year-on-year, not annual. It "
                     "disagrees with an annual reconstruction on 6 of 10 "
                     "sampled. This adapter computes 3-year CAGR from the "
                     "annual statements instead; do not swap this field in.",
        "verified": "deliberately unused",
    },
    "earningsGrowth": {
        "raw_unit": "fraction", "internal_unit": "NOT USED",
        "transform": "n/a",
        "semantics": "as revenueGrowth -- quarterly YoY. Disagrees with an "
                     "annual reconstruction on 8 of 10 sampled.",
        "verified": "deliberately unused",
    },
}

DEBT_TO_EQUITY_IS_PERCENT = True

# Yahoo reports the STATEMENTS in the company's own reporting currency, which
# is not always the currency of the quote. Infosys files in USD while its NSE
# price and marketCap are in rupees. Dividing a USD cash-flow figure by
# RUPEES_PER_CRORE understates it by the exchange rate -- roughly 86x -- and
# "Cash flow from operations" is a HARD RED FLAG input, so a silently shrunken
# figure is worse than an absent one.
#
# Ratios built from two statement rows (ROCE, interest coverage, derived
# ROE/ROA) are currency-safe because the unit cancels. Only absolute
# statement figures crossing into crore are exposed.
STATEMENT_CURRENCY = "INR"

# Range alarms, not clamps. Extreme real companies exist, and silently
# clamping an outlier would hide exactly the data error this audit exists to
# find. `reject` bounds are physical impossibilities; `warn` bounds are
# implausibilities worth printing.
FIELD_RANGES = {
    # (warn_low, warn_high, reject_low, reject_high) in INTERNAL units
    "Return on equity": (-100.0, 100.0, None, None),
    "Return on assets": (-50.0, 50.0, None, None),
    "Debt to equity": (0.0, 10.0, 0.0, None),
    "Interest Coverage": (-50.0, 500.0, None, None),
    "Dividend yield": (0.0, 20.0, 0.0, 100.0),
    "Promoter holding": (0.0, 100.0, 0.0, 100.0),
    "Gross NPA %": (0.0, 25.0, 0.0, 100.0),
    "Net NPA %": (0.0, 15.0, 0.0, 100.0),
    "Capital adequacy ratio": (5.0, 30.0, 0.0, 100.0),
    "ROCE": (-50.0, 150.0, None, None),
}


def _num(value):
    """A finite float, or None. None means not measured and stays empty."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _pct(value, already_percent=False):
    """Format a Yahoo figure as Screener's percent string, or '' if absent."""
    number = _num(value)
    if number is None:
        return ""
    return "%.2f%%" % (number if already_percent else number * 100.0)


def _plain(value, places=2):
    number = _num(value)
    return "" if number is None else ("%.*f" % (places, number))


# Substring matching is how a lookup silently returns the wrong line. Asking
# for "Operating Income" on HDFCBANK's income statement matched "Other Non
# Operating Income Expenses" -- a negative non-operating line -- and the
# adapter published an Interest Coverage of -0.02 for a healthy bank. That is
# worse than the missing value it replaced, because the engine scores it.
#
# A substring hit is only accepted when it cannot be one of these inversions.
SUBSTRING_TRAPS = ("non operating", "non-operating", "discontinued",
                   "pre tax", "pretax", "non current", "non-current")


def _row_from_frame(frame, *names):
    """First matching row of a yfinance statement frame, newest period first.

    Exact label first. A case-insensitive substring is then allowed, because
    Yahoo genuinely renames these rows between tickers -- but only when the
    candidate does not contain a phrase that INVERTS the meaning of what was
    asked for. "Operating Income" must never resolve to "Other Non Operating
    Income", and "Current Liabilities" must never resolve to "Total Non
    Current Liabilities".

    Returning None is the correct outcome when nothing safe matches: an empty
    cell is read as "not measured", which is true, while a wrong cell is
    scored as though it were a fact.
    """
    if frame is None or getattr(frame, "empty", True):
        return None
    labels = list(frame.index)
    for wanted in names:
        for label in labels:
            if str(label) == wanted:
                return frame.loc[label]
    for wanted in names:
        for label in labels:
            text = str(label).lower()
            if wanted.lower() not in text:
                continue
            # Only a trap the REQUEST did not itself ask for disqualifies a
            # candidate, so a deliberate lookup of a non-operating line still
            # works.
            if any(trap in text and trap not in wanted.lower()
                   for trap in SUBSTRING_TRAPS):
                continue
            return frame.loc[label]
    return None


def _first(series):
    """Newest value of a statement row, or None. Columns are newest-first."""
    if series is None:
        return None
    for value in list(series):
        number = _num(value)
        if number is not None:
            return number
    return None


def _cagr(series, years):
    """Compound growth between the newest and `years`-older column, as percent.

    Returns None rather than a number when the span is short, either endpoint
    is missing, or the older endpoint is non-positive -- a growth rate off a
    negative base is not a rate.
    """
    if series is None:
        return None
    values = [_num(v) for v in list(series)]
    if len(values) <= years:
        return None
    latest, oldest = values[0], values[years]
    if latest is None or oldest is None or oldest <= 0 or latest <= 0:
        return None
    return ((latest / oldest) ** (1.0 / years) - 1.0) * 100.0


def _derive_roce(financials, balance_sheet):
    """EBIT / (total assets - current liabilities), as percent.

    Yahoo has no ROCE field. The book definition is return on capital employed,
    and capital employed is total assets less current liabilities. EBIT falls
    back to EBITDA only when EBIT is absent, which OVERSTATES ROCE for
    asset-heavy companies -- flagged rather than silently substituted.
    """
    ebit = _first(_row_from_frame(financials, "EBIT", "Operating Income"))
    fallback = False
    if ebit is None:
        ebit = _first(_row_from_frame(financials, "Normalized EBITDA", "EBITDA"))
        fallback = ebit is not None
    assets = _first(_row_from_frame(balance_sheet, "Total Assets"))
    current = _first(_row_from_frame(
        balance_sheet, "Current Liabilities", "Total Current Liabilities"))
    if ebit is None or assets is None or current is None:
        return None, fallback
    employed = assets - current
    if employed <= 0:
        return None, fallback
    return ebit / employed * 100.0, fallback


def _derive_return(profit, denominator_row):
    """Net income over a balance-sheet base, as a FRACTION to match Yahoo.

    Yahoo omits returnOnEquity and returnOnAssets for a good number of Indian
    tickers -- 4 of the first 5 in this universe -- and ROE alone is 15 of the
    30 financial-quality points, so an absent value is expensive. Both are
    recoverable from statements Yahoo does serve.
    """
    latest_profit = _first(profit)
    base = _first(denominator_row)
    if latest_profit is None or base is None or base <= 0:
        return None
    return latest_profit / base


def _derive_interest_cover(financials):
    """EBIT / interest expense. None when there is no interest expense at all."""
    ebit = _first(_row_from_frame(financials, "EBIT", "Operating Income"))
    interest = _first(_row_from_frame(
        financials, "Interest Expense", "Interest Expense Non Operating"))
    if ebit is None or interest is None:
        return None
    interest = abs(interest)
    if interest <= 0:
        return None
    return ebit / interest


def _as_number(text):
    """A CSV cell back to a number, tolerating the '%' the export writes."""
    if text is None:
        return None
    body = str(text).strip().rstrip("%")
    if not body:
        return None
    try:
        return float(body)
    except ValueError:
        return None


def validate_row(row):
    """Range alarms over a finished row. Returns (warnings, rejections).

    ALARMS, NOT CLAMPS. Extreme real companies exist -- a 12.9% dividend yield
    and a 3.1x debt-to-equity are both in this universe and both true -- so
    silently pulling an outlier back inside a plausible band would hide exactly
    the data error this is here to catch. A warning is printed and the value is
    published unchanged.

    A REJECTION is different: it marks a value that is not merely implausible
    but impossible, such as a promoter holding of 140% or a negative capital
    adequacy ratio. Those are emptied, because an impossible number is not a
    measurement and the engine reads an empty cell as "not measured".
    """
    warnings_out, rejected = [], []
    for column, (warn_low, warn_high, reject_low, reject_high) in FIELD_RANGES.items():
        value = _as_number(row.get(column))
        if value is None:
            continue
        if ((reject_low is not None and value < reject_low)
                or (reject_high is not None and value > reject_high)):
            rejected.append("%s %s impossible, emptied" % (column, row[column]))
            row[column] = ""
            continue
        if ((warn_low is not None and value < warn_low)
                or (warn_high is not None and value > warn_high)):
            warnings_out.append("%s %s outside [%s, %s]"
                                % (column, row[column], warn_low, warn_high))
    return warnings_out, rejected


def fx_to_inr(yf, currency, cache):
    """Rate converting `currency` into rupees, or None.

    Cached per run: a hundred tickers share at most a couple of currencies, and
    the rate must be the SAME for every row in one export or two companies
    become incomparable for a reason that has nothing to do with either.

    The vintage caveat is real and is stated in the output: this is today's
    rate applied to a past financial year. That is wrong in principle and much
    less wrong than the alternative, which was an 86x understatement. The file
    already describes today and cannot be used for backtesting.
    """
    if not currency or currency == STATEMENT_CURRENCY:
        return 1.0
    if currency in cache:
        return cache[currency]
    rate = None
    try:
        quote = yf.Ticker("%sINR=X" % currency).info or {}
        rate = _num(quote.get("regularMarketPrice") or quote.get("previousClose"))
    except Exception:
        rate = None
    cache[currency] = rate
    return rate


def fetch_one(yf, symbol, name, industry, fx_cache=None, capture=None):
    """One Screener-shaped row, or None if Yahoo returns nothing usable."""
    ticker = yf.Ticker(symbol + ".NS")
    try:
        info = ticker.info or {}
    except Exception:
        return None, ["info unavailable"]
    if not info.get("marketCap") and not info.get("currentPrice"):
        return None, ["no quote"]

    try:
        financials = ticker.financials
        balance_sheet = ticker.balance_sheet
        cashflow = ticker.cashflow
    except Exception:
        financials = balance_sheet = cashflow = None

    roce, ebitda_fallback = _derive_roce(financials, balance_sheet)
    revenue = _row_from_frame(financials, "Total Revenue", "Operating Revenue")
    profit = _row_from_frame(financials, "Net Income",
                             "Net Income Common Stockholders")
    operating_cash = _first(_row_from_frame(cashflow, "Operating Cash Flow"))
    # WHICH CURRENCY ARE THE STATEMENTS IN? Not necessarily the one the
    # `financialCurrency` field names -- that describes the `info` block, and
    # the statements do not always follow it. Infosys reports BOTH in USD.
    # HCL Technologies reports `info` in USD and its STATEMENTS IN RUPEES, so
    # trusting the label converted a correct figure into a 19-lakh-crore
    # absurdity.
    #
    # So the currency is measured rather than read: `info.totalRevenue` and
    # the statement's own revenue are the same quantity expressed in the two
    # units, and their ratio says which. Only absolute statement figures are
    # exposed; every ratio below cancels its unit, and cash flow is the only
    # one that crosses into crore.
    currency = info.get("financialCurrency") or STATEMENT_CURRENCY
    currency_note = None
    if operating_cash is not None and currency != STATEMENT_CURRENCY:
        rate = fx_to_inr(yf, currency, fx_cache if fx_cache is not None else {})
        info_revenue = _num(info.get("totalRevenue"))
        statement_revenue = _first(revenue)
        ratio = ((info_revenue / statement_revenue)
                 if (info_revenue and statement_revenue) else None)
        if not rate or ratio is None:
            operating_cash = None
            currency_note = ("cash flow dropped: cannot establish statement "
                             "currency for %s" % currency)
        elif abs(ratio - 1.0) <= 0.25:
            # Statements share the info block's currency, which is not INR.
            operating_cash *= rate
            currency_note = "cash flow converted %s->INR at %.4f" % (currency, rate)
        elif abs(ratio * rate - 1.0) <= 0.25:
            # Statements are already in rupees even though the label says
            # otherwise. Leave them alone.
            currency_note = ("statements already INR despite financialCurrency "
                             "%s; no conversion" % currency)
        else:
            operating_cash = None
            currency_note = ("cash flow dropped: statement currency ambiguous "
                             "(revenue ratio %.4f against %s rate %.2f)"
                             % (ratio, currency, rate))

    debt_to_equity = _num(info.get("debtToEquity"))
    if debt_to_equity is not None and DEBT_TO_EQUITY_IS_PERCENT:
        debt_to_equity /= 100.0

    # Prefer Yahoo's own figure; fall back to the statements only when it is
    # absent, so a ticker Yahoo covers is never silently recomputed differently
    # from one it does not.
    derived = []
    return_on_equity = _num(info.get("returnOnEquity"))
    if return_on_equity is None:
        return_on_equity = _derive_return(profit, _row_from_frame(
            balance_sheet, "Stockholders Equity", "Common Stock Equity",
            "Total Equity Gross Minority Interest"))
        if return_on_equity is not None:
            derived.append("ROE")
    return_on_assets = _num(info.get("returnOnAssets"))
    if return_on_assets is None:
        return_on_assets = _derive_return(
            profit, _row_from_frame(balance_sheet, "Total Assets"))
        if return_on_assets is not None:
            derived.append("ROA")

    market_cap = _num(info.get("marketCap"))
    if capture is not None:
        # POINT-IN-TIME SIZE, captured from the SAME response the row is built
        # from so it cannot drift from it. Raw rupees and raw share count, not
        # the crore figure the export carries: the export rounds, and a size
        # diagnostic ranks on small differences.
        #
        # This exists because the strongest open hypothesis in the project --
        # whether illiquidity carries longer-horizon information or is simply
        # small-cap exposure -- is blocked on having market cap that was TRUE
        # AT THE TIME. It cannot be recovered later, so the only way to have it
        # in 2027 is to start writing it down now.
        capture[symbol] = {
            "marketCap": market_cap,
            "sharesOutstanding": _num(info.get("sharesOutstanding")),
            "currentPrice": _num(info.get("currentPrice")),
            "currency": info.get("currency") or "",
            "financialCurrency": info.get("financialCurrency") or "",
        }
    row = {
        "Name": name,
        "NSE code": symbol,
        "BSE code": "",
        "Current Price": _plain(info.get("currentPrice")),
        "Market Capitalization": _plain(
            None if market_cap is None else market_cap / RUPEES_PER_CRORE),
        "Sales growth 3Years": _pct(_cagr(revenue, 3), already_percent=True),
        "Profit growth 3Years": _pct(_cagr(profit, 3), already_percent=True),
        "ROCE": _pct(roce, already_percent=True),
        "Return on equity": _pct(return_on_equity),
        "Debt to equity": _plain(debt_to_equity),
        "Interest Coverage": _plain(_derive_interest_cover(financials)),
        "Cash flow from operations": _plain(
            None if operating_cash is None else operating_cash / RUPEES_PER_CRORE),
        "Promoter holding": _pct(info.get("heldPercentInsiders")),
        # EMPTY ON PURPOSE. See the module docstring: a defaulted 0 would award
        # governance points and suppress a hard red flag.
        "Pledged percentage": "",
        "Price to Earning": _plain(info.get("trailingPE")),
        "Price to book value": _plain(info.get("priceToBook")),
        "Dividend yield": _pct(info.get("dividendYield"), already_percent=True),
        "Industry": industry,
        "Return on assets": _pct(return_on_assets),
        # EMPTY ON PURPOSE. Not published by Yahoo; the engine reports a lender
        # missing these as "not scored" rather than scoring it on the wrong model.
        "Gross NPA %": "",
        "Net NPA %": "",
        "Capital adequacy ratio": "",
    }
    notes = []
    if currency_note:
        notes.append(currency_note)
    if derived:
        notes.append("derived from statements: " + ", ".join(derived))
    if ebitda_fallback:
        notes.append("ROCE from EBITDA (overstated)")
    missing = [c for c in ("ROCE", "Return on equity", "Debt to equity",
                           "Interest Coverage", "Cash flow from operations")
               if not row[c]]
    if missing:
        notes.append("missing: " + ", ".join(missing))
    return row, notes


class _Frame:
    """The two attributes of a yfinance statement frame these helpers touch.

    A stub rather than a pandas frame so the invariants below run with no
    network and no dependency: they are about LABEL RESOLUTION and UNITS, and
    neither needs a real DataFrame to be wrong.
    """

    def __init__(self, rows):
        self._rows = dict(rows)
        self.empty = not rows

    @property
    def index(self):
        return list(self._rows)

    @property
    def loc(self):
        return self._rows


class ContractTests(unittest.TestCase):
    """Invariants over the field contract. Each one failed at least once."""

    def test_operating_income_never_resolves_to_a_non_operating_line(self):
        # THE BUG THIS EXISTS FOR. HDFCBANK has no "EBIT" and no "Operating
        # Income" row, and "Operating Income" is a substring of "Other Non
        # Operating Income Expenses". The adapter resolved to that negative
        # non-operating line and published Interest Coverage -0.02 for a
        # healthy bank -- a wrong number, which is worse than a missing one,
        # because the engine scores it.
        bank = _Frame({"Other Non Operating Income Expenses": [-3.7e10],
                       "Interest Expense": [1.9e12]})
        self.assertIsNone(_row_from_frame(bank, "EBIT", "Operating Income"))
        self.assertIsNone(_derive_interest_cover(bank))
        # A company that HAS the row is unaffected.
        normal = _Frame({"EBIT": [6.7e11], "Interest Expense": [1.2e10]})
        self.assertAlmostEqual(_derive_interest_cover(normal), 55.833, places=2)

    def test_current_liabilities_never_resolves_to_non_current(self):
        # Same trap on the balance sheet, and the one that would corrupt ROCE:
        # capital employed is assets less CURRENT liabilities, so matching the
        # non-current line inverts the denominator.
        sheet = _Frame({"Total Assets": [1.0e12],
                        "Total Non Current Liabilities Net Minority Interest": [2.0e11]})
        self.assertIsNone(_row_from_frame(sheet, "Current Liabilities",
                                          "Total Current Liabilities"))
        roce, _fallback = _derive_roce(_Frame({"EBIT": [1.0e11]}), sheet)
        self.assertIsNone(roce)

    def test_a_deliberate_non_operating_lookup_still_works(self):
        # The guard must not block a caller that ASKED for the trap phrase,
        # or it would be a blanket ban rather than a mis-resolution guard.
        frame = _Frame({"Interest Expense Non Operating": [5.0e9]})
        self.assertIsNotNone(_row_from_frame(frame, "Interest Expense Non Operating"))

    def test_the_scaling_contract_holds_in_both_directions(self):
        # ROE 0.184 is a FRACTION and must publish as 18.40%, never 0.18%.
        self.assertEqual(_pct(0.184), "18.40%")
        # Dividend yield 2.95 is ALREADY a percent and must not be multiplied.
        self.assertEqual(_pct(2.95, already_percent=True), "2.95%")
        # The same number under the wrong convention is the bug being excluded.
        self.assertNotEqual(_pct(2.95), _pct(2.95, already_percent=True))
        # D/E 74.3 is a percent of equity and must publish as the ratio 0.74.
        self.assertEqual(_plain(74.3 / 100.0), "0.74")

    def test_impossible_values_are_emptied_and_extreme_ones_are_kept(self):
        row = {"Promoter holding": "140.00%", "Capital adequacy ratio": "-2.00%",
               "Dividend yield": "12.89%", "Debt to equity": "3.15"}
        _alarms, rejected = validate_row(row)
        self.assertEqual(len(rejected), 2)
        self.assertEqual(row["Promoter holding"], "")
        self.assertEqual(row["Capital adequacy ratio"], "")
        # Vedanta really does yield 12.89% and really is levered 3.15x. A
        # validator that "corrected" these would be destroying the data.
        self.assertEqual(row["Dividend yield"], "12.89%")
        self.assertEqual(row["Debt to equity"], "3.15")

    def test_growth_off_a_negative_base_is_refused(self):
        # A loss-maker turning a profit has no meaningful growth RATE, and the
        # arithmetic would return a confident number for one.
        self.assertIsNone(_cagr(_Frame({"r": [1]}).loc["r"], 3))
        self.assertIsNone(_cagr([100.0, 50.0, 20.0, -10.0], 3))
        self.assertAlmostEqual(_cagr([200.0, 150.0, 120.0, 100.0], 3), 26.0, places=0)

    def test_roce_refuses_non_positive_capital_employed(self):
        sheet = _Frame({"Total Assets": [1.0e11], "Current Liabilities": [2.0e11]})
        roce, _ = _derive_roce(_Frame({"EBIT": [1.0e10]}), sheet)
        self.assertIsNone(roce, "negative capital employed is not a ROCE")

    def test_derived_returns_refuse_a_non_positive_base(self):
        # A negative-equity company would otherwise report a POSITIVE ROE from
        # a negative profit over a negative base.
        self.assertIsNone(_derive_return([-5.0e9], [-1.0e10]))
        self.assertAlmostEqual(_derive_return([5.0e9], [1.0e10]), 0.5)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="directory to write the CSV into")
    parser.add_argument("--limit", type=int, default=0,
                        help="stop after N tickers; for a quick smoke test")
    parser.add_argument("--sleep", type=float, default=0.3,
                        help="seconds between tickers, to stay polite")
    parser.add_argument("--self-test", action="store_true",
                        help="run the contract invariants offline and exit")
    args = parser.parse_args()

    if args.self_test:
        suite = unittest.TestLoader().loadTestsFromTestCase(ContractTests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    warnings.filterwarnings("ignore")
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance is not installed. Run:\n"
              "  .venv/bin/pip install -r requirements-network.txt", file=sys.stderr)
        return 1

    if not UNIVERSE.exists():
        print("no universe file at %s" % UNIVERSE, file=sys.stderr)
        return 1
    with UNIVERSE.open(newline="", encoding="utf-8") as handle:
        universe = [r for r in csv.DictReader(handle) if r.get("Symbol")]
    if args.limit:
        universe = universe[:args.limit]

    rows, failures, fx_cache = [], [], {}
    for index, entry in enumerate(universe, start=1):
        symbol = entry["Symbol"].strip()
        row, notes = fetch_one(yf, symbol, entry.get("Company Name", "").strip(),
                               entry.get("Industry", "").strip(), fx_cache)
        if row is None:
            failures.append((symbol, "; ".join(notes)))
            print("  %3d/%d  %-14s SKIPPED (%s)"
                  % (index, len(universe), symbol, "; ".join(notes)))
        else:
            alarms, rejections = validate_row(row)
            notes.extend(rejections)
            notes.extend(alarms)
            rows.append(row)
            print("  %3d/%d  %-14s ok%s"
                  % (index, len(universe), symbol,
                     ("  [" + "; ".join(notes) + "]") if notes else ""))
        time.sleep(args.sleep)

    if not rows:
        print("nothing fetched; not writing a file", file=sys.stderr)
        return 1

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.date.today().strftime("%Y%m%d")
    path = out_dir / ("yahoo_fundamentals_%s.csv" % stamp)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    filled = {c: sum(1 for r in rows if r[c]) for c in COLUMNS}
    print("\nWrote %s" % path)
    print("%d rows, %d columns. Field coverage:" % (len(rows), len(COLUMNS)))
    for column in COLUMNS:
        count = filled[column]
        if count == len(rows):
            mark = ""
        elif count == 0:
            mark = "EMPTY BY DESIGN" if column in (
                "BSE code", "Pledged percentage", "Gross NPA %", "Net NPA %",
                "Capital adequacy ratio") else "ALL MISSING"
        else:
            mark = "partial"
        print("   %-26s %3d/%d  %s" % (column, count, len(rows), mark))
    if failures:
        print("\n%d ticker(s) skipped:" % len(failures))
        for symbol, why in failures:
            print("   %-14s %s" % (symbol, why))
    print("\nThis file describes TODAY. It cannot backtest the fundamental half:\n"
          "Yahoo carries no filing dates and no vintages. See knowledge/blocked.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
