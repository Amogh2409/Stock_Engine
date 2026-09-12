"""
===================================================================================
Indian Equity Quantitative Screening Engine
Architecture: Google Colab + Google Drive persistence + NSE daily data
Style: Long-only medium-term investing (1-6 month holding horizon)
Market: NSE/BSE Indian equities | Currency: INR (Rs, crore)
===================================================================================
DISCLAIMER
This notebook generates deterministic, rule-based quantitative research signals
for investment research and educational due diligence. It does NOT execute
trades, solicit capital, or guarantee future returns.
It is run-on-demand and does NOT provide continuous monitoring.
===================================================================================

IMPORTING THIS MODULE HAS NO SIDE EFFECTS.
No Drive mount, no network access, and no pipeline execution happen at import
time. Everything runnable lives inside main(), which is invoked only under the
__main__ guard at the bottom of this file. That makes the engine importable by
offline unit tests.

Data-source unit contract: fundamentals arrive from Screener.in CSV exports.
Monetary columns are natively denominated in rupee CRORE; growth/return/holding
columns are PERCENT; valuation and leverage columns are dimensionless RATIOS.
clean_numeric() takes the field's declared unit so that "100 LAKH" and
"1 CRORE" both resolve to 1.0 crore, and so a monetary suffix on a percentage
is rejected rather than silently accepted.

CSV export contract: every string cell is passed through escape_csv_cell()
before export so spreadsheet formula injection cannot execute. Numeric columns
are written as numbers and are never converted to text.
"""

# === SECTION:imports:Imports, Seed & Reproducibility ===
import argparse
import csv
import datetime
import decimal
import hashlib
import io
import json
import math
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

# Deterministic seed. The engine is rule-based and contains no stochastic
# component; the seed is fixed only so third-party library behaviour cannot
# introduce run-to-run variation. It is applied inside main(), never at import
# time, so importing the engine leaves global RNG and warning state untouched.
DETERMINISTIC_SEED = 42

SCHEMA_VERSION = "v6"
# === END SECTION:imports ===


# === SECTION:universe_snapshot:Shared Nifty 100 Snapshot & Provenance ===
# GENERATED BLOCK - DO NOT EDIT BY HAND.
# Injected from data/nifty100_snapshot.json by scripts/build_python_source.mjs,
# the same snapshot that generates src/data/nifty100Snapshot.ts. One file feeds
# both engines so the browser and the notebook can never disagree.
# === GENERATED:NIFTY100 START ===
NIFTY100_PROVENANCE = {
    "source_url": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "retrieved_at_utc": "2026-09-10T19:09:00Z",
    "as_of_date": "2026-09-10",
    "sha256_of_source_csv": "1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9",
    "count": 100,
}

# Cached snapshot, NOT a live feed. Current as of
# NIFTY100_PROVENANCE["as_of_date"]; the index is rebalanced periodically.
NIFTY100_FALLBACK_SYMBOLS = [
    "ABB", "ADANIENSOL", "ADANIENT", "ADANIGREEN", "ADANIPORTS", "ADANIPOWER",
    "AMBUJACEM", "APOLLOHOSP", "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJAJFINSV",
    "BAJAJHLDNG", "BAJFINANCE", "BANKBARODA", "BEL", "BHARTIARTL", "BOSCHLTD",
    "BPCL", "BRITANNIA", "CANBK", "CGPOWER", "CHOLAFIN", "CIPLA",
    "COALINDIA", "CUMMINSIND", "DIVISLAB", "DLF", "DMART", "DRREDDY",
    "EICHERMOT", "ENRIN", "ETERNAL", "GAIL", "GODREJCP", "GRASIM",
    "HAL", "HCLTECH", "HDFCAMC", "HDFCBANK", "HDFCLIFE", "HINDALCO",
    "HINDUNILVR", "HINDZINC", "HYUNDAI", "ICICIBANK", "INDHOTEL", "INDIGO",
    "INFY", "IOC", "IRFC", "ITC", "JINDALSTEL", "JIOFIN",
    "JSWSTEEL", "KOTAKBANK", "LODHA", "LT", "LTM", "M&M",
    "MARUTI", "MAXHEALTH", "MAZDOCK", "MOTHERSON", "MUTHOOTFIN", "NESTLEIND",
    "NTPC", "ONGC", "PFC", "PIDILITIND", "PNB", "POWERGRID",
    "RECLTD", "RELIANCE", "SBILIFE", "SBIN", "SHREECEM", "SHRIRAMFIN",
    "SIEMENS", "SOLARINDS", "SUNPHARMA", "TATACAP", "TATACONSUM", "TATAPOWER",
    "TATASTEEL", "TCS", "TECHM", "TITAN", "TMCV", "TMPV",
    "TORNTPHARM", "TRENT", "TVSMOTOR", "ULTRACEMCO", "UNIONBANK", "UNITDSPR",
    "VBL", "VEDL", "WIPRO", "ZYDUSLIFE",
]
# === GENERATED:NIFTY100 END ===
# === END SECTION:universe_snapshot ===


# === SECTION:helpers:Numeric Helpers & Canonical Rounding ===
# Whitespace exactly as JavaScript's \s and String.prototype.trim() define it
# (WhiteSpace + LineTerminator). Python's \s and str.strip() disagree at the
# edges -- \x1c-\x1f and \x85 are whitespace to Python, U+FEFF is whitespace to
# JavaScript -- so the Python side spells the set out instead of trusting the
# language default. screenerEngine.ts uses \s and trim(), which are this set.
_WS_CHARS = (
    "\t\n\x0b\x0c\r \N{NO-BREAK SPACE}\N{OGHAM SPACE MARK}"
    + "".join(chr(code) for code in range(0x2000, 0x200B))
    + "\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}\N{NARROW NO-BREAK SPACE}"
    + "\N{MEDIUM MATHEMATICAL SPACE}\N{IDEOGRAPHIC SPACE}\N{ZERO WIDTH NO-BREAK SPACE}"
)
_WS_CLASS = "".join(re.escape(ch) for ch in _WS_CHARS)


def js_trim(text):
    """str.strip() with JavaScript's whitespace set. Mirrors String.prototype.trim()."""
    return str(text).strip(_WS_CHARS)


def clamp(val, min_val, max_val):
    """Clamp val into [min_val, max_val]. Mirrors clamp() in screenerEngine.ts."""
    return max(min_val, min(max_val, val))


def round1(value):
    """Canonical score rounding: one decimal place, half-up.

    Implemented as floor(x*10 + 0.5)/10, which is bit-for-bit what
    JavaScript's Math.round(x*10)/10 computes on the same IEEE-754 double.
    Both engines MUST use this so scores -- and therefore rank order -- are
    identical. Python's built-in round() is banker's rounding and must never
    be used for scores.

    Scores are always non-negative, so half-up and half-away-from-zero agree.
    """
    if value is None:
        return None
    return math.floor(float(value) * 10.0 + 0.5) / 10.0


def parse_strict_decimal(val):
    """Strict scalar -> float. Mirrors parseStrictDecimal() in screenerEngine.ts.

    Finite numbers pass through. Strings must match _NUMERIC_BODY_RE, the
    ASCII-only decimal shape both engines pin, so hex (0x10), binary (0b101),
    octal (0o17), underscore separators (1_0), inf/nan and non-ASCII digits are
    rejected identically -- JavaScript's Number() and Python's float() each
    accept some of those and not others.
    """
    if isinstance(val, bool) or not isinstance(val, (str, int, float)):
        return None
    if isinstance(val, (int, float)):
        try:
            num = float(val)
        except OverflowError:
            return None
        return None if math.isnan(num) or math.isinf(num) else num
    text = js_trim(val)
    if not _NUMERIC_BODY_RE.match(text):
        return None
    num = float(text)
    if math.isnan(num) or math.isinf(num):
        return None
    return num


# Field unit contract. See the module docstring.
UNIT_CRORE = "crore"      # natively rupee crore; accepts CR / LAKH suffixes
UNIT_PERCENT = "percent"  # accepts a trailing %, rejects monetary suffixes
UNIT_RATIO = "ratio"      # dimensionless, rejects % and monetary suffixes
UNIT_PRICE = "price"      # rupees per share, rejects monetary suffixes
UNIT_PLAIN = "plain"      # no unit expectations

_MONETARY_SUFFIX_RE = re.compile(r"(CRORES|CRORE|CRS|CR|LAKHS|LAKH|LACS|LAC)$")
_CURRENCY_CHARS_RE = re.compile("[₹$€£,\"'" + _WS_CLASS + "]")
# Rupee words written in front of a price ("Rs 1,500", "Rs. 1,500", "INR 1500").
# Applied after the currency characters and spaces are removed, so the text is
# already upper-cased and closed up. Mirrors CURRENCY_PREFIX_RE in TS.
_CURRENCY_PREFIX_RE = re.compile(r"^(?:RS\.?|INR)")
# The cleaned body must be a plain decimal. This deliberately rejects hex
# (0x10), underscore separators (1_0), "inf" and "nan" -- each of which one
# language's number parser accepts and the other's does not. Digits are spelled
# [0-9] because Python's \d also matches non-ASCII digits (for example U+0663)
# while JavaScript's does not. Pinning the accepted shape here is what keeps
# the two engines in agreement.
_NUMERIC_BODY_RE = re.compile(r"^[+-]?(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?$")


def clean_numeric(value, unit=UNIT_PLAIN):
    """Unit-aware numeric parser shared with cleanNumeric() in screenerEngine.ts.

    unit=UNIT_CRORE   "1 CRORE" -> 1.0, "100 LAKH" -> 1.0, "10 LAKH" -> 0.1
    unit=UNIT_PERCENT "15.5%"   -> 15.5 ; "15 CR" -> None (monetary on percent)
    unit=UNIT_RATIO   "0.42"    -> 0.42 ; "0.42%" -> None ; "1 CR" -> None
    unit=UNIT_PRICE   "Rs 1,500"-> 1500 ; "1500 CR" -> None

    Returns None for anything it cannot interpret under the declared unit.
    Never guesses: an unexpected suffix is a rejection, not a silent strip.
    """
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num = float(value)
        if math.isnan(num) or math.isinf(num):
            return None
        return num

    text = js_trim(str(value).upper())
    if text == "":
        return None

    has_percent = "%" in text
    text_no_currency = _CURRENCY_CHARS_RE.sub("", text).replace("%", "")
    text_no_currency = _CURRENCY_PREFIX_RE.sub("", text_no_currency, count=1)

    multiplier = 1.0
    suffix_match = _MONETARY_SUFFIX_RE.search(text_no_currency)
    has_monetary = suffix_match is not None
    if has_monetary:
        suffix = suffix_match.group(1)
        text_no_currency = text_no_currency[: suffix_match.start()]
        if suffix.startswith("LA"):
            # 100 lakh == 1 crore
            multiplier = 0.01
        else:
            multiplier = 1.0

    if unit == UNIT_CRORE:
        if has_percent:
            return None
    elif unit in (UNIT_PERCENT, UNIT_RATIO, UNIT_PRICE):
        if has_monetary:
            return None
        multiplier = 1.0
        if unit in (UNIT_RATIO, UNIT_PRICE) and has_percent:
            return None
    else:
        multiplier = 1.0

    if not _NUMERIC_BODY_RE.match(text_no_currency):
        return None
    try:
        num = float(text_no_currency)
    except (TypeError, ValueError):
        return None
    if math.isnan(num) or math.isinf(num):
        return None
    return num * multiplier


def js_number_to_string(value):
    """Format a finite number exactly as JavaScript's String(number) does.

    Used wherever a number is embedded in text both engines must emit
    byte-for-byte, such as custom-filter rejection reasons. Python's str()
    differs from JavaScript for integral floats (30.0 vs 30) and in where it
    switches to exponent notation (1e-05 vs 0.00001, 1e+16 vs 10000000000000000).
    repr() already yields the shortest round-trip digits, so only the layout
    rules of ECMAScript Number::toString need reproducing.
    """
    x = float(value)
    if x == 0:
        return "0"
    if x < 0:
        return "-" + js_number_to_string(-x)
    _, digit_tuple, exponent = decimal.Decimal(repr(x)).normalize().as_tuple()
    digits = "".join(str(d) for d in digit_tuple)
    k = len(digits)
    n = exponent + k  # x == 0.<digits> * 10**n
    if k <= n <= 21:
        return digits + "0" * (n - k)
    if 0 < n <= 21:
        return digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return "0." + "0" * (-n) + digits
    e = n - 1
    mantissa = digits if k == 1 else digits[0] + "." + digits[1:]
    return "%se%s%d" % (mantissa, "+" if e >= 0 else "-", abs(e))
# === END SECTION:helpers ===


# === SECTION:csv_safety:Spreadsheet Formula-Injection Guard ===
_DANGEROUS_LEAD = ("=", "+", "-", "@")


def escape_csv_cell(value):
    """Neutralise spreadsheet formula injection in a *string* cell.

    If the first non-whitespace character is = + - or @, prefix an apostrophe.
    Numeric values are returned unchanged so real numeric columns stay numeric
    in the exported file. Mirrors escapeCsvCell() in screenerEngine.ts.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    text = str(value)
    stripped = text.lstrip(_WS_CHARS)
    if stripped[:1] in _DANGEROUS_LEAD:
        return "'" + text
    return text


def write_safe_csv(df, path, numeric_columns=()):
    """Write a DataFrame to CSV with formula-injection protection.

    Columns named in numeric_columns are left as numbers; every other column is
    coerced through escape_csv_cell(). Uses QUOTE_MINIMAL so quoting matches
    the browser exporter.
    """
    numeric = set(numeric_columns)
    safe = df.copy()
    for col in safe.columns:
        if col in numeric:
            continue
        safe[col] = safe[col].map(escape_csv_cell)
    safe.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    return path
# === END SECTION:csv_safety ===


# === SECTION:column_resolution:Identifier-Safe Column Resolution ===
# Ordered alias lists. Rank within a list is preference order; the resolver is
# independent of the order columns happen to appear in the CSV.
COLUMN_ALIASES = {
    "name": ["name", "company name", "company"],
    "sector": ["industry", "sector", "industry/sector"],
    "currentPrice": ["current price", "cmp", "close price", "market price", "price"],
    "marketCap": ["market capitalization", "market cap", "mcap", "mar cap"],
    "salesGrowth": ["sales growth 3years", "sales growth", "sales var 3yrs"],
    "profitGrowth": ["profit growth 3years", "profit growth", "pat growth 3years", "net profit growth"],
    "roce": ["return on capital employed", "roce"],
    "roe": ["return on equity", "roe"],
    "debtToEquity": ["debt to equity", "debt / equity", "debt/equity ratio", "d/e"],
    "interestCoverage": ["interest coverage ratio", "interest coverage", "icr"],
    "operatingCashFlow": [
        "cash flow from operations",
        "cash from operating activity",
        "operating cash flow",
        "cfo",
        "ocf",
    ],
    "promoterHolding": ["promoter holding", "promoter holding %"],
    "promoterPledge": ["pledged percentage", "promoter pledge", "pledge %"],
    "peRatio": ["price to earning", "price to earnings", "price/earnings", "stock p/e", "p/e ratio", "p/e", "pe ratio", "pe"],
    "pbRatio": ["price to book value", "price to book", "p/b ratio", "p/b", "pb ratio", "pb"],
    "dividendYield": ["dividend yield", "div yield"],
    # Optional. Present only in exports that carry an absolute revenue column;
    # "Sales growth 3Years" is a percentage and is a different field.
    "sales": ["sales", "revenue", "total revenue", "total income"],
    # --- Financial-company metrics (banks, NBFCs). Optional everywhere else. ---
    # Screener.in spells these differently across screens, so each carries the
    # spellings seen in the wild; normalize_header() strips the trailing "%".
    "returnOnAssets": ["return on assets", "roa"],
    "grossNpa": ["gross npa", "gross npa percentage"],
    "netNpa": ["net npa", "net npa percentage"],
    "capitalAdequacy": ["capital adequacy ratio", "capital adequacy", "car", "crar"],
    "casa": ["casa", "casa ratio"],
    # Screener.in has no "net interest margin" ratio; "Financing Margin %" is
    # its nearest equivalent and is labelled as such wherever it is reported.
    "financingMargin": ["financing margin", "net interest margin", "nim"],
}

# Identifier fields are resolved separately: an NSE symbol column and a BSE
# scrip-code column must not consume one another, and when only a BSE column
# exists it has to serve as both the bseCode and the ticker fallback.
TICKER_PRIMARY_ALIASES = ["nse code", "nse symbol", "symbol", "ticker", "nse", "code"]
BSE_CODE_ALIASES = ["bse code", "scrip code", "bse id", "bse"]

# Aliases short enough to collide with unrelated words are matched exactly only.
EXACT_ONLY_ALIASES = {
    "pe", "pb", "roe", "roce", "ocf", "cfo", "icr", "d/e", "p/e", "p/b",
    "cmp", "code", "nse", "bse", "price", "company", "name",
    # "sales" would otherwise partial-match "Sales growth 3Years"; "car" would
    # match "Cars", "nim"/"roa"/"casa" are short enough to collide by accident.
    "sales", "roa", "car", "crar", "casa", "nim",
}

FIELD_UNITS = {
    "currentPrice": UNIT_PRICE,
    "marketCap": UNIT_CRORE,
    "operatingCashFlow": UNIT_CRORE,
    "salesGrowth": UNIT_PERCENT,
    "profitGrowth": UNIT_PERCENT,
    "roce": UNIT_PERCENT,
    "roe": UNIT_PERCENT,
    "promoterHolding": UNIT_PERCENT,
    "promoterPledge": UNIT_PERCENT,
    "dividendYield": UNIT_PERCENT,
    "debtToEquity": UNIT_RATIO,
    "interestCoverage": UNIT_RATIO,
    "peRatio": UNIT_RATIO,
    "pbRatio": UNIT_RATIO,
    "sales": UNIT_CRORE,
    "returnOnAssets": UNIT_PERCENT,
    "grossNpa": UNIT_PERCENT,
    "netNpa": UNIT_PERCENT,
    "capitalAdequacy": UNIT_PERCENT,
    "casa": UNIT_PERCENT,
    "financingMargin": UNIT_PERCENT,
}

_ZERO_WIDTH_RE = re.compile(r"[​-‍﻿]")
# Word characters are spelled A-Za-z0-9_ because Python's \w also matches
# accented and other non-ASCII letters while JavaScript's does not.
_NON_WORD_RE = re.compile(r"[^A-Za-z0-9_/" + _WS_CLASS + "]")
_WHITESPACE_RE = re.compile("[" + _WS_CLASS + "]+")


def normalize_header(text):
    """Lowercase, strip zero-width chars and punctuation, collapse whitespace."""
    lowered = js_trim(str(text).lower())
    lowered = _ZERO_WIDTH_RE.sub("", lowered)
    lowered = _NON_WORD_RE.sub("", lowered)
    return js_trim(_WHITESPACE_RE.sub(" ", lowered))


def _match_rank(normalized_header, aliases):
    """Return (kind, rank) for the best alias match, or None.

    kind 0 == exact, kind 1 == word-boundary partial. Lower is better.
    """
    best = None
    for rank, alias in enumerate(aliases):
        alias_norm = normalize_header(alias)
        if not alias_norm:
            continue
        if normalized_header == alias_norm:
            candidate = (0, rank)
        elif alias in EXACT_ONLY_ALIASES:
            continue
        elif re.search(r"\b" + re.escape(alias_norm) + r"\b", normalized_header):
            candidate = (1, rank)
        else:
            continue
        if best is None or candidate < best:
            best = candidate
    return best


def resolve_columns(headers):
    """Map canonical field names to actual CSV column names.

    Deterministic and independent of column order. Identifier resolution
    guarantees:
      * "NSE Code" + "BSE Code"  -> ticker=NSE Code,  bseCode=BSE Code
      * "BSE Code" only          -> ticker=BSE Code,  bseCode=BSE Code (shared)
      * "NSE Code" only          -> ticker=NSE Code,  no bseCode
    Mirrors detectColumnMapping() in screenerEngine.ts.
    """
    headers = list(headers)
    normalized = [normalize_header(h) for h in headers]
    mapping = {}
    claimed = set()

    # --- Identifiers first, so a generic alias cannot steal them. ---
    bse_candidates = []
    ticker_candidates = []
    for idx, norm in enumerate(normalized):
        if not norm:
            continue
        bse_hit = _match_rank(norm, BSE_CODE_ALIASES)
        if bse_hit is not None:
            bse_candidates.append((bse_hit[0], bse_hit[1], idx))
        tick_hit = _match_rank(norm, TICKER_PRIMARY_ALIASES)
        if tick_hit is not None:
            ticker_candidates.append((tick_hit[0], tick_hit[1], idx))

    # A column that matches a BSE alias is not eligible as a primary ticker.
    bse_idxs = {c[2] for c in bse_candidates}
    ticker_primary = [c for c in ticker_candidates if c[2] not in bse_idxs]

    if bse_candidates:
        best_bse = min(bse_candidates)
        mapping["bseCode"] = headers[best_bse[2]]
        claimed.add(best_bse[2])

    if ticker_primary:
        best_tick = min(ticker_primary)
        mapping["ticker"] = headers[best_tick[2]]
        claimed.add(best_tick[2])
    elif "bseCode" in mapping:
        # Only a BSE column exists: share it as the ticker fallback. Both
        # mappings stay available, which is what deduplication relies on.
        mapping["ticker"] = mapping["bseCode"]

    # --- Remaining fields: exact matches everywhere, then partials. ---
    for kind_pass in (0, 1):
        candidates = []
        for field, aliases in COLUMN_ALIASES.items():
            if field in mapping:
                continue
            for idx, norm in enumerate(normalized):
                if not norm or idx in claimed:
                    continue
                hit = _match_rank(norm, aliases)
                if hit is None or hit[0] != kind_pass:
                    continue
                field_order = list(COLUMN_ALIASES).index(field)
                candidates.append((hit[1], field_order, idx, field))
        # Assign greedily in a deterministic order: best alias rank first, then
        # declaration order, then column position.
        for _rank, _order, idx, field in sorted(candidates):
            if field in mapping or idx in claimed:
                continue
            mapping[field] = headers[idx]
            claimed.add(idx)

    return mapping


def parse_row_values(row, mapping):
    """Extract unit-aware numeric fields plus identifiers from one CSV row."""
    def get(field):
        col = mapping.get(field)
        if col is None:
            return None
        return clean_numeric(row.get(col), FIELD_UNITS.get(field, UNIT_PLAIN))

    def get_text(field, default=""):
        col = mapping.get(field)
        if col is None:
            return default
        raw = row.get(col)
        if raw is None:
            return default
        try:
            if pd.isna(raw):
                return default
        except (TypeError, ValueError):
            pass
        return js_trim(raw)

    ticker = get_text("ticker").upper()
    return {
        "ticker": ticker,
        "name": get_text("name", "Unknown") or "Unknown",
        "bseCode": get_text("bseCode").upper() or None,
        "sector": get_text("sector"),
        "currentPrice": get("currentPrice"),
        "marketCap": get("marketCap"),
        "salesGrowth": get("salesGrowth"),
        "profitGrowth": get("profitGrowth"),
        "roce": get("roce"),
        "roe": get("roe"),
        "debtToEquity": get("debtToEquity"),
        "interestCoverage": get("interestCoverage"),
        "operatingCashFlow": get("operatingCashFlow"),
        "promoterHolding": get("promoterHolding"),
        "promoterPledge": get("promoterPledge"),
        "peRatio": get("peRatio"),
        "pbRatio": get("pbRatio"),
        "dividendYield": get("dividendYield"),
        "sales": get("sales"),
        "returnOnAssets": get("returnOnAssets"),
        "grossNpa": get("grossNpa"),
        "netNpa": get("netNpa"),
        "capitalAdequacy": get("capitalAdequacy"),
        "casa": get("casa"),
        "financingMargin": get("financingMargin"),
    }


# Numeric fields compared between two rows for the same company. Any
# disagreement means the export contradicts itself about that company.
DEDUPE_COMPARED_FIELDS = (
    "currentPrice", "marketCap", "salesGrowth", "profitGrowth", "roce", "roe",
    "debtToEquity", "interestCoverage", "operatingCashFlow", "promoterHolding",
    "promoterPledge", "peRatio", "pbRatio", "dividendYield", "sales",
    "returnOnAssets", "grossNpa", "netNpa", "capitalAdequacy", "casa",
    "financingMargin",
)


def _rows_disagree(first, second):
    """True when two rows for one company report different numbers.

    clean_numeric() never yields NaN, so plain inequality is safe here.
    Mirrors rowsDisagree() in screenerEngine.ts.
    """
    for field in DEDUPE_COMPARED_FIELDS:
        if first.get(field) != second.get(field):
            return True
    return False


def dedupe_stocks(stocks):
    """Drop duplicates by ticker, then BSE code, then normalised name.

    The first row seen survives. When a dropped duplicate reports different
    numbers from the survivor, the survivor is marked duplicateConflict, which
    hard_red_flags() turns into a rejection: with two disagreeing rows for one
    company there is no way to tell which is real.

    Byte-for-byte the same rule set as processScreenerPipeline() in
    screenerEngine.ts. Returns (unique_stocks, duplicates_removed).
    """
    by_ticker = {}
    by_bse = {}
    by_name = {}
    unique = []
    duplicates = 0
    for stock in stocks:
        ticker = (stock.get("ticker") or "").upper()
        bse = (stock.get("bseCode") or "").upper()
        raw_name = stock.get("name") or ""
        name_key = re.sub(r"[^A-Z0-9]", "", raw_name.upper())
        is_unknown = (not name_key) or raw_name == "Unknown"

        # Checked in the same order as before, so which rows count as
        # duplicates is unchanged; only the conflict marking is new.
        existing = None
        if ticker and ticker in by_ticker:
            existing = by_ticker[ticker]
        elif bse and bse in by_bse:
            existing = by_bse[bse]
        elif (not is_unknown) and name_key in by_name:
            existing = by_name[name_key]

        if existing is not None:
            duplicates += 1
            if _rows_disagree(existing, stock):
                existing["duplicateConflict"] = True
            continue

        if ticker:
            by_ticker[ticker] = stock
        if bse:
            by_bse[bse] = stock
        if not is_unknown:
            by_name[name_key] = stock
        unique.append(stock)
    return unique, duplicates
# === END SECTION:column_resolution ===


# === SECTION:config:Validated Configuration ===
DEFAULT_APP_CONFIG = {
    "universe_mode": "nifty100",
    "custom_symbols": [],
    "custom_filters": [],
    "top_n": 20,
    "minimum_total_score": 65,
    "fundamentals_stale_after_days": 30,
    "enable_technical_confirmation": True,
    # Off by default: every company that survives the hard red flags is scored
    # and ranked. Turning this on re-applies the old pass/fail hurdles (minimum
    # ROCE, growth, leverage, valuation and so on) as a filter over that ranked
    # list, rather than as the only way to appear in it.
    "strict_screen": False,
}

DEFAULT_SCREENING_CONFIG = {
    "minMarketCapCr": 1000,
    "minSalesGrowthPct": 10.0,
    "minProfitGrowthPct": 12.0,
    "minRocePct": 15.0,
    "minRoePct": 15.0,
    "maxDebtToEquity": 1.0,
    "minInterestCoverage": 3.0,
    "requirePositiveOcf": True,
    "minPromoterHoldingPct": 40.0,
    "maxPromoterPledgePct": 10.0,
    "minPeRatio": 5.0,
    "maxPeRatio": 55.0,
    "maxPbRatio": 12.0,
    "minDividendYieldPct": 0.2,
    "minimum_fundamental_coverage": 80.0,
}

ALLOWED_FILTER_FIELDS = {
    "marketCap", "salesGrowth", "profitGrowth", "roce", "roe", "debtToEquity",
    "interestCoverage", "operatingCashFlow", "promoterHolding",
    "promoterPledge", "peRatio", "pbRatio", "dividendYield",
}
ALLOWED_FILTER_OPS = {">", "<", ">=", "<=", "==", "!="}

# Sector/industry text marking a company as financial-sector. Screener.in has
# many names for them ("Financial - Services", "Capital Markets", "Stock
# Brokers", "Other Financial Services", ...) and the leverage and cash-flow
# rules transfer to none of them. "financ" covers Finance/Financial/Financing/
# Microfinance, "brok" covers broker/broking/brokerage, "insur" insurance and
# insurers. "capital market" is spelled in full so "Capital Goods" is untouched.
# ASCII-only case folding (re.A), exactly as JavaScript's /i behaves: Unicode
# folding would also match the long s (U+017F) as "s".
FINANCIAL_SECTOR_TERMS = (
    "bank", "financ", "nbfc", "insur", "brok", "capital market", "asset management",
    "mutual fund", "depositor", "securities", "stock exchange", "wealth management",
    "lending",
)
FINANCIAL_SECTOR_RE = re.compile("|".join(FINANCIAL_SECTOR_TERMS), re.I | re.A)
_INVERSE_OPS = {">": "<=", "<": ">=", ">=": "<", "<=": ">", "==": "!=", "!=": "=="}
_FILTER_COMPARATORS = {
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}

# --- Sector grouping ------------------------------------------------------
# Coarse groups, used when a Screener.in industry label is too thin to give a
# meaningful median. Screener's labels are fine-grained ("FMCG - Food", "FMCG -
# Household Products", "Metals - Non Ferrous"), so a 100-row export splits into
# roughly 25 industries and most of them hold one or two companies.
#
# ORDER IS LOAD-BEARING. The first group with a matching term wins, so a group
# is listed before any later one whose terms would also match it:
#   "Cables - Power"      -> Industrials (cable), before Utilities (power)
#   "Industrial Minerals" -> Metals & Mining (mineral), before Industrials
#
# Terms match at a word boundary and may be prefixes ("alumini" covers
# aluminium and aluminum, "chemical" covers Chemicals). The leading boundary is
# what stops "oil" matching "boiler" and "port" matching "airport". Every term
# must stay plain lowercase letters and spaces -- no regex metacharacters --
# because the two engines build this pattern without an escaping step.
# Mirrors SECTOR_GROUP_TERMS in screenerEngine.ts.
SECTOR_GROUP_FINANCIALS = "Financials"
SECTOR_GROUP_TERMS = (
    ("Information Technology", ("computers", "software", "information technology",
                                "it services", "bpo")),
    ("Healthcare", ("pharma", "healthcare", "hospital", "diagnostic", "biotech",
                    "medical", "drug")),
    ("Automobile", ("automobile", "auto component", "auto ancillar", "tyre",
                    "two wheeler", "commercial vehicle", "passenger vehicle")),
    ("Metals & Mining", ("metal", "steel", "mining", "mineral", "zinc",
                         "alumini", "copper", "ferrous")),
    ("Construction Materials", ("cement", "tiles", "ceramic", "asbestos")),
    ("Chemicals", ("chemical", "fertilis", "fertiliz", "paint", "plastic", "polymer")),
    ("Energy", ("oil", "gas", "petroleum", "refiner", "coal", "energy")),
    ("Consumer Durables", ("consumer electronic", "consumer durable", "watches",
                           "footwear", "appliance", "furniture", "jewel")),
    ("FMCG", ("fmcg", "beverage", "tobacco", "cigarette", "personal product",
              "household product", "sugar", "dairy")),
    ("Consumer Services", ("retail", "hotel", "restaurant", "travel", "airline",
                           "aviation", "media", "entertainment", "education")),
    ("Telecommunication", ("telecom",)),
    ("Realty", ("realty", "real estate")),
    ("Industrials", ("capital goods", "engineering", "abrasive", "defence",
                     "infrastructure", "cable", "bearing", "compressor",
                     "industrial", "logistic", "port", "trading", "packaging",
                     "construction", "textile", "paper")),
    ("Utilities", ("power", "electric", "utility", "renewable")),
)
_SECTOR_GROUP_RES = tuple(
    (name, re.compile(r"\b(?:" + "|".join(terms) + ")", re.I | re.A))
    for name, terms in SECTOR_GROUP_TERMS
)


def sector_group(sector):
    """Coarse group for a Screener.in industry label, or None if nothing matches.

    Financials is decided by FINANCIAL_SECTOR_RE itself rather than by a
    separate term list, so a company's group can never disagree with whether
    the engine treats it as a financial company. Mirrors sectorGroup() in TS.
    """
    text = sector or ""
    if FINANCIAL_SECTOR_RE.search(text):
        return SECTOR_GROUP_FINANCIALS
    for name, pattern in _SECTOR_GROUP_RES:
        if pattern.search(text):
            return name
    return None


# --- Valuation yardsticks from the loaded file ----------------------------
# Smallest bucket that may serve as a median. Below this the comparison says
# more about the sample than about the company.
MIN_MEDIAN_SAMPLE = 5
_MEDIAN_COUNT_KEYS = {"peRatio": "peCount", "pbRatio": "pbCount"}
_MEDIAN_LABELS = {"peRatio": "P/E", "pbRatio": "P/B"}


def _median(values):
    """Middle value, or the mean of the two middle ones. None when empty."""
    ordered = sorted(values)
    count = len(ordered)
    if count == 0:
        return None
    mid = count // 2
    if count % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _median_bucket(entries):
    return {
        "peRatio": _median(entries["pe"]),
        "pbRatio": _median(entries["pb"]),
        "peCount": len(entries["pe"]),
        "pbCount": len(entries["pb"]),
    }


def sector_medians(stocks):
    """P/E and P/B yardsticks for the loaded file: by industry, by group, overall.

    Only positive ratios feed a median. A negative P/E is a loss and a negative
    P/B is negative net worth; neither is a cheap valuation, and both would drag
    the yardstick the wrong way. Mirrors sectorMedians() in screenerEngine.ts.
    """
    industries, groups = {}, {}
    universe = {"pe": [], "pb": []}
    for stock in stocks:
        industry = js_trim(stock.get("sector") or "")
        group = sector_group(industry)
        pe, pb = stock.get("peRatio"), stock.get("pbRatio")
        buckets = [universe]
        if industry:
            buckets.append(industries.setdefault(industry, {"pe": [], "pb": []}))
        if group:
            buckets.append(groups.setdefault(group, {"pe": [], "pb": []}))
        for bucket in buckets:
            if pe is not None and pe > 0:
                bucket["pe"].append(pe)
            if pb is not None and pb > 0:
                bucket["pb"].append(pb)
    return {
        "byIndustry": {name: _median_bucket(v) for name, v in industries.items()},
        "byGroup": {name: _median_bucket(v) for name, v in groups.items()},
        "universe": _median_bucket(universe),
    }


def valuation_yardstick(medians, sector, metric):
    """(median, basis text) for one metric: industry, else group, else universe.

    A bucket is used only when at least MIN_MEDIAN_SAMPLE companies in it report
    the metric. The basis text always names which bucket was used and why, so a
    fallback can never be mistaken for a true sector comparison. Mirrors
    valuationYardstick() in screenerEngine.ts.
    """
    count_key = _MEDIAN_COUNT_KEYS[metric]
    industry = js_trim(sector or "")
    group = sector_group(industry)
    industry_bucket = medians["byIndustry"].get(industry) or {}
    group_bucket = medians["byGroup"].get(group) or {}

    value = industry_bucket.get(metric)
    count = industry_bucket.get(count_key, 0)
    if value is not None and count >= MIN_MEDIAN_SAMPLE:
        return value, "%s median %s (n=%d)" % (industry, format(round1(value), ".1f"), count)

    group_value = group_bucket.get(metric)
    group_count = group_bucket.get(count_key, 0)
    if group_value is not None and group_count >= MIN_MEDIAN_SAMPLE:
        return group_value, "%s group median %s (industry n=%d)" % (
            group, format(round1(group_value), ".1f"), count)

    universe_value = medians["universe"].get(metric)
    if universe_value is None:
        return None, "no %s yardstick (the file has no positive %s)" % (
            _MEDIAN_LABELS[metric], _MEDIAN_LABELS[metric])
    return universe_value, "universe median %s (group n=%d)" % (
        format(round1(universe_value), ".1f"), group_count)

# Documented range of every numeric setting. Shared with CONFIG_LIMITS in
# screenerEngine.ts -- the browser clamps its inputs to the same bounds -- and
# asserted equal by the cross-engine parity suite.
CONFIG_LIMITS = {
    "top_n": (1, 100),
    "minimum_total_score": (0, 100),
    "fundamentals_stale_after_days": (1, 365),
    "minMarketCapCr": (0, 100000),
    "minSalesGrowthPct": (-100, 100),
    "minProfitGrowthPct": (-100, 100),
    "minRocePct": (0, 100),
    "minRoePct": (0, 100),
    "maxDebtToEquity": (0, 10),
    "minInterestCoverage": (0, 100),
    "minPromoterHoldingPct": (0, 100),
    "maxPromoterPledgePct": (0, 100),
    "minPeRatio": (0, 200),
    "maxPeRatio": (0, 500),
    "maxPbRatio": (0, 100),
    "minDividendYieldPct": (0, 30),
    "minimum_fundamental_coverage": (0, 100),
}
WHOLE_NUMBER_SETTINGS = ("top_n",)
BOOLEAN_SETTINGS = ("enable_technical_confirmation", "requirePositiveOcf", "strict_screen")
UNIVERSE_MODES = ("nifty100", "custom")
CONFIG_SECTIONS = ("schema_version", "app", "screening")
CONFIG_FILENAME = "config.json"


def _json_text(value):
    """JSON text exactly as JavaScript's JSON.stringify writes it.

    json.dumps differs for numbers (JavaScript writes 6.0 as "6"), so numbers
    go through js_number_to_string and non-finite ones become null, as in JS.
    Used for values quoted inside error messages both engines must match.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return js_number_to_string(value) if _is_finite_number(value) else "null"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_json_text(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join("%s:%s" % (json.dumps(str(k), ensure_ascii=False), _json_text(v))
                              for k, v in value.items()) + "}"
    return json.dumps(str(value), ensure_ascii=False)


def _is_finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def normalise_symbols(symbols):
    """Trim, upper-case and drop blank symbols. Mirrors normaliseSymbols() in TS."""
    cleaned = (js_trim(s).upper() for s in (symbols or []))
    return [s for s in cleaned if s]


def validate_custom_filters(filters):
    """Problems with a custom-filter list, as readable strings; empty when valid.

    Only whitelisted fields and operators with a strictly parsed finite number
    are accepted, so a filter can only ever be a numeric comparison. Mirrors
    validateCustomFilters() in screenerEngine.ts.
    """
    errors = []
    for filt in filters or []:
        if not isinstance(filt, dict):
            errors.append("Invalid custom filter: %s" % _json_text(filt))
            continue
        field = filt.get("field")
        op = filt.get("operator")
        if not isinstance(field, str) or field not in ALLOWED_FILTER_FIELDS:
            errors.append("Invalid custom filter field: %s" % _json_text(field))
        elif not isinstance(op, str) or op not in ALLOWED_FILTER_OPS:
            errors.append("Invalid custom filter operator: %s" % _json_text(op))
        elif parse_strict_decimal(filt.get("value")) is None:
            errors.append("Invalid numeric value in custom filter for %s: %s"
                          % (field, _json_text(filt.get("value"))))
    return errors


def _setting_error(section, key, value):
    """Why value is unacceptable for key, or None. Mirrors settingError() in TS."""
    label = "%s.%s" % (section, key)
    if key in CONFIG_LIMITS:
        low, high = CONFIG_LIMITS[key]
        if not _is_finite_number(value):
            return "%s must be a number" % label
        if key in WHOLE_NUMBER_SETTINGS and not float(value).is_integer():
            return "%s must be a whole number" % label
        if not low <= value <= high:
            return "%s must be between %s and %s" % (
                label, js_number_to_string(low), js_number_to_string(high))
        return None
    if key in BOOLEAN_SETTINGS:
        return None if isinstance(value, bool) else "%s must be true or false" % label
    if key == "universe_mode":
        if isinstance(value, str) and value in UNIVERSE_MODES:
            return None
        return "%s must be one of: %s" % (label, ", ".join(UNIVERSE_MODES))
    if key == "custom_symbols":
        if isinstance(value, list) and all(isinstance(s, str) for s in value):
            return None
        return "%s must be a list of symbols" % label
    if key == "custom_filters":
        if not isinstance(value, list):
            return "%s must be a list" % label
        problems = validate_custom_filters(value)
        return "; ".join(problems) if problems else None
    return "Unknown %s setting: %s" % (section, key)


def validate_config_document(document):
    """Validate a saved configuration and merge it over the defaults.

    Returns (app_config, screening_config, errors). Every key is optional and
    an omitted key keeps its default, but unknown sections or keys, wrong types
    and out-of-range values are errors -- never silently clamped -- because a
    config file asking for something the engine will not do must fail loudly.
    Mirrors validateConfigDocument() in screenerEngine.ts.
    """
    app = dict(DEFAULT_APP_CONFIG, custom_symbols=[], custom_filters=[])
    screening = dict(DEFAULT_SCREENING_CONFIG)
    if not isinstance(document, dict):
        return app, screening, ["Configuration must be a JSON object"]
    # Keys are checked in code-point order: JavaScript lists integer-like keys
    # first whatever the file order, so file order cannot be shared.
    errors = ["Unknown configuration section: %s" % key
              for key in sorted(document) if key not in CONFIG_SECTIONS]
    version = document.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        errors.append("Unsupported schema_version %s (expected %s)"
                      % (_json_text(version), SCHEMA_VERSION))
    for section, target in (("app", app), ("screening", screening)):
        values = document.get(section, {})
        if not isinstance(values, dict):
            errors.append("%s must be an object" % section)
            continue
        for key in sorted(values):
            value = values[key]
            if key not in target:
                errors.append("Unknown %s setting: %s" % (section, key))
                continue
            problem = _setting_error(section, key, value)
            if problem:
                errors.append(problem)
            elif key == "custom_symbols":
                target[key] = normalise_symbols(value)
            elif key == "custom_filters":
                target[key] = [dict(f) for f in value]
            elif key in WHOLE_NUMBER_SETTINGS:
                target[key] = int(value)
            else:
                target[key] = value
    # A minimum P/E above the maximum rejects every company, so it is a config
    # error rather than a screen that quietly returns nothing.
    if screening["minPeRatio"] > screening["maxPeRatio"]:
        errors.append("screening.minPeRatio (%s) must not be above screening.maxPeRatio (%s)"
                      % (js_number_to_string(screening["minPeRatio"]),
                         js_number_to_string(screening["maxPeRatio"])))
    return app, screening, errors


def config_document(app_config, screening_config):
    """The canonical saved-configuration shape, as the browser exports it."""
    return {
        "schema_version": SCHEMA_VERSION,
        "app": {key: app_config[key] for key in DEFAULT_APP_CONFIG},
        "screening": {key: screening_config[key] for key in DEFAULT_SCREENING_CONFIG},
    }


def load_config_file(path):
    """Read and validate a saved configuration. Raises ValueError listing every problem."""
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise ValueError("Could not read configuration %s: %s" % (path, exc))
    app, screening, errors = validate_config_document(document)
    if errors:
        raise ValueError("Invalid configuration %s: %s" % (path, "; ".join(errors)))
    return app, screening
# === END SECTION:config ===


# === SECTION:universe:Universe Provider (Nifty 100 & Custom) ===
class UniverseProvider:
    """Resolves the screening universe.

    get_universe() is offline by default and returns the pinned snapshot.
    Pass allow_network=True to attempt a live NSE refresh; failures fall back
    to the snapshot and are reported as cached with their as-of date.
    """

    NIFTY_100_URL = NIFTY100_PROVENANCE.get("source_url", "")

    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir)
        self.cache_file = self.cache_dir / "nifty100_constituents_cache.csv"
        self.last_source = "snapshot"
        self.cache_as_of = None

    def read_cache(self):
        """(symbols, as-of date) from an earlier live refresh, or (None, None).

        The cached file is the NSE CSV itself, so its date is the file's
        modification time. It is used only when it parses, holds 100 unique
        symbols and is newer than the pinned snapshot -- otherwise the snapshot
        is the better list.
        """
        if not self.cache_file.exists():
            return None, None
        try:
            frame = pd.read_csv(self.cache_file, dtype=str, keep_default_na=False)
            symbols = normalise_symbols(frame["Symbol"].tolist())
        except (OSError, ValueError, KeyError):
            return None, None
        if len(set(symbols)) != 100:
            return None, None
        as_of = datetime.date.fromtimestamp(self.cache_file.stat().st_mtime)
        snapshot_date = _parse_iso_date(NIFTY100_PROVENANCE.get("as_of_date", ""))
        if snapshot_date is not None and as_of <= snapshot_date:
            return None, None
        return symbols, as_of

    def snapshot_symbols(self):
        symbols = list(NIFTY100_FALLBACK_SYMBOLS)
        if len(set(symbols)) != 100:
            raise ValueError(
                "Pinned Nifty 100 snapshot is invalid: expected 100 unique "
                "symbols, found %d" % len(set(symbols))
            )
        return symbols

    def describe_source(self):
        if self.last_source == "live":
            return "live NSE index feed"
        if self.last_source == "cache":
            return "cached NSE list, as of %s" % self.cache_as_of.isoformat()
        return "cached snapshot (as of %s)" % NIFTY100_PROVENANCE.get("as_of_date", "unknown")

    def fetch_live(self, timeout=30):
        """Attempt a live refresh. Raises on any failure; never silently fakes."""
        import requests  # imported lazily so offline imports stay clean

        response = requests.get(
            self.NIFTY_100_URL,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"},
        )
        response.raise_for_status()
        frame = pd.read_csv(io.StringIO(response.text))
        if "Symbol" not in frame.columns:
            raise ValueError("NSE feed missing 'Symbol' column")
        symbols = [str(s).strip().upper() for s in frame["Symbol"].tolist() if str(s).strip()]
        if len(set(symbols)) != 100:
            raise ValueError("NSE feed returned %d unique symbols, expected 100" % len(set(symbols)))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        frame.to_csv(self.cache_file, index=False)
        return symbols

    def get_universe(self, mode="nifty100", custom_symbols=None, allow_network=False):
        if mode == "custom":
            return normalise_symbols(custom_symbols)

        if allow_network:
            try:
                symbols = self.fetch_live()
                self.last_source = "live"
                print("Refreshed %d Nifty 100 constituents from the live NSE feed." % len(symbols))
                return symbols
            except Exception as exc:  # noqa: BLE001 - fall back, but say so
                print("Live NSE refresh failed (%s). Falling back to cached snapshot." % exc)

        cached, cache_as_of = self.read_cache()
        if cached is not None:
            self.last_source = "cache"
            self.cache_as_of = cache_as_of
            print("Using CACHED NSE list from %s (as of %s), which is newer than the "
                  "pinned snapshot." % (self.cache_file.name, cache_as_of.isoformat()))
            return cached

        self.last_source = "snapshot"
        symbols = self.snapshot_symbols()
        print(
            "Using CACHED Nifty 100 snapshot (as of %s, sha256 %s...). "
            "This is not a live list; the index is rebalanced periodically."
            % (
                NIFTY100_PROVENANCE.get("as_of_date", "unknown"),
                str(NIFTY100_PROVENANCE.get("sha256_of_source_csv", ""))[:12],
            )
        )
        return symbols
# === END SECTION:universe ===


# === SECTION:fundamentals:Fundamentals Adapter (CSV only) ===
def read_fundamentals_csv(source):
    """Read a fundamentals CSV (a path or a file-like object) as text cells.

    keep_default_na=False stops pandas turning cells such as "NA", "None" or
    "N/A" into blanks -- the browser keeps them as text, and "NA" can be a
    ticker. Empty cells stay empty strings, which both engines treat as missing.
    """
    return pd.read_csv(source, dtype=str, keep_default_na=False)


class FundamentalsAdapter:
    """Loads Screener.in fundamentals exports. CSV only, by design.

    XLSX ingestion was removed: the parser stack it required carried known
    vulnerabilities and the notebook never needed it. Export "CSV" from
    Screener.in instead.
    """

    SUPPORTED_SUFFIXES = (".csv",)

    def __init__(self, fundamentals_dir):
        self.dir = Path(fundamentals_dir)

    def list_available(self):
        if not self.dir.exists():
            return []
        return sorted(
            (p for p in self.dir.iterdir() if p.suffix.lower() in self.SUPPORTED_SUFFIXES),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

    def load(self, path):
        path = Path(path)
        if path.suffix.lower() not in self.SUPPORTED_SUFFIXES:
            raise ValueError(
                "Unsupported fundamentals format '%s'. This engine is CSV-only; "
                "re-export from Screener.in as CSV." % path.suffix
            )
        frame = read_fundamentals_csv(path)
        if frame.empty:
            raise ValueError("Fundamentals file '%s' contains no rows" % path.name)
        return frame


# Column headers that carry the date the data describes.
FUNDAMENTALS_DATE_ALIASES = ("date", "as on", "as of", "as at", "report date", "data date")
_FILENAME_DATE_RE = re.compile(r"([0-9]{4}-[0-9]{2}-[0-9]{2})")


def _parse_iso_date(value):
    """A real YYYY-MM-DD date, or None."""
    text = js_trim(value) if isinstance(value, str) else str(value)
    if not _is_real_date(text):
        return None
    return datetime.date(int(text[:4]), int(text[5:7]), int(text[8:]))


def fundamentals_as_of(frame, path):
    """(date the fundamentals describe, where that date came from).

    In order: a date column inside the export ("Date", "As on", ...), then an
    ISO date in the file name, then the file's modification time. Copying an
    old export resets its timestamp -- which made a months-old file look like
    it was written today -- so the timestamp is the last resort and the source
    is always reported. Mirrors fundamentalsAsOf() in screenerEngine.ts.
    """
    for column in frame.columns:
        if normalize_header(column) in FUNDAMENTALS_DATE_ALIASES:
            dates = [d for d in (_parse_iso_date(v) for v in frame[column]) if d is not None]
            if dates:
                return max(dates), "data date"
    match = _FILENAME_DATE_RE.search(Path(path).name)
    if match:
        from_name = _parse_iso_date(match.group(1))
        if from_name is not None:
            return from_name, "file name"
    return datetime.date.fromtimestamp(Path(path).stat().st_mtime), "file timestamp"


def fundamentals_age_days(frame, path):
    """(age in days, where the date came from). See fundamentals_as_of()."""
    as_of, source = fundamentals_as_of(frame, path)
    return (datetime.date.today() - as_of).days, source
# === END SECTION:fundamentals ===


# === SECTION:technicals:Technical Indicators & Price History ===
SESSIONS_52_WEEK = 252
SESSIONS_6_MONTH = 126
# Price history is anchored to a start date rather than a yfinance "period",
# because that vocabulary has no value between 10y and max, and the backtest
# needs a decade-plus with a fixed, reproducible beginning. Everything that
# threads this value treats it as an opaque window key: it is folded into the
# cache key, so changing it retires every previously cached price file instead
# of serving an 18-month file under an 11-year name.
HISTORY_START = "2015-01-01"
BENCHMARK_SYMBOL = "^NSEI"   # Nifty 50: the relative-strength benchmark
# Open, High and Low were added so true range, ATR and ADX can be computed
# honestly instead of being approximated from closes. Readers treat all three as
# optional: a four-column Date,Ticker,Close,Volume file written by an earlier
# version still loads, and the indicators that need a high and a low report
# themselves unavailable on it rather than substituting the close.
PRICE_HISTORY_COLUMNS = ["Date", "Ticker", "Open", "High", "Low", "Close", "Volume"]
_ISO_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_BSE_CODE_RE = re.compile(r"^[0-9]+$")
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_real_date(text):
    """YYYY-MM-DD naming a real Gregorian date. Mirrors isRealDate() in TS.

    Plain arithmetic rather than datetime, so both engines agree for every
    year (JavaScript's Date maps years 0-99 onto 1900-1999).
    """
    if not _ISO_DATE_RE.match(text):
        return False
    year, month, day = int(text[:4]), int(text[5:7]), int(text[8:])
    if not 1 <= month <= 12:
        return False
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    return 1 <= day <= _MONTH_DAYS[month - 1] + (1 if month == 2 and leap else 0)

TECHNICAL_INDICATOR_KEYS = ("sma50", "sma200", "smaCross", "relativeStrength6M", "high52Week")


def empty_technicals(source="unavailable"):
    return {
        "currentPrice": None,
        "sma50": None,
        "sma200": None,
        "isAboveSma50": None,
        "isAboveSma200": None,
        "isSma50Above200": None,
        "relativeStrength6M": None,
        "volumeRatio20D": None,
        "distFrom52WHighPct": None,
        "volatility30D": None,
        "high52Week": None,
        "source": source,
        "as_of": None,
        "history_rows": 0,
        "available": {key: False for key in TECHNICAL_INDICATOR_KEYS},
        "data_status": "UNAVAILABLE",
    }


def _finite_or_nan(value):
    """A finite float, else NaN. Strings are NaN, exactly as finiteOrNaN() treats them."""
    if value is None or isinstance(value, (bool, str)):
        return float("nan")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float("nan")
    return number if math.isfinite(number) else float("nan")


def _align_to_end(values, length, pad):
    """Right-align values to length entries (the latest sessions line up)."""
    out = [pad] * length
    values = list(values)
    for offset in range(1, min(length, len(values)) + 1):
        out[length - offset] = values[len(values) - offset]
    return out


def _sequential_mean(values):
    """Left-to-right float sum divided by n: bit-identical to the TS reduce().

    Built-in sum() is deliberately avoided. Since Python 3.12 it compensates
    float rounding, so it can differ from JavaScript in the last bit -- and a
    last-bit difference is enough to flip a price-versus-SMA comparison on a
    flat price series.
    """
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def compute_technical_indicators(price_series, bench_series=None, volume_series=None,
                                 source="injected", dates=None, highs=None, lows=None):
    """Pure indicator computation. No network, no globals. Mirrors computeTechnicalIndicators().

    Inputs are position-aligned: bench_series[i] and volume_series[i] belong to
    the session of price_series[i], with None/NaN where a value is absent.
    Sequences of different lengths are aligned at their most recent end. A
    pandas Series with a DatetimeIndex is also accepted; the benchmark and
    volume series are then aligned to its dates by label.

    Availability is explicit per indicator:
      sma50               needs >= 50 sessions
      sma200              needs >= 200 sessions
      smaCross            needs both SMAs
      relativeStrength6M  needs >= 126 sessions where stock and benchmark both trade
      high52Week          needs >= 252 sessions (a genuine 52-week window)

    A 200-session maximum is NOT a 52-week high: with fewer than 252 valid
    sessions high52Week/distFrom52WHighPct stay None and score zero points.

    data_status is COMPLETE only when every indicator above is available,
    PARTIAL when some are, UNAVAILABLE when there is no usable history.
    """
    tech = empty_technicals(source=source)
    if price_series is None:
        return tech
    if isinstance(price_series, pd.Series):
        index = price_series.index
        if dates is None and isinstance(index, pd.DatetimeIndex):
            dates = [stamp.strftime("%Y-%m-%d") for stamp in index]
        if isinstance(bench_series, pd.Series):
            bench_series = bench_series.reindex(index)
        if isinstance(volume_series, pd.Series):
            volume_series = volume_series.reindex(index)
        price_series = price_series.tolist()

    closes = [_finite_or_nan(v) for v in price_series]
    n = len(closes)
    valid = [i for i in range(n) if not math.isnan(closes[i])]
    if not valid:
        return tech
    prices = [closes[i] for i in valid]
    current = prices[-1]
    tech["history_rows"] = len(prices)
    tech["currentPrice"] = current
    if dates is not None:
        tech["as_of"] = _align_to_end(dates, n, None)[valid[-1]]

    if len(prices) >= 50:
        sma50 = _sequential_mean(prices[-50:])
        tech["sma50"] = sma50
        tech["isAboveSma50"] = current > sma50
        tech["available"]["sma50"] = True

    if len(prices) >= 200:
        sma200 = _sequential_mean(prices[-200:])
        tech["sma200"] = sma200
        tech["isAboveSma200"] = current > sma200
        tech["available"]["sma200"] = True
        if tech["sma50"] is not None:
            tech["isSma50Above200"] = tech["sma50"] > sma200
            tech["available"]["smaCross"] = True

    # 52-week high: a full 252-session window, over the last 252 valid sessions only.
    if len(prices) >= SESSIONS_52_WEEK:
        high = max(prices[-SESSIONS_52_WEEK:])
        tech["high52Week"] = high
        if high > 0:
            tech["distFrom52WHighPct"] = ((current - high) / high) * 100.0
            tech["available"]["high52Week"] = True

    # Annualised volatility of up to the last 30 daily returns (needs 20).
    returns = []
    for i in range(max(1, len(prices) - 30), len(prices)):
        if prices[i - 1] != 0:
            returns.append(prices[i] / prices[i - 1] - 1)
    if len(returns) >= 20:
        mean = _sequential_mean(returns)
        squares = 0.0
        for value in returns:
            deviation = value - mean
            squares += deviation * deviation
        variance = squares / (len(returns) - 1)
        tech["volatility30D"] = math.sqrt(variance) * math.sqrt(SESSIONS_52_WEEK) * 100.0

    # Volume on the latest session against the mean of the last 20 sessions
    # that report volume, up to and including it. A blank latest volume gives
    # no ratio rather than quietly using an older session's volume as "today".
    if volume_series is not None:
        volumes = _align_to_end([_finite_or_nan(v) for v in volume_series], n, float("nan"))
        latest = volumes[valid[-1]]
        window = [v for v in volumes[:valid[-1] + 1] if not math.isnan(v)][-20:]
        if not math.isnan(latest) and len(window) >= 20:
            average = _sequential_mean(window)
            if average > 0:
                tech["volumeRatio20D"] = latest / average

    if bench_series is not None:
        bench = _align_to_end([_finite_or_nan(v) for v in bench_series], n, float("nan"))
        pairs = [(closes[i], bench[i]) for i in valid if not math.isnan(bench[i])]
        if len(pairs) >= SESSIONS_6_MONTH:
            past_stock, past_bench = pairs[-SESSIONS_6_MONTH]
            curr_stock, curr_bench = pairs[-1]
            if past_stock != 0 and past_bench != 0:
                stock_ret = (curr_stock - past_stock) / past_stock
                bench_ret = (curr_bench - past_bench) / past_bench
                tech["relativeStrength6M"] = (stock_ret - bench_ret) * 100.0
                tech["available"]["relativeStrength6M"] = True

    available_count = sum(1 for key in TECHNICAL_INDICATOR_KEYS if tech["available"][key])
    if available_count == len(TECHNICAL_INDICATOR_KEYS):
        tech["data_status"] = "COMPLETE"
    elif available_count > 0:
        tech["data_status"] = "PARTIAL"
    else:
        tech["data_status"] = "UNAVAILABLE"
    return tech


def calculate_technical_score(tech, is_enabled):
    """Per-indicator technical score. Mirrors calculateTechnicalScore() in TS.

    tech is None when the run had no price history at all. That is a fact
    about the run, reported once by the pipeline, so it raises no per-stock
    warning. An UNAVAILABLE record means history was loaded but this stock is
    not in it, and that IS flagged. Points are awarded only for indicators that
    are actually available, so an absent 52-week high contributes zero rather
    than a spurious bonus. Returns (score_or_None, breakdown, warnings).
    """
    if not is_enabled:
        return None, ["Technical screening disabled"], []
    if tech is None:
        return None, ["No price history loaded"], []
    if tech.get("data_status") == "UNAVAILABLE":
        rows = tech.get("history_rows") or 0
        reason = ("Only %d sessions of price history; indicators need at least 50" % rows
                  if rows else "Technical data unavailable")
        return None, [reason], ["Technical Data Missing"]

    avail = tech.get("available", {})
    score = 0
    breakdown = []
    warnings_out = []

    if avail.get("sma200") and tech.get("isAboveSma200"):
        score += 30
        breakdown.append("Price > 200 SMA (+30)")
    if avail.get("sma50") and tech.get("isAboveSma50"):
        score += 20
        breakdown.append("Price > 50 SMA (+20)")
    if avail.get("smaCross") and tech.get("isSma50Above200"):
        score += 20
        breakdown.append("50 SMA > 200 SMA (+20)")
    if avail.get("relativeStrength6M"):
        rs = tech.get("relativeStrength6M")
        if rs is not None and rs > 0:
            score += 15
            breakdown.append("Positive 6M RS vs benchmark (+15)")
    if avail.get("high52Week"):
        dist = tech.get("distFrom52WHighPct")
        if dist is not None and dist > -15:
            score += 15
            breakdown.append("Within 15% of 52W high (+15)")
    else:
        breakdown.append("52W high unavailable (needs %d sessions) (+0)" % SESSIONS_52_WEEK)

    if tech.get("data_status") != "COMPLETE":
        missing = [k for k in TECHNICAL_INDICATOR_KEYS if not avail.get(k)]
        warnings_out.append("Technical Data Partial (%s)" % ", ".join(missing))

    return round1(clamp(score, 0, 100)), breakdown, warnings_out


def yahoo_symbol(ticker):
    """Yahoo Finance symbol for a screener ticker: NSE symbols get .NS, BSE codes .BO."""
    symbol = js_trim(ticker).upper()
    if symbol.startswith("^") or symbol.endswith((".NS", ".BO")):
        return symbol
    return symbol + (".BO" if _BSE_CODE_RE.match(symbol) else ".NS")


def _value_at(series, stamp):
    """One session's value from a yfinance column, or NaN when absent."""
    return _finite_or_nan(series.get(stamp)) if series is not None else float("nan")


def price_history_rows_from_download(frame, tickers):
    """Flatten a yfinance download into sorted rows.

    Each row is (date, ticker, open, high, low, close, volume). yfinance labels
    columns (field, symbol) -- or (symbol, field) with group_by="ticker". Each
    Yahoo symbol is mapped back to its screener ticker; the benchmark keeps
    BENCHMARK_SYMBOL. Sessions without a finite close are dropped rather than
    filled; a session missing only its open, high or low keeps the close and
    leaves those blank, so one gap never discards a whole session.
    """
    wanted = {yahoo_symbol(t): js_trim(t).upper() for t in tickers}
    wanted[BENCHMARK_SYMBOL] = BENCHMARK_SYMBOL
    if frame is None or len(frame) == 0:
        return []
    columns = frame.columns
    if isinstance(columns, pd.MultiIndex):
        field_level = 0 if "Close" in set(columns.get_level_values(0)) else 1

        def column(field, symbol):
            key = (field, symbol) if field_level == 0 else (symbol, field)
            return frame[key] if key in columns else None
    else:
        raise ValueError("expected per-symbol columns in the price download, got %s"
                         % list(columns)[:5])

    rows = []
    for symbol, ticker in wanted.items():
        closes = column("Close", symbol)
        if closes is None:
            continue
        opens = column("Open", symbol)
        highs = column("High", symbol)
        lows = column("Low", symbol)
        volumes = column("Volume", symbol)
        for stamp, close in closes.items():
            close = _finite_or_nan(close)
            if math.isnan(close):
                continue
            rows.append((
                pd.Timestamp(stamp).strftime("%Y-%m-%d"), ticker,
                _value_at(opens, stamp), _value_at(highs, stamp),
                _value_at(lows, stamp), close, _value_at(volumes, stamp),
            ))
    rows.sort(key=lambda row: (row[1], row[0]))
    return rows


def _price_cell(value):
    """Shortest text that round-trips a price, or blank when the session has none."""
    return "" if math.isnan(value) else repr(float(value))


def _volume_cell(value):
    """Volume as a whole number where it is one, blank when absent."""
    if math.isnan(value):
        return ""
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def price_history_to_csv(rows):
    """Render rows as Date,Ticker,Open,High,Low,Close,Volume text.

    Prices use repr(), the shortest text that round-trips, so both engines parse
    back exactly the double that was downloaded. An absent open, high or low is
    written blank rather than as a copy of the close.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(PRICE_HISTORY_COLUMNS)
    for date, ticker, open_price, high, low, close, volume in rows:
        writer.writerow([
            date, ticker, _price_cell(open_price), _price_cell(high),
            _price_cell(low), repr(float(close)), _volume_cell(volume),
        ])
    return buffer.getvalue()


def parse_price_history_csv(text):
    """Parse Date,Ticker,Close[,Volume] text into per-ticker series.

    Returns (history, skipped). history maps ticker -> {"dates", "closes",
    "volumes"}, each sorted by date. Headers are matched case-insensitively and
    "Symbol" is accepted for Ticker. Rows with a malformed date, a blank ticker
    or a non-numeric close are skipped and counted; a later row for the same
    ticker and date replaces an earlier one. Mirrors parsePriceHistoryCsv().
    """
    if text[:1] == chr(0xFEFF):
        text = text[1:]
    # One rule for both engines: \r\n and a lone \r both end a line, and only
    # commas separate fields (the browser would otherwise sniff both).
    try:
        rows = list(csv.reader(io.StringIO(re.sub(r"\r\n?", "\n", text)), delimiter=","))
    except csv.Error as exc:
        raise ValueError("Price history CSV could not be parsed: %s" % exc)
    names = [js_trim(cell).lower() for cell in (rows[0] if rows else [])]

    def find(*aliases):
        for alias in aliases:
            if alias in names:
                return names.index(alias)
        return None

    date_col, ticker_col = find("date"), find("ticker", "symbol")
    close_col, volume_col = find("close"), find("volume")
    # Optional: a file written before the OHLCV widening has none of these, and
    # the indicators that need a high and a low then report unavailable.
    open_col, high_col, low_col = find("open"), find("high"), find("low")
    if date_col is None or ticker_col is None or close_col is None:
        raise ValueError("Price history CSV needs Date, Ticker and Close columns (Volume is optional)")

    points_by_ticker = {}
    skipped = 0
    for row in rows[1:]:
        if not js_trim("".join(row)):
            continue

        def cell(index):
            return row[index] if index is not None and index < len(row) else ""

        date = js_trim(cell(date_col))
        ticker = js_trim(cell(ticker_col)).upper()
        close = parse_strict_decimal(cell(close_col))
        if not _is_real_date(date) or not ticker or close is None:
            skipped += 1
            continue
        points_by_ticker.setdefault(ticker, {})[date] = (
            close,
            parse_strict_decimal(cell(volume_col)),
            parse_strict_decimal(cell(open_col)),
            parse_strict_decimal(cell(high_col)),
            parse_strict_decimal(cell(low_col)),
        )

    history = {}
    for ticker, points in points_by_ticker.items():
        ordered = sorted(points)
        history[ticker] = {
            "dates": ordered,
            "closes": [points[d][0] for d in ordered],
            "volumes": [points[d][1] for d in ordered],
            "opens": [points[d][2] for d in ordered],
            "highs": [points[d][3] for d in ordered],
            "lows": [points[d][4] for d in ordered],
        }
    return history, skipped


def technicals_from_history(history, tickers):
    """Indicators for each ticker from a parsed price history. Mirrors technicalsFromHistory().

    The benchmark is aligned to each stock's own dates, so relative strength
    compares the two over sessions where both actually traded.
    """
    history = history or {}
    bench = history.get(BENCHMARK_SYMBOL)
    bench_by_date = dict(zip(bench["dates"], bench["closes"])) if bench else None
    out = {}
    for ticker in tickers:
        entry = history.get(ticker)
        if entry is None:
            out[ticker] = empty_technicals(source="not in price history")
            continue
        bench_aligned = None
        if bench_by_date is not None:
            bench_aligned = [bench_by_date.get(d) for d in entry["dates"]]
        out[ticker] = compute_technical_indicators(
            entry["closes"], bench_aligned, entry["volumes"],
            source="price history", dates=entry["dates"],
            highs=entry.get("highs"), lows=entry.get("lows"),
        )
    return out


class MarketDataProvider:
    """Daily price history via yfinance, cached as a price-history CSV.

    Network use is opt-in and injectable: pass downloader=<callable> returning
    a yfinance-shaped frame to supply history in tests. The default downloader
    is imported only when a download actually happens. The cached file is the
    same Date,Ticker,Close,Volume format the browser accepts, so uploading it
    there reproduces this run's technical scores exactly.
    """

    def __init__(self, cache_dir, downloader=None):
        self.cache_dir = Path(cache_dir)
        self.downloader = downloader

    def cache_key(self, symbols, period, schema_version=SCHEMA_VERSION):
        payload = json.dumps(
            {"symbols": sorted(symbols), "period": period, "schema": schema_version},
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _default_downloader(self, symbols, period):
        import yfinance as yf  # lazy: keeps offline imports clean

        # start= rather than period=: yfinance offers no period between "10y"
        # and "max". auto_adjust folds splits and dividends into every OHLC
        # field, so the highs and lows stay consistent with the closes.
        return yf.download(
            [yahoo_symbol(s) for s in symbols] + [BENCHMARK_SYMBOL], start=period,
            interval="1d", auto_adjust=True, progress=False, group_by="column",
        )

    def fetch(self, symbols, period=HISTORY_START):
        downloader = self.downloader or self._default_downloader
        return downloader(symbols, period)

    def cache_path(self, tickers, period, day):
        return self.cache_dir / ("price_history_%s_%s.csv"
                                 % (day.strftime("%Y%m%d"), self.cache_key(tickers, period)[:12]))

    def load_price_history(self, tickers, allow_network, period=HISTORY_START, today=None):
        """Return (history, path, description); history is None when nothing usable exists.

        A file counts only if it prices at least one of the tickers -- a
        benchmark-only file is useless, and the browser rejects one too.
        Today's cached file is reused as-is when it covers every ticker.
        Otherwise, with network access, prices are downloaded again; the
        download replaces today's file only if it covers at least as many
        tickers, and the newest earlier file wins whenever it covers more. So a
        partial (for example rate-limited) download never hides a more complete
        one. The description records which file was used and why.
        """
        tickers = sorted(set(tickers))
        wanted = len(tickers)
        day = today or datetime.date.today()
        stamp = day.strftime("%Y%m%d")
        today_path = self.cache_path(tickers, period, day)

        def covering(history):
            return sum(1 for t in tickers if t in history) if history else 0

        def usable(path, description):
            history = self._read(path)
            return (covering(history), history, path, description) if covering(history) else None

        best = usable(today_path, "cached earlier today") if today_path.exists() else None
        if best and best[0] == wanted:
            return best[1:]

        problem = "offline run"
        if allow_network:
            try:
                rows = price_history_rows_from_download(self.fetch(tickers, period), tickers)
            except Exception as exc:  # noqa: BLE001 - reported, then fall back to cache
                rows, problem = [], "the download failed (%s)" % exc
            else:
                problem = "the download had no prices for these tickers"
            text = price_history_to_csv(rows) if rows else ""
            fresh = parse_price_history_csv(text)[0] if rows else {}
            covered = covering(fresh)
            if 0 < covered < wanted:
                problem = "today's download priced only %d of %d tickers" % (covered, wanted)
            if covered and (best is None or covered >= best[0]):
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                today_path.write_text(text, encoding="utf-8")
                note = "" if covered == wanted else " (%d of %d tickers)" % (covered, wanted)
                best = (covered, fresh, today_path, "downloaded" + note)

        if best is None or best[0] < wanted:
            key = self.cache_key(tickers, period)[:12]
            earlier = sorted(
                p for p in (self.cache_dir.glob("price_history_*_%s.csv" % key) if self.cache_dir.exists() else [])
                if p.name.split("_")[2] < stamp
            )
            if earlier:
                when = earlier[-1].name.split("_")[2]
                older = usable(earlier[-1], "cached on %s-%s-%s, because %s"
                               % (when[:4], when[4:6], when[6:], problem))
                if older and (best is None or older[0] > best[0]):
                    best = older
        if best is None:
            return None, None, problem
        return best[1], best[2], best[3]

    @staticmethod
    def _read(path):
        """Parsed history from a cached file, or None if it is unreadable or malformed."""
        try:
            return parse_price_history_csv(Path(path).read_text(encoding="utf-8"))[0]
        except (OSError, ValueError):
            return None
# === END SECTION:technicals ===


# === SECTION:engine:Core Screening Engine ===
COVERAGE_FIELDS_BASE = [
    "marketCap", "salesGrowth", "profitGrowth", "roce", "roe",
    "operatingCashFlow", "peRatio", "pbRatio", "promoterHolding",
]
COVERAGE_FIELDS_NON_FINANCIAL = ["debtToEquity", "interestCoverage"]

WATCHLIST_NUMERIC_COLUMNS = (
    "Rank", "CurrentPrice", "MarketCapCr", "Score", "TechScore", "Coverage",
    "FinancialQuality", "Growth", "BalanceSheet", "Valuation", "Governance",
)

# --- Financial-company metrics -------------------------------------------
# Banks and NBFCs are scored on their own model rather than excluded, but only
# when the export actually carries the metrics that model needs. Without them a
# lender is reported as "not scored" rather than scored wrongly on ratios that
# do not describe it.
#
# CASA and financing margin are deliberately NOT scored, only reported: an NBFC
# has no CASA at all, so awarding points for it would penalise every NBFC for
# being an NBFC. Mirrors the same constants in screenerEngine.ts.
BANK_REQUIRED_FIELDS = ("returnOnAssets", "grossNpa", "netNpa", "capitalAdequacy")
BANK_OPTIONAL_FIELDS = ("casa", "financingMargin")
BANK_FIELD_LABELS = {
    "returnOnAssets": "Return on assets",
    "grossNpa": "Gross NPA %",
    "netNpa": "Net NPA %",
    "capitalAdequacy": "Capital adequacy ratio",
    "casa": "CASA %",
    "financingMargin": "Financing margin %",
}


def bank_metric_gaps(stock):
    """Required financial-company metrics this row does not carry, in order.

    Non-empty means the company cannot be scored on the financial model.
    Mirrors bankMetricGaps() in screenerEngine.ts.
    """
    return [BANK_FIELD_LABELS[f] for f in BANK_REQUIRED_FIELDS if stock.get(f) is None]


def hard_red_flags(stock, sc, is_financial, coverage):
    """Reasons a company's numbers cannot be trusted, in a fixed order.

    A non-empty list rejects the company outright and stops it being scored.
    These are not "unattractive" findings -- an expensive stock still gets a
    score -- they are "this row is not usable as evidence". Mirrors
    hardRedFlags() in screenerEngine.ts.
    """
    flags = []
    mcap = stock.get("marketCap")
    ph = stock.get("promoterHolding")
    pp = stock.get("promoterPledge")
    pb = stock.get("pbRatio")
    de = stock.get("debtToEquity")
    ocf = stock.get("operatingCashFlow")
    sales = stock.get("sales")

    # 1. Negative net worth. P/B and D/E change sign, not magnitude, so a
    #    "cheap" P/B of -0.3 is insolvency rather than a bargain.
    if (pb is not None and pb < 0) or (de is not None and de < 0):
        flags.append("Negative net worth")
    # 2. Pledged promoter stake above the configured limit.
    if pp is not None and pp > sc["maxPromoterPledgePct"]:
        flags.append("High Promoter Pledge")
    # 3. Operating cash flow, for NON-FINANCIAL companies only. For a bank or
    #    NBFC a negative OCF is ordinary -- a growing loan book consumes cash --
    #    so applying this rule to lenders would reject the healthy ones.
    if sc.get("requirePositiveOcf") and not is_financial:
        if ocf is None:
            flags.append("OCF missing")
        elif ocf <= 0:
            flags.append("Negative OCF")
    # 4. Too little of the row is present to score it honestly.
    if coverage < sc["minimum_fundamental_coverage"]:
        flags.append("Insufficient Data (%s%%)" % format(round1(coverage), ".1f"))
    # 5. Revenue of zero or less: every growth rate and margin divides by it.
    #    Checked only when the export carries an absolute revenue column.
    if sales is not None and sales <= 0:
        flags.append("Non-positive Sales")
    # 6. Impossible shareholding percentages mean the row itself is corrupt.
    if ph is not None and not 0 <= ph <= 100:
        flags.append("Impossible Promoter Holding")
    if pp is not None and not 0 <= pp <= 100:
        flags.append("Impossible Promoter Pledge")
    # 7. A company cannot be worth nothing and still be listed.
    if mcap is not None and mcap <= 0:
        flags.append("Non-positive Market Cap")
    # 8. Internally contradictory: a promoter cannot pledge a stake it does not
    #    hold. This replaces a "P/B < 0 while book value > 0" check, which would
    #    need a book-value column the Screener.in export does not carry.
    if pp is not None and pp > 0 and ph is not None and ph == 0:
        flags.append("Pledge without promoter holding")
    # 9. Two rows for the same company disagreed on their numbers, so there is
    #    no way to tell which one is real. Set by dedupe_stocks().
    if stock.get("duplicateConflict"):
        flags.append("Conflicting duplicate rows")
    return flags


# Coverage for a financial company counts the metrics its own model uses,
# instead of the leverage and interest-cover columns that do not describe one.
COVERAGE_FIELDS_FINANCIAL = list(BANK_REQUIRED_FIELDS)

ZERO_PARTS = {
    "financialQuality": 0.0, "growth": 0.0, "balanceSheetSafety": 0.0,
    "valuation": 0.0, "governance": 0.0,
}


def _award(label, value, unit, awarded):
    """One scored line: "ROCE 25.0% (+15.0)". Mirrors award() in TS."""
    return "%s %s%s (+%s)" % (label, format(round1(value), ".1f"), unit,
                              format(round1(awarded), ".1f"))


def _valuation_points(stock, medians, lines):
    """Sector-relative valuation, worth 10 for P/E and 5 for P/B.

    A ratio of half the yardstick earns full marks, the yardstick itself earns
    half, and half again above it earns nothing. Judging against the sector is
    the point: a P/E of 30 is dear for a bank and cheap for a fast-growing
    software company. Mirrors valuationPoints() in screenerEngine.ts.
    """
    total = 0.0
    for metric, label, cap in (("peRatio", "P/E", 10.0), ("pbRatio", "P/B", 5.0)):
        value = stock.get(metric)
        yardstick, basis = valuation_yardstick(medians, stock.get("sector"), metric)
        if value is None:
            lines.append("%s missing, so no valuation points (+0.0)" % label)
            continue
        if value <= 0:
            lines.append("%s %s is not meaningful, so no valuation points (+0.0)"
                         % (label, format(round1(value), ".1f")))
            continue
        if yardstick is None or yardstick <= 0:
            lines.append("%s %s: %s (+0.0)" % (label, format(round1(value), ".1f"), basis))
            continue
        awarded = clamp(cap * (1.5 - value / yardstick), 0, cap)
        total += awarded
        lines.append("%s %s vs %s (+%s)" % (label, format(round1(value), ".1f"), basis,
                                            format(round1(awarded), ".1f")))
    return total


def _growth_points(stock, lines):
    """Growth, worth 25. Shared by both scoring models."""
    total = 0.0
    for metric, label in (("salesGrowth", "Sales growth"), ("profitGrowth", "Profit growth")):
        value = stock.get(metric)
        if value is None:
            lines.append("%s missing (+0.0)" % label)
        elif value <= 0:
            lines.append("%s %s%% (+0.0)" % (label, format(round1(value), ".1f")))
        else:
            awarded = clamp((value / 15.0) * 12.5, 0, 12.5)
            total += awarded
            lines.append(_award(label, value, "%", awarded))
    return clamp(total, 0, 25)


def _governance_points(stock, lines):
    """Governance, worth 10. Shared by both scoring models."""
    total = 0.0
    ph = stock.get("promoterHolding")
    pp = stock.get("promoterPledge")
    if ph is None:
        lines.append("Promoter holding missing (+0.0)")
    elif ph <= 0:
        # A genuine zero. ITC, L&T, HDFC Bank and ICICI Bank are professionally
        # managed with no promoter at all, so this earns no points -- but it is
        # a published figure, not an absent one, and must not be called missing.
        lines.append(_award("Promoter holding", ph, "%", 0.0))
    else:
        awarded = clamp((ph / 75.0) * 5.0, 0, 5)
        total += awarded
        lines.append(_award("Promoter holding", ph, "%", awarded))
    if pp is None:
        lines.append("Promoter pledge missing (+0.0)")
    elif pp == 0:
        total += 5.0
        lines.append("No promoter pledge (+5.0)")
    else:
        awarded = clamp(5.0 - pp, 0, 5)
        total += awarded
        lines.append(_award("Promoter pledge", pp, "%", awarded))
    return clamp(total, 0, 10)


def score_general(stock, sc, medians):
    """Graded sub-scores for a non-financial company: 30/25/20/15/10.

    Returns (parts, lines) where every awarded point carries a reason line.
    Mirrors scoreGeneral() in screenerEngine.ts.
    """
    lines = []
    quality = 0.0
    for metric, label in (("roce", "ROCE"), ("roe", "ROE")):
        value = stock.get(metric)
        if value is None:
            lines.append("%s missing (+0.0)" % label)
        elif value <= 0:
            # Reported and genuinely zero or negative: worth no points, but a
            # fact about the company rather than a gap in the export.
            lines.append(_award(label, value, "%", 0.0))
        else:
            awarded = clamp((value / 20.0) * 15.0, 0, 15)
            quality += awarded
            lines.append(_award(label, value, "%", awarded))

    safety = 0.0
    de = stock.get("debtToEquity")
    if de is None:
        lines.append("Debt/Equity missing (+0.0)")
    elif de < 0:
        # Unreachable in practice: a negative D/E is negative net worth, a hard
        # red flag that stops scoring before this point.
        lines.append(_award("D/E", de, "", 0.0))
    else:
        # Zero debt is the best possible case and earns the full ten.
        awarded = clamp(10.0 - de * 5.0, 0, 10)
        safety += awarded
        lines.append(_award("D/E", de, "", awarded))
    icr = stock.get("interestCoverage")
    if icr is None:
        lines.append("Interest coverage missing (+0.0)")
    elif icr <= 0:
        # No operating profit to cover interest at all: a real reported figure
        # that earns nothing.
        lines.append(_award("Interest cover", icr, "x", 0.0))
    else:
        awarded = clamp((icr / 5.0) * 10.0, 0, 10)
        safety += awarded
        lines.append(_award("Interest cover", icr, "x", awarded))

    return {
        "financialQuality": clamp(quality, 0, 30),
        "growth": _growth_points(stock, lines),
        "balanceSheetSafety": clamp(safety, 0, 20),
        "valuation": clamp(_valuation_points(stock, medians, lines), 0, 15),
        "governance": _governance_points(stock, lines),
    }, lines


def score_financial(stock, sc, medians):
    """Graded sub-scores for a bank or NBFC, on the same 30/25/20/15/10 scale.

    Quality is return on assets and return on equity; safety is capital
    adequacy and net NPA. Thresholds: a 1.5% return on assets is strong for a
    lender, capital adequacy is scored above the 9% regulatory floor, and net
    NPA is scored down from a clean book to 2%.

    CASA and financing margin are reported but score nothing -- an NBFC has no
    CASA at all, so paying points for it would penalise every NBFC for being
    one. Mirrors scoreFinancial() in screenerEngine.ts.
    """
    lines = []
    quality = 0.0
    roa = stock.get("returnOnAssets")
    if roa is None:
        lines.append("Return on assets missing (+0.0)")
    elif roa <= 0:
        lines.append(_award("Return on assets", roa, "%", 0.0))
    else:
        awarded = clamp((roa / 1.5) * 15.0, 0, 15)
        quality += awarded
        lines.append(_award("Return on assets", roa, "%", awarded))
    roe = stock.get("roe")
    if roe is None:
        lines.append("ROE missing (+0.0)")
    elif roe <= 0:
        lines.append(_award("ROE", roe, "%", 0.0))
    else:
        awarded = clamp((roe / 20.0) * 15.0, 0, 15)
        quality += awarded
        lines.append(_award("ROE", roe, "%", awarded))

    safety = 0.0
    car = stock.get("capitalAdequacy")
    if car is not None:
        awarded = clamp(((car - 9.0) / 7.0) * 10.0, 0, 10)
        safety += awarded
        lines.append(_award("Capital adequacy", car, "%", awarded))
    else:
        lines.append("Capital adequacy missing (+0.0)")
    net_npa = stock.get("netNpa")
    if net_npa is not None:
        awarded = clamp(((2.0 - net_npa) / 2.0) * 10.0, 0, 10)
        safety += awarded
        lines.append(_award("Net NPA", net_npa, "%", awarded))
    else:
        lines.append("Net NPA missing (+0.0)")

    # Reported, never scored.
    gross_npa = stock.get("grossNpa")
    if gross_npa is not None:
        lines.append("Gross NPA %s%% (reported, not scored)" % format(round1(gross_npa), ".1f"))
    for field, label in (("casa", "CASA"), ("financingMargin", "Financing margin")):
        value = stock.get(field)
        if value is not None:
            lines.append("%s %s%% (reported, not scored)" % (label, format(round1(value), ".1f")))

    return {
        "financialQuality": clamp(quality, 0, 30),
        "growth": _growth_points(stock, lines),
        "balanceSheetSafety": clamp(safety, 0, 20),
        "valuation": clamp(_valuation_points(stock, medians, lines), 0, 15),
        "governance": _governance_points(stock, lines),
    }, lines


def strict_screen_failures(stock, sc, is_financial):
    """The old pass/fail hurdles, applied only when strict_screen is on.

    These are preferences, not data-integrity problems, so by default they cost
    points rather than rejecting a company. Mirrors strictScreenFailures() in TS.
    """
    reasons = []
    mcap = stock.get("marketCap")
    sg = stock.get("salesGrowth")
    pg = stock.get("profitGrowth")
    roce = stock.get("roce")
    roe = stock.get("roe")
    de = stock.get("debtToEquity")
    icr = stock.get("interestCoverage")
    pe = stock.get("peRatio")
    pb = stock.get("pbRatio")
    ph = stock.get("promoterHolding")

    if mcap is None:
        reasons.append("Market Cap missing")
    elif mcap < sc["minMarketCapCr"]:
        reasons.append("Low Market Cap")
    if sg is None:
        reasons.append("Sales Growth missing")
    elif sg < sc["minSalesGrowthPct"]:
        reasons.append("Low Sales Growth")
    if pg is None:
        reasons.append("Profit Growth missing")
    elif pg < sc["minProfitGrowthPct"]:
        reasons.append("Low Profit Growth")
    if roce is None:
        reasons.append("ROCE missing")
    elif roce < sc["minRocePct"]:
        reasons.append("Low ROCE")
    if roe is None:
        reasons.append("ROE missing")
    elif roe < sc["minRoePct"]:
        reasons.append("Low ROE")
    if not is_financial:
        if de is None:
            reasons.append("Debt/Equity missing")
        elif de > sc["maxDebtToEquity"]:
            reasons.append("High D/E")
        if icr is None:
            reasons.append("Interest Coverage missing")
        elif icr < sc["minInterestCoverage"]:
            reasons.append("Low Interest Coverage")
    if pe is None:
        reasons.append("P/E Ratio missing")
    else:
        if pe < sc["minPeRatio"]:
            reasons.append("P/E below minimum")
        if pe > sc["maxPeRatio"]:
            reasons.append("P/E above maximum")
    if pb is None:
        reasons.append("P/B Ratio missing")
    elif pb > sc["maxPbRatio"]:
        reasons.append("P/B above maximum")
    if ph is None:
        reasons.append("Promoter Holding missing")
    elif ph < sc["minPromoterHoldingPct"]:
        reasons.append("Low Promoter Holding")
    return reasons


class ScreeningEngine:
    """Deterministic rule-based screen and score.

    Scores use round1() (one decimal, half-up) so they are identical to the
    browser engine's. Watchlists sort by score descending then ticker
    ascending, which makes rank order fully deterministic.
    """

    def __init__(self, app_config, screening_config):
        self.config = dict(app_config)
        self.sc = dict(screening_config)
        self._validate_config()

    def _validate_config(self):
        errors = validate_custom_filters(self.config.get("custom_filters"))
        if errors:
            raise ValueError("; ".join(errors))

    def evaluate_custom_filters(self, stock):
        """Apply whitelisted comparisons only. Never evaluates user strings."""
        failures = []
        for filt in self.config.get("custom_filters", []) or []:
            field = filt["field"]
            op = filt["operator"]
            limit = parse_strict_decimal(filt["value"])
            value = stock.get(field)
            if value is None:
                failures.append("Missing value for %s" % field)
                continue
            if not _FILTER_COMPARATORS[op](value, limit):
                # js_number_to_string keeps the text identical to the browser's
                # ("roce <= 30", never Python's "roce <= 30.0").
                failures.append("%s %s %s" % (field, _INVERSE_OPS[op], js_number_to_string(limit)))
        return failures

    def evaluate(self, stock, tech=None, medians=None):
        """Screen and score one stock. Returns a dict mirroring StockEvaluation.

        Three outcomes, decided in this order:
          not scored -- a financial company whose export lacks the metrics the
                        financial model needs. Saying so is honest; scoring it
                        on ratios that do not describe a lender is not.
          rejected   -- a hard red flag fired: the numbers cannot be trusted,
                        so there is nothing worth scoring.
          scored     -- graded sub-scores, each awarded point carrying its own
                        reason line.

        The old pass/fail hurdles (minimum ROCE, growth, leverage, valuation)
        are preferences rather than data-integrity problems, so they now cost
        points instead of rejecting a company, and only reject when
        strict_screen is on.

        medians comes from sector_medians() over the whole loaded file and is
        what makes valuation sector-relative. Mirrors evaluateStock() in TS.
        """
        sc = self.sc
        reasons = []
        warning_flags = []
        if medians is None:
            medians = sector_medians([])

        sector = stock.get("sector") or ""
        is_financial = bool(FINANCIAL_SECTOR_RE.search(sector))
        scoring_model = "financial" if is_financial else "general"

        reasons.extend(self.evaluate_custom_filters(stock))

        mcap = stock.get("marketCap")
        pp = stock.get("promoterPledge")
        div = stock.get("dividendYield")

        # Coverage counts the fields the company's own model actually uses.
        fields = list(COVERAGE_FIELDS_BASE)
        fields += COVERAGE_FIELDS_FINANCIAL if is_financial else COVERAGE_FIELDS_NON_FINANCIAL
        available = sum(1 for f in fields if stock.get(f) is not None)
        coverage = (available / float(len(fields))) * 100.0

        gaps = bank_metric_gaps(stock) if is_financial else []
        not_scored = None
        if gaps:
            # Reported before coverage, so a bank whose export simply lacks the
            # bank columns is told exactly which ones are missing rather than
            # being dismissed as an incomplete row.
            not_scored = "Not scored: missing bank metrics (%s)" % ", ".join(gaps)

        red_flags = [] if not_scored else hard_red_flags(stock, sc, is_financial, coverage)

        if not_scored:
            reasons.append(not_scored)
            warning_flags.append("Missing Bank Metrics")
            parts, score_lines = dict(ZERO_PARTS), []
        elif red_flags:
            reasons.extend(red_flags)
            parts, score_lines = dict(ZERO_PARTS), []
        else:
            scorer = score_financial if is_financial else score_general
            parts, score_lines = scorer(stock, sc, medians)
            if self.config.get("strict_screen"):
                reasons.extend(strict_screen_failures(stock, sc, is_financial))

        fq = parts["financialQuality"]
        growth = parts["growth"]
        balance = parts["balanceSheetSafety"]
        valuation = parts["valuation"]
        governance = parts["governance"]
        total = clamp(fq + growth + balance + valuation + governance, 0, 100)

        scored = not_scored is None and not red_flags
        if scored and total < self.config.get("minimum_total_score", 0):
            reasons.append("Low Total Score: %s" % format(round1(total), ".1f"))

        if div is not None and div < sc["minDividendYieldPct"]:
            warning_flags.append("Low Dividend Yield")
        if mcap is not None and mcap < 500:
            warning_flags.append("Micro Cap")
        if pp is not None and pp > 0:
            warning_flags.append("Promoter Pledged")

        tech_score, tech_breakdown, tech_warnings = calculate_technical_score(
            tech, bool(self.config.get("enable_technical_confirmation"))
        )
        # Technical availability warnings are part of the displayed flag set in
        # both engines, not a separate discarded list.
        warning_flags.extend(tech_warnings)

        return {
            "ticker": stock.get("ticker") or "",
            "name": stock.get("name") or "Unknown",
            "sector": sector,
            "sectorGroup": sector_group(sector),
            "currentPrice": stock.get("currentPrice"),
            "marketCap": mcap,
            "passed": len(reasons) == 0,
            "score": round1(total),
            "coverage": round1(coverage),
            "reasons": list(reasons),
            "warningFlags": list(warning_flags),
            "redFlags": list(red_flags),
            "notScored": not_scored,
            "scoringModel": scoring_model,
            "scoreLines": list(score_lines),
            "techScore": tech_score,
            "techBreakdown": tech_breakdown,
            "dataStatus": (tech or {}).get("data_status", "UNAVAILABLE"),
            "categoryScores": {
                "financialQuality": round1(fq),
                "growth": round1(growth),
                "balanceSheetSafety": round1(balance),
                "valuation": round1(valuation),
                "governance": round1(governance),
            },
            "explanation": build_explanation(stock, total, fq, growth, balance,
                                             valuation, governance, reasons, warning_flags),
        }

    def prepare(self, frame, mapping=None, universe=None):
        """Parse, de-duplicate and universe-filter a fundamentals frame.

        Returns (stocks, duplicates_removed, outside_universe), matching the
        first half of processScreenerPipeline() in screenerEngine.ts.
        """
        if mapping is None:
            mapping = resolve_columns(frame.columns)
        stocks = [parse_row_values(row, mapping) for _, row in frame.iterrows()]
        stocks, duplicates = dedupe_stocks(stocks)
        outside = 0
        allowed = set(normalise_symbols(universe)) if universe is not None else set()
        if allowed:
            kept = [s for s in stocks if (s.get("ticker") or "").upper() in allowed]
            outside = len(stocks) - len(kept)
            stocks = kept
        return stocks, duplicates, outside

    def candidate_tickers(self, frame, mapping=None, universe=None):
        """Tickers that will actually be screened: the ones price history is needed for."""
        stocks, _, _ = self.prepare(frame, mapping, universe)
        return [s["ticker"] for s in stocks if s["ticker"]]

    def screen(self, frame, mapping=None, universe=None, price_history=None):
        """Run the full screen over a fundamentals DataFrame.

        price_history is a parsed Date,Ticker,Close history (see
        parse_price_history_csv) or None when the run has none; technical
        confirmation then reports "No price history loaded" instead of flagging
        every stock.

        Returns dict(evaluations, watchlist, passed_below_cutoff, rejected,
        duplicates_removed, outside_universe). Passing stocks are sorted by
        score desc then ticker asc and ranked 1-based over the whole passing
        list; watchlist holds the first top_n of them and passed_below_cutoff
        the rest, so a stock that passed is never missing from the output.
        """
        stocks, duplicates, outside = self.prepare(frame, mapping, universe)
        technicals = None
        if price_history is not None:
            technicals = technicals_from_history(price_history, [s["ticker"] for s in stocks])
        # One set of yardsticks for the whole run, computed from the companies
        # actually being screened, so valuation is judged against this file's
        # sectors rather than a hard-coded notion of "expensive".
        medians = sector_medians(stocks)
        evaluations = [
            self.evaluate(s, None if technicals is None else technicals[s["ticker"]], medians)
            for s in stocks
        ]

        # Every passing stock is ranked, then the list is split at top_n: the
        # ones below the cut-off are reported separately rather than dropped.
        passed = [e for e in evaluations if e["passed"]]
        passed.sort(key=lambda e: (-e["score"], e["ticker"]))
        for idx, item in enumerate(passed):
            item["rank"] = idx + 1
        top_n = int(self.config.get("top_n") or 0)
        cutoff = top_n if top_n > 0 else len(passed)

        rejected = [e for e in evaluations if not e["passed"]]
        rejected.sort(key=lambda e: (-e["score"], e["ticker"]))

        return {
            "evaluations": evaluations,
            "watchlist": passed[:cutoff],
            "passed_below_cutoff": passed[cutoff:],
            "rejected": rejected,
            "duplicates_removed": duplicates,
            "outside_universe": outside,
        }


def build_explanation(stock, total, fq, growth, balance, valuation, governance,
                      reasons, warning_flags):
    """Factual research rationale assembled from actual factor contributions.

    Never empty. Mirrors buildExplanation() in screenerEngine.ts.
    """
    parts = []
    contributions = [
        ("financial quality", fq, 30),
        ("growth", growth, 25),
        ("balance-sheet safety", balance, 20),
        ("valuation", valuation, 15),
        ("governance", governance, 10),
    ]
    ranked = sorted(contributions, key=lambda c: (-(c[1] / c[2]) if c[2] else 0, c[0]))
    strongest = ranked[0]
    weakest = ranked[-1]
    parts.append(
        "Total fundamental score %s/100." % format(round1(total), ".1f")
    )
    parts.append(
        "Strongest factor: %s at %s/%d; weakest: %s at %s/%d."
        % (strongest[0], format(round1(strongest[1]), ".1f"), strongest[2],
           weakest[0], format(round1(weakest[1]), ".1f"), weakest[2])
    )
    metrics = []
    for label, key, suffix in (
        ("ROCE", "roce", "%"), ("ROE", "roe", "%"),
        ("D/E", "debtToEquity", ""), ("P/E", "peRatio", ""),
        ("promoter holding", "promoterHolding", "%"),
    ):
        value = stock.get(key)
        if value is not None:
            metrics.append("%s %s%s" % (label, format(round1(value), ".1f"), suffix))
    if metrics:
        parts.append("Key inputs: %s." % ", ".join(metrics))
    if reasons:
        parts.append("Rejected because: %s." % "; ".join(reasons))
    else:
        parts.append("Passed every configured screening rule.")
    if warning_flags:
        parts.append("Warnings: %s." % ", ".join(warning_flags))
    return " ".join(parts)
# === END SECTION:engine ===


# === SECTION:deltas:Run-Over-Run Delta Tracking ===
# Columns that hold numbers and must stay numeric in the export.
DELTA_NUMERIC_COLUMNS = frozenset({
    "PreviousRank", "CurrentRank", "RankDelta",
    "PreviousScore", "CurrentScore", "ScoreDelta",
})

RANKING_CHANGE_COLUMNS = [
    "Ticker", "Name", "ChangeType", "PreviousRank", "CurrentRank", "RankDelta",
    "PreviousScore", "CurrentScore", "ScoreDelta", "NewWarnings",
]

CHANGE_NEW_ENTRY = "NEW_ENTRY"
CHANGE_RANK_UP = "RANK_UP"
CHANGE_RANK_DOWN = "RANK_DOWN"
CHANGE_REMOVED = "REMOVED_ENTRY"
CHANGE_STABLE = "STABLE"


def valid_snapshot_entries(data):
    """Snapshot entries usable for delta tracking; malformed ones are dropped.

    A hand-edited or half-written latest_watchlist.json must not crash a run.
    Mirrors validSnapshotEntries() in screenerEngine.ts.
    """
    if not isinstance(data, list):
        return []
    entries = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        ticker, name = raw.get("ticker"), raw.get("name")
        rank, score, flags = raw.get("rank"), raw.get("score"), raw.get("warningFlags")
        if not isinstance(ticker, str) or not ticker:
            continue
        if not _is_finite_number(rank) or not _is_finite_number(score):
            continue
        entries.append({
            "ticker": ticker,
            "name": name if isinstance(name, str) else ticker,
            "rank": rank,
            "score": score,
            "warningFlags": [f for f in flags if isinstance(f, str)] if isinstance(flags, list) else [],
        })
    return entries


def compute_ranking_changes(current, previous):
    """Canonical delta computation shared with computeRankingChanges() in TS.

    current/previous are lists of dicts with ticker, name, rank, score and
    warningFlags. RankDelta = PreviousRank - CurrentRank (positive == moved up).
    Deltas are None where an entry or removal makes the comparison undefined.
    Output order: current watchlist by rank, then removals by previous rank.
    """
    previous = previous or []
    prev_map = {}
    for item in previous:
        prev_map[item["ticker"]] = {
            "name": item.get("name"),
            "rank": item.get("rank"),
            "score": item.get("score"),
            "warnings": set(item.get("warningFlags") or []),
        }

    changes = []
    seen = set()
    for item in sorted(current or [], key=lambda i: i.get("rank") or 0):
        ticker = item["ticker"]
        seen.add(ticker)
        new_rank = item.get("rank")
        new_score = item.get("score")
        current_warnings = list(item.get("warningFlags") or [])
        prev = prev_map.get(ticker)
        if prev is None:
            changes.append({
                "Ticker": ticker,
                "Name": item.get("name") or ticker,
                "ChangeType": CHANGE_NEW_ENTRY,
                "PreviousRank": None,
                "CurrentRank": new_rank,
                "RankDelta": None,
                "PreviousScore": None,
                "CurrentScore": new_score,
                "ScoreDelta": None,
                "NewWarnings": current_warnings,
            })
            continue
        if new_rank < prev["rank"]:
            change_type = CHANGE_RANK_UP
        elif new_rank > prev["rank"]:
            change_type = CHANGE_RANK_DOWN
        else:
            change_type = CHANGE_STABLE
        changes.append({
            "Ticker": ticker,
            "Name": item.get("name") or ticker,
            "ChangeType": change_type,
            "PreviousRank": prev["rank"],
            "CurrentRank": new_rank,
            "RankDelta": prev["rank"] - new_rank,
            "PreviousScore": prev["score"],
            "CurrentScore": new_score,
            "ScoreDelta": round1(new_score - prev["score"]),
            "NewWarnings": [w for w in current_warnings if w not in prev["warnings"]],
        })

    removed = [(t, p) for t, p in prev_map.items() if t not in seen]
    for ticker, prev in sorted(removed, key=lambda kv: kv[1]["rank"] or 0):
        changes.append({
            "Ticker": ticker,
            "Name": prev["name"] or ticker,
            "ChangeType": CHANGE_REMOVED,
            "PreviousRank": prev["rank"],
            "CurrentRank": None,
            "RankDelta": None,
            "PreviousScore": prev["score"],
            "CurrentScore": None,
            "ScoreDelta": None,
            "NewWarnings": [],
        })
    return changes


def _format_delta_cell(column, value):
    if value is None:
        return ""
    if column in ("PreviousScore", "CurrentScore", "ScoreDelta"):
        return format(round1(value), ".1f")
    if column in ("PreviousRank", "CurrentRank", "RankDelta"):
        return str(int(value))
    if column == "NewWarnings":
        return ", ".join(value)
    return str(value)


def ranking_changes_to_csv(changes):
    """Render canonical ranking-changes CSV. Byte-identical to the TS writer.

    LF line endings, QUOTE_MINIMAL, formula-injection guard on text cells.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(RANKING_CHANGE_COLUMNS)
    for change in changes:
        row = []
        for col in RANKING_CHANGE_COLUMNS:
            cell = _format_delta_cell(col, change.get(col))
            # Numeric columns are written as numbers; a negative delta must not
            # become text just because it starts with a minus sign.
            row.append(cell if col in DELTA_NUMERIC_COLUMNS else escape_csv_cell(cell))
        writer.writerow(row)
    return buffer.getvalue()


WATCHLIST_CSV_COLUMNS = [
    "Rank", "Ticker", "Name", "Sector", "CurrentPrice", "MarketCapCr", "Score",
    "TechScore", "Coverage", "FinancialQuality", "Growth", "BalanceSheet",
    "Valuation", "Governance", "WarningFlags",
]
REJECTED_CSV_COLUMNS = [
    "Ticker", "Name", "Sector", "Score", "Coverage", "RejectionReasons", "WarningFlags",
]


def _num(value):
    return "" if value is None else format(round1(value), ".1f")


def watchlist_to_csv(rows):
    """Render the watchlist CSV. Text cells guarded, numerics stay numeric."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(WATCHLIST_CSV_COLUMNS)
    for item in rows:
        cats = item.get("categoryScores", {})
        writer.writerow([
            item.get("rank", ""),
            escape_csv_cell(item.get("ticker")),
            escape_csv_cell(item.get("name")),
            escape_csv_cell(item.get("sector")),
            _num(item.get("currentPrice")),
            _num(item.get("marketCap")),
            _num(item.get("score")),
            "" if item.get("techScore") is None else _num(item.get("techScore")),
            _num(item.get("coverage")),
            _num(cats.get("financialQuality")),
            _num(cats.get("growth")),
            _num(cats.get("balanceSheetSafety")),
            _num(cats.get("valuation")),
            _num(cats.get("governance")),
            escape_csv_cell(", ".join(item.get("warningFlags") or [])),
        ])
    return buffer.getvalue()


def rejected_to_csv(rows):
    """Render the rejected-stock CSV with the same guarantees."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(REJECTED_CSV_COLUMNS)
    for item in rows:
        writer.writerow([
            escape_csv_cell(item.get("ticker")),
            escape_csv_cell(item.get("name")),
            escape_csv_cell(item.get("sector")),
            _num(item.get("score")),
            _num(item.get("coverage")),
            escape_csv_cell("; ".join(item.get("reasons") or [])),
            escape_csv_cell(", ".join(item.get("warningFlags") or [])),
        ])
    return buffer.getvalue()
# === END SECTION:deltas ===


# === SECTION:storage:Data Root, Persistent Layout & Run Logging ===
STORAGE_SUBDIRS = ("config", "fundamentals", "market_data", "cache", "reports", "watchlists", "logs")

# Everything the engine reads or writes lives under one resolved data root, so
# a run never scatters files across the working directory.
DATA_DIR_ENV_VAR = "TRADEBOT_DATA_DIR"
DEFAULT_DATA_DIR_NAME = "data-store"
COLAB_DATA_DIR = "/content/drive/MyDrive/IndianStockEngine"


def project_root():
    """Directory that holds this engine, or the CWD when running from a cell.

    In Colab the notebook has no __file__, so the working directory is the only
    sensible anchor; on disk the engine sits in <project>/python/engine.py.
    """
    module_file = globals().get("__file__")
    if module_file:
        here = Path(module_file).resolve().parent
        return here.parent if here.name == "python" else here
    return Path.cwd()


def resolve_data_root(base_dir=None, mount_drive=True):
    """Decide where run data goes, in a documented precedence order.

    1. an explicit base_dir argument
    2. the TRADEBOT_DATA_DIR environment variable
    3. Google Drive, when running inside Colab and mount_drive is on
    4. <project root>/data-store

    Returns (path, description) so callers can report which rule applied.
    """
    if base_dir is not None:
        return Path(base_dir).expanduser().resolve(), "explicit base_dir argument"

    from_env = os.environ.get(DATA_DIR_ENV_VAR)
    if from_env:
        return Path(from_env).expanduser().resolve(), "%s environment variable" % DATA_DIR_ENV_VAR

    if mount_drive:
        try:
            from google.colab import drive  # noqa: PLC0415 - Colab only

            print("Mounting Google Drive at /content/drive ...")
            drive.mount("/content/drive", force_remount=False)
            return Path(COLAB_DATA_DIR), "Google Drive (Colab)"
        except ImportError:
            pass

    return (project_root() / DEFAULT_DATA_DIR_NAME).resolve(), "project-local default"


def setup_storage_paths(base_dir=None, mount_drive=True):
    """Create the persistent directory layout and return the path map.

    Called only from main(). Importing this module never mounts Drive, touches
    the network, or creates directories.
    """
    root, how = resolve_data_root(base_dir, mount_drive)
    paths = {"root": root}
    for sub in STORAGE_SUBDIRS:
        target = root / sub
        target.mkdir(parents=True, exist_ok=True)
        paths[sub] = target
    print("Data root: %s  (%s)" % (root, how))
    for sub in STORAGE_SUBDIRS:
        print("  %-13s %s" % (sub + "/", paths[sub]))
    return paths


class _Tee:
    """Duplicate a text stream to a log file.

    Used so a run log captures everything the console shows -- including
    unittest output, which writes to the stream directly and would otherwise be
    lost from the log file.
    """

    def __init__(self, stream, handle):
        self._stream = stream
        self._handle = handle

    def write(self, text):
        self._stream.write(text)
        self._handle.write(text)
        self._handle.flush()
        return len(text)

    def flush(self):
        self._stream.flush()
        self._handle.flush()

    def isatty(self):
        return getattr(self._stream, "isatty", lambda: False)()


def run_timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def open_run_log(paths, stamp):
    """Open <data root>/logs/run_<stamp>.log and tee stdout/stderr into it.

    Returns (handle, restore_callable). The caller must invoke restore in a
    finally block so the streams are always put back.
    """
    log_path = paths["logs"] / ("run_%s.log" % stamp)
    handle = open(log_path, "a", encoding="utf-8", buffering=1)
    handle.write("=" * 78 + "\n")
    handle.write("Indian Equity Screening Engine %s - run %s\n" % (SCHEMA_VERSION, stamp))
    handle.write("started (local): %s\n" % datetime.datetime.now().isoformat(timespec="seconds"))
    handle.write("data root:       %s\n" % paths["root"])
    handle.write("python:          %s\n" % sys.version.split()[0])
    handle.write("=" * 78 + "\n")

    original_out, original_err = sys.stdout, sys.stderr
    sys.stdout = _Tee(original_out, handle)
    sys.stderr = _Tee(original_err, handle)

    def restore():
        sys.stdout, sys.stderr = original_out, original_err
        handle.write("finished (local): %s\n" % datetime.datetime.now().isoformat(timespec="seconds"))
        handle.close()

    return log_path, restore


def write_run_summary(paths, stamp, summary):
    """Write a machine-readable summary of the run next to the text log."""
    summary_path = paths["logs"] / ("run_%s.json" % stamp)
    payload = dict(summary)
    payload.setdefault("schema_version", SCHEMA_VERSION)
    payload.setdefault("timestamp", stamp)
    payload.setdefault("data_root", str(paths["root"]))
    summary_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return summary_path
# === END SECTION:storage ===


# === SECTION:tests:Offline Unit Tests (injected fixtures, no network) ===
def _fixture_frame():
    """Two-row fundamentals fixture with standard Screener.in headers."""
    return pd.DataFrame([
        {
            "Name": "Alpha Ltd", "NSE Code": "ALPHA", "BSE Code": "500001",
            "Industry": "Computers - Software", "Current Price": "1000",
            "Market Capitalization": "5000", "Sales growth 3Years": "20%",
            "Profit growth 3Years": "20%", "Return on capital employed": "25%",
            "Return on equity": "22%", "Debt to equity": "0.10",
            "Interest Coverage": "20", "Cash flow from operations": "900",
            "Promoter holding": "60%", "Pledged percentage": "0%",
            "Price to Earning": "18", "Price to book value": "2.5",
            "Dividend yield": "1.2%",
        },
        {
            "Name": "Beta Ltd", "NSE Code": "BETA", "BSE Code": "500002",
            "Industry": "Cement", "Current Price": "500",
            "Market Capitalization": "2000", "Sales growth 3Years": "5%",
            "Profit growth 3Years": "4%", "Return on capital employed": "9%",
            "Return on equity": "8%", "Debt to equity": "1.80",
            "Interest Coverage": "1.2", "Cash flow from operations": "-50",
            "Promoter holding": "20%", "Pledged percentage": "35%",
            "Price to Earning": "70", "Price to book value": "14",
            "Dividend yield": "0.0%",
        },
    ])


_FULL_STOCK = {
    "ticker": "TEST", "name": "Test Co", "bseCode": None,
    "sector": "Computers - Software", "currentPrice": 100.0, "marketCap": 10000.0,
    "salesGrowth": 20.0, "profitGrowth": 20.0, "roce": 25.0, "roe": 25.0,
    "debtToEquity": 0.0, "interestCoverage": 10.0, "operatingCashFlow": 100.0,
    "promoterHolding": 60.0, "promoterPledge": 0.0, "peRatio": 15.0,
    "pbRatio": 2.0, "dividendYield": 1.0,
}


def engine_for_tests(**app_overrides):
    """A ScreeningEngine with cutoffs and technicals off, for single-stock checks."""
    app = dict(DEFAULT_APP_CONFIG, minimum_total_score=0, enable_technical_confirmation=False)
    app.update(app_overrides)
    return ScreeningEngine(app, DEFAULT_SCREENING_CONFIG)


def _synthetic_prices(n, start=100.0, step=0.5):
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series([start + step * i for i in range(n)], index=idx)


class EngineTests(unittest.TestCase):
    """Fully offline. No Drive, no network, no pipeline execution."""

    # --- numeric parsing -------------------------------------------------
    def test_unit_aware_crore_parsing(self):
        self.assertEqual(clean_numeric("1 CRORE", UNIT_CRORE), 1.0)
        self.assertEqual(clean_numeric("100 LAKH", UNIT_CRORE), 1.0)
        self.assertAlmostEqual(clean_numeric("10 LAKH", UNIT_CRORE), 0.1, places=10)
        self.assertEqual(clean_numeric("1,500", UNIT_CRORE), 1500.0)

    def test_monetary_suffix_rejected_on_percent_and_ratio(self):
        self.assertIsNone(clean_numeric("15 CR", UNIT_PERCENT))
        self.assertIsNone(clean_numeric("15 LAKH", UNIT_PERCENT))
        self.assertIsNone(clean_numeric("1 CR", UNIT_RATIO))
        self.assertIsNone(clean_numeric("0.5%", UNIT_RATIO))
        self.assertEqual(clean_numeric("15.5%", UNIT_PERCENT), 15.5)

    def test_malformed_numbers_rejected(self):
        for bad in ("1500abc", "", "N/A", None, "--"):
            self.assertIsNone(clean_numeric(bad, UNIT_RATIO), bad)
        self.assertIsNone(clean_numeric(float("inf"), UNIT_RATIO))
        self.assertIsNone(clean_numeric(float("nan"), UNIT_RATIO))

    def test_round1_is_half_up(self):
        self.assertEqual(round1(74.55), 74.6)
        self.assertEqual(round1(81.45), 81.5)
        self.assertEqual(round1(0.05), 0.1)
        self.assertEqual(round1(100.0), 100.0)

    # --- identifier mapping ---------------------------------------------
    def test_nse_and_bse_do_not_consume_each_other(self):
        m = resolve_columns(["Name", "NSE Code", "BSE Code"])
        self.assertEqual(m["ticker"], "NSE Code")
        self.assertEqual(m["bseCode"], "BSE Code")

    def test_bse_only_serves_as_ticker_fallback(self):
        m = resolve_columns(["Name", "BSE Code"])
        self.assertEqual(m["bseCode"], "BSE Code")
        self.assertEqual(m["ticker"], "BSE Code")

    def test_nse_only(self):
        m = resolve_columns(["Name", "NSE Code"])
        self.assertEqual(m["ticker"], "NSE Code")
        self.assertNotIn("bseCode", m)

    def test_header_order_is_irrelevant(self):
        a = resolve_columns(["Name", "NSE Code", "BSE Code", "Price to Earning"])
        b = resolve_columns(["Price to Earning", "BSE Code", "NSE Code", "Name"])
        self.assertEqual(a, {k: v for k, v in b.items()})

    def test_pe_not_stolen_by_price_alias(self):
        m = resolve_columns(["Name", "Price to Earning", "Price to book value"])
        self.assertEqual(m["peRatio"], "Price to Earning")
        self.assertEqual(m["pbRatio"], "Price to book value")
        self.assertNotIn("currentPrice", m)

    def test_full_screener_header_set(self):
        m = resolve_columns(list(_fixture_frame().columns))
        for field in ("ticker", "bseCode", "name", "sector", "marketCap",
                      "salesGrowth", "profitGrowth", "roce", "roe",
                      "debtToEquity", "interestCoverage", "operatingCashFlow",
                      "promoterHolding", "promoterPledge", "peRatio",
                      "pbRatio", "dividendYield"):
            self.assertIn(field, m, field)

    # --- deduplication ---------------------------------------------------
    def test_dedupe_by_ticker_bse_and_name(self):
        rows = [
            {"ticker": "A", "bseCode": "1", "name": "Alpha"},
            {"ticker": "A", "bseCode": "9", "name": "Other"},
            {"ticker": "B", "bseCode": "1", "name": "Beta"},
            {"ticker": "C", "bseCode": "3", "name": "Alpha"},
            {"ticker": "D", "bseCode": "4", "name": "Delta"},
        ]
        unique, dupes = dedupe_stocks(rows)
        self.assertEqual([u["ticker"] for u in unique], ["A", "D"])
        self.assertEqual(dupes, 3)

    # --- technical history semantics -------------------------------------
    def test_52_week_high_requires_252_sessions(self):
        expectations = {
            20: False, 199: False, 200: False, 251: False, 252: True, 300: True,
        }
        for n, expected in expectations.items():
            tech = compute_technical_indicators(_synthetic_prices(n))
            self.assertEqual(tech["available"]["high52Week"], expected, "n=%d" % n)
            if expected:
                self.assertIsNotNone(tech["high52Week"], "n=%d" % n)
            else:
                self.assertIsNone(tech["high52Week"], "n=%d" % n)
                self.assertIsNone(tech["distFrom52WHighPct"], "n=%d" % n)

    def test_52_week_high_uses_last_252_sessions_only(self):
        # A spike 260 sessions ago must NOT count as the 52-week high.
        idx = pd.date_range("2023-01-01", periods=300, freq="B")
        values = [100.0] * 300
        values[10] = 9999.0
        series = pd.Series(values, index=idx)
        tech = compute_technical_indicators(series)
        self.assertTrue(tech["available"]["high52Week"])
        self.assertEqual(tech["high52Week"], 100.0)

    def test_no_points_for_unavailable_52w_high(self):
        tech = compute_technical_indicators(_synthetic_prices(251))
        score, breakdown, _ = calculate_technical_score(tech, True)
        self.assertIsNotNone(score)
        self.assertTrue(any("52W high unavailable" in b for b in breakdown))

    def test_data_status_levels(self):
        self.assertEqual(compute_technical_indicators(_synthetic_prices(0))["data_status"], "UNAVAILABLE")
        self.assertEqual(compute_technical_indicators(_synthetic_prices(60))["data_status"], "PARTIAL")
        bench = _synthetic_prices(300, start=50.0, step=0.1)
        full = compute_technical_indicators(_synthetic_prices(300), bench_series=bench)
        self.assertEqual(full["data_status"], "COMPLETE")

    def test_technical_disabled_returns_none(self):
        tech = compute_technical_indicators(_synthetic_prices(300))
        score, breakdown, _ = calculate_technical_score(tech, False)
        self.assertIsNone(score)
        self.assertEqual(breakdown, ["Technical screening disabled"])

    # --- screening / scoring ---------------------------------------------
    def test_fixture_screen_outcomes(self):
        engine = ScreeningEngine(
            dict(DEFAULT_APP_CONFIG, universe_mode="custom",
                 custom_symbols=["ALPHA", "BETA"], minimum_total_score=0,
                 enable_technical_confirmation=False),
            DEFAULT_SCREENING_CONFIG,
        )
        result = engine.screen(_fixture_frame())
        by_ticker = {e["ticker"]: e for e in result["evaluations"]}
        self.assertTrue(by_ticker["ALPHA"]["passed"], by_ticker["ALPHA"]["reasons"])
        self.assertFalse(by_ticker["BETA"]["passed"])
        # A pledged promoter stake above the limit and a negative operating
        # cash flow are hard red flags. BETA's weak growth and poor returns now
        # cost it points instead of rejecting it.
        self.assertEqual(by_ticker["BETA"]["redFlags"], ["High Promoter Pledge", "Negative OCF"])
        self.assertIn("Promoter Pledged", by_ticker["BETA"]["warningFlags"])
        self.assertIn("Low Dividend Yield", by_ticker["BETA"]["warningFlags"])

    def test_old_hurdles_reject_only_under_the_strict_screen(self):
        weak = dict(_FULL_STOCK, salesGrowth=1.0)
        relaxed = engine_for_tests().evaluate(weak)
        self.assertTrue(relaxed["passed"], relaxed["reasons"])
        self.assertNotIn("Low Sales Growth", relaxed["reasons"])
        strict = engine_for_tests(strict_screen=True).evaluate(weak)
        self.assertIn("Low Sales Growth", strict["reasons"])
        self.assertFalse(strict["passed"])
        # The strict screen filters; it does not change what a company scores.
        self.assertEqual(strict["score"], relaxed["score"])

    def test_reasons_and_warnings_are_lists(self):
        engine = ScreeningEngine(
            dict(DEFAULT_APP_CONFIG, minimum_total_score=0, enable_technical_confirmation=False),
            DEFAULT_SCREENING_CONFIG,
        )
        ev = engine.evaluate({"ticker": "X", "name": "X", "sector": "IT"})
        self.assertIsInstance(ev["reasons"], list)
        self.assertIsInstance(ev["warningFlags"], list)
        self.assertTrue(all(isinstance(r, str) for r in ev["reasons"]))

    def test_sparse_company_is_not_scaled_up(self):
        engine = ScreeningEngine(
            dict(DEFAULT_APP_CONFIG, minimum_total_score=0, enable_technical_confirmation=False),
            DEFAULT_SCREENING_CONFIG,
        )
        ev = engine.evaluate({"ticker": "SPARSE", "name": "Sparse", "sector": "IT", "roce": 25})
        self.assertFalse(ev["passed"])
        self.assertLessEqual(ev["score"], 15.0)
        self.assertTrue(any("Insufficient Data" in r for r in ev["reasons"]))

    def test_score_bounds_with_extreme_inputs(self):
        engine = ScreeningEngine(
            dict(DEFAULT_APP_CONFIG, minimum_total_score=0, enable_technical_confirmation=False),
            DEFAULT_SCREENING_CONFIG,
        )
        huge = {k: 1e9 for k in COVERAGE_FIELDS_BASE + COVERAGE_FIELDS_NON_FINANCIAL}
        huge.update({"ticker": "HUGE", "name": "Huge", "sector": "IT", "promoterPledge": 0})
        self.assertLessEqual(engine.evaluate(huge)["score"], 100.0)
        negative = {k: -1e9 for k in COVERAGE_FIELDS_BASE + COVERAGE_FIELDS_NON_FINANCIAL}
        negative.update({"ticker": "NEG", "name": "Neg", "sector": "IT", "promoterPledge": -5})
        self.assertGreaterEqual(engine.evaluate(negative)["score"], 0.0)

    def test_watchlist_sort_is_score_then_ticker(self):
        # Runs the real screen: promoter holding 75% saturates governance where
        # 60% does not, so MMM scores highest and AAA/ZZZ tie, breaking by ticker.
        engine = ScreeningEngine(
            dict(DEFAULT_APP_CONFIG, minimum_total_score=0, top_n=10,
                 enable_technical_confirmation=False),
            DEFAULT_SCREENING_CONFIG,
        )
        alpha = _fixture_frame().iloc[0].to_dict()
        rows = [dict(alpha, **{"Name": t, "NSE Code": t, "BSE Code": "", "Promoter holding": ph})
                for t, ph in (("ZZZ", "60%"), ("AAA", "60%"), ("MMM", "75%"))]
        result = engine.screen(pd.DataFrame(rows))
        self.assertEqual([w["ticker"] for w in result["watchlist"]], ["MMM", "AAA", "ZZZ"])
        self.assertEqual([w["rank"] for w in result["watchlist"]], [1, 2, 3])
        self.assertEqual(result["watchlist"][1]["score"], result["watchlist"][2]["score"])

    def test_explanation_is_never_empty(self):
        engine = ScreeningEngine(
            dict(DEFAULT_APP_CONFIG, minimum_total_score=0, enable_technical_confirmation=False),
            DEFAULT_SCREENING_CONFIG,
        )
        for stock in ({"ticker": "A", "name": "A", "sector": "IT"},
                      {"ticker": "B", "name": "B", "sector": "IT", "roce": 30, "roe": 25}):
            text = engine.evaluate(stock)["explanation"]
            self.assertTrue(text and len(text) > 20, text)

    def test_invalid_custom_filter_rejected(self):
        with self.assertRaises(ValueError):
            ScreeningEngine(
                dict(DEFAULT_APP_CONFIG, custom_filters=[{"field": "os.system", "operator": ">", "value": 1}]),
                DEFAULT_SCREENING_CONFIG,
            )
        with self.assertRaises(ValueError):
            ScreeningEngine(
                dict(DEFAULT_APP_CONFIG, custom_filters=[{"field": "roce", "operator": "exec", "value": 1}]),
                DEFAULT_SCREENING_CONFIG,
            )
        with self.assertRaises(ValueError):
            ScreeningEngine(
                dict(DEFAULT_APP_CONFIG, custom_filters=[{"field": "roce", "operator": ">", "value": "drop table"}]),
                DEFAULT_SCREENING_CONFIG,
            )

    # --- CSV safety -------------------------------------------------------
    def test_formula_injection_guard(self):
        self.assertEqual(escape_csv_cell("=cmd|"), "'=cmd|")
        self.assertEqual(escape_csv_cell("+1+1"), "'+1+1")
        self.assertEqual(escape_csv_cell("-500"), "'-500")
        self.assertEqual(escape_csv_cell("@SUM(A1)"), "'@SUM(A1)")
        self.assertEqual(escape_csv_cell("  =leading"), "'  =leading")
        self.assertEqual(escape_csv_cell("\t@tabbed"), "'\t@tabbed")
        self.assertEqual(escape_csv_cell("Normal"), "Normal")

    def test_numeric_cells_stay_numeric(self):
        self.assertEqual(escape_csv_cell(-500), -500)
        self.assertEqual(escape_csv_cell(12.5), 12.5)

    def test_watchlist_csv_guards_text_only(self):
        rows = [{
            "rank": 1, "ticker": "=EVIL", "name": "-Corp", "sector": "IT",
            "currentPrice": 10.0, "marketCap": 1000.0, "score": 80.0,
            "techScore": None, "coverage": 100.0,
            "categoryScores": {"financialQuality": 30.0, "growth": 25.0,
                               "balanceSheetSafety": 20.0, "valuation": 5.0,
                               "governance": 0.0},
            "warningFlags": ["@flag"],
        }]
        out = watchlist_to_csv(rows)
        self.assertIn("'=EVIL", out)
        self.assertIn("'-Corp", out)
        self.assertIn("'@flag", out)
        self.assertIn("1,", out.splitlines()[1][:3])

    def test_rejected_csv_guards(self):
        out = rejected_to_csv([{
            "ticker": "=X", "name": "+Y", "sector": "@Z", "score": 1.0,
            "coverage": 50.0, "reasons": ["-bad"], "warningFlags": [],
        }])
        for token in ("'=X", "'+Y", "'@Z", "'-bad"):
            self.assertIn(token, out)

    # --- deltas -----------------------------------------------------------
    def test_delta_schema_and_semantics(self):
        prev = [
            {"ticker": "A", "name": "A", "rank": 1, "score": 90.0, "warningFlags": []},
            {"ticker": "B", "name": "B", "rank": 2, "score": 80.0, "warningFlags": ["Micro Cap"]},
            {"ticker": "C", "name": "C", "rank": 3, "score": 70.0, "warningFlags": []},
        ]
        curr = [
            {"ticker": "B", "name": "B", "rank": 1, "score": 85.0, "warningFlags": ["Micro Cap", "Promoter Pledged"]},
            {"ticker": "A", "name": "A", "rank": 2, "score": 84.0, "warningFlags": []},
            {"ticker": "D", "name": "D", "rank": 3, "score": 75.0, "warningFlags": []},
        ]
        changes = compute_ranking_changes(curr, prev)
        by_ticker = {c["Ticker"]: c for c in changes}
        self.assertEqual(by_ticker["B"]["ChangeType"], CHANGE_RANK_UP)
        self.assertEqual(by_ticker["B"]["RankDelta"], 1)
        self.assertEqual(by_ticker["B"]["NewWarnings"], ["Promoter Pledged"])
        self.assertEqual(by_ticker["A"]["ChangeType"], CHANGE_RANK_DOWN)
        self.assertEqual(by_ticker["A"]["RankDelta"], -1)
        self.assertEqual(by_ticker["D"]["ChangeType"], CHANGE_NEW_ENTRY)
        self.assertIsNone(by_ticker["D"]["RankDelta"])
        self.assertIsNone(by_ticker["D"]["ScoreDelta"])
        self.assertEqual(by_ticker["C"]["ChangeType"], CHANGE_REMOVED)
        self.assertIsNone(by_ticker["C"]["RankDelta"])
        csv_text = ranking_changes_to_csv(changes)
        self.assertEqual(csv_text.splitlines()[0], ",".join(RANKING_CHANGE_COLUMNS))

    def test_delta_first_run_marks_all_new(self):
        curr = [{"ticker": "A", "name": "A", "rank": 1, "score": 80.0, "warningFlags": []}]
        changes = compute_ranking_changes(curr, None)
        self.assertEqual(len(changes), 1)
        self.assertEqual(changes[0]["ChangeType"], CHANGE_NEW_ENTRY)

    # --- universe ---------------------------------------------------------
    def test_pinned_snapshot_is_exactly_100_unique(self):
        symbols = UniverseProvider(Path(".")).snapshot_symbols()
        self.assertEqual(len(symbols), 100)
        self.assertEqual(len(set(symbols)), 100)

    def test_snapshot_provenance_is_recorded(self):
        for key in ("source_url", "retrieved_at_utc", "as_of_date", "sha256_of_source_csv"):
            self.assertTrue(NIFTY100_PROVENANCE.get(key), key)
        self.assertEqual(len(NIFTY100_PROVENANCE["sha256_of_source_csv"]), 64)

    def test_offline_universe_is_labelled_cached(self):
        provider = UniverseProvider(Path("."))
        provider.get_universe("nifty100", allow_network=False)
        self.assertIn("cached snapshot", provider.describe_source())

    def test_custom_universe_mode(self):
        provider = UniverseProvider(Path("."))
        self.assertEqual(provider.get_universe("custom", [" tcs ", "infy"]), ["TCS", "INFY"])

    # --- fundamentals adapter --------------------------------------------
    def test_xlsx_is_rejected(self):
        adapter = FundamentalsAdapter(Path("."))
        with self.assertRaises(ValueError):
            adapter.load(Path("whatever.xlsx"))

    # --- cache key --------------------------------------------------------
    def test_cache_key_is_order_insensitive_and_schema_aware(self):
        mdp = MarketDataProvider(Path("."))
        self.assertEqual(mdp.cache_key(["A", "B"], "1y"), mdp.cache_key(["B", "A"], "1y"))
        self.assertNotEqual(mdp.cache_key(["A"], "1y"), mdp.cache_key(["A"], "2y"))
        self.assertNotEqual(mdp.cache_key(["A"], "1y"), mdp.cache_key(["A"], "1y", "v99"))

    def test_market_data_downloader_is_injectable(self):
        calls = []

        def fake(symbols, period):
            calls.append((tuple(symbols), period))
            return "FRAME"

        mdp = MarketDataProvider(Path("."), downloader=fake)
        self.assertEqual(mdp.fetch(["TCS"], "2015-01-01"), "FRAME")
        self.assertEqual(calls, [(("TCS",), "2015-01-01")])
        # The default window is the configured start date, not a yfinance period.
        mdp.fetch(["TCS"])
        self.assertEqual(calls[-1], (("TCS",), HISTORY_START))

    # --- cross-engine number and text shapes -------------------------------
    def test_js_number_to_string_matches_javascript(self):
        cases = {30.0: "30", 30.5: "30.5", -2.0: "-2", 0.0: "0", 1e-7: "1e-7",
                 1e-6: "0.000001", 1e16: "10000000000000000", 1e21: "1e+21",
                 123456.789: "123456.789", 0.1 + 0.2: "0.30000000000000004"}
        for value, expected in cases.items():
            self.assertEqual(js_number_to_string(value), expected, value)

    def test_custom_filter_reason_uses_javascript_number_text(self):
        engine = ScreeningEngine(
            dict(DEFAULT_APP_CONFIG, minimum_total_score=0, enable_technical_confirmation=False,
                 custom_filters=[{"field": "roce", "operator": ">", "value": "30"}]),
            DEFAULT_SCREENING_CONFIG,
        )
        reasons = engine.evaluate({"ticker": "X", "name": "X", "sector": "IT", "roce": 25})["reasons"]
        self.assertIn("roce <= 30", reasons)

    def test_strict_decimal_accepts_only_ascii_decimals(self):
        arabic_twelve = chr(0x0661) + chr(0x0662)
        for bad in ("0x10", "0b101", "0o17", "1_0", "inf", "nan", arabic_twelve, "", " "):
            self.assertIsNone(parse_strict_decimal(bad), bad)
        self.assertEqual(parse_strict_decimal(" 12.5 "), 12.5)
        self.assertEqual(parse_strict_decimal("1e3"), 1000.0)
        self.assertIsNone(clean_numeric(chr(0x0663), UNIT_RATIO))

    def test_whitespace_follows_javascript(self):
        # U+001F is whitespace to Python but not to JavaScript; U+FEFF the reverse.
        self.assertIsNone(clean_numeric("5" + chr(0x1F), UNIT_RATIO))
        self.assertEqual(clean_numeric(chr(0xFEFF) + "5", UNIT_RATIO), 5.0)
        self.assertEqual(js_trim(chr(0xA0) + "x" + chr(0x3000)), "x")
        self.assertEqual(normalize_header("Promoter" + chr(0xA0) + "holding " + chr(0xE9)), "promoter holding")

    # --- price history ----------------------------------------------------
    def test_yahoo_symbols(self):
        self.assertEqual(yahoo_symbol(" tcs "), "TCS.NS")
        self.assertEqual(yahoo_symbol("500209"), "500209.BO")
        self.assertEqual(yahoo_symbol(BENCHMARK_SYMBOL), BENCHMARK_SYMBOL)

    def test_price_history_csv_parses_and_skips_bad_rows(self):
        text = ("date,SYMBOL,Close,Volume\n"
                "2025-01-02,tcs,100.5,1000\n"
                "2025-01-01,TCS,100,\n"
                "2025-01-02,TCS,101,2000\n"
                "not-a-date,TCS,1,1\n"
                "2025-01-03,,1,1\n"
                "2025-01-03,TCS,abc,1\n"
                ",,,\n")
        history, skipped = parse_price_history_csv(text)
        self.assertEqual(skipped, 3)
        self.assertEqual(history["TCS"], {
            "dates": ["2025-01-01", "2025-01-02"],
            "closes": [100.0, 101.0], "volumes": [None, 2000.0],
            # A file written before the OHLCV widening still loads; the missing
            # columns stay absent and are never guessed from the close.
            "opens": [None, None], "highs": [None, None], "lows": [None, None],
        })
        with self.assertRaises(ValueError):
            parse_price_history_csv("Date,Close\n2025-01-01,1\n")
        wide, _ = parse_price_history_csv(
            "Date,Ticker,Open,High,Low,Close,Volume\n2025-01-01,TCS,99,105,98,104,1000\n")
        self.assertEqual(wide["TCS"]["opens"], [99.0])
        self.assertEqual(wide["TCS"]["highs"], [105.0])
        self.assertEqual(wide["TCS"]["lows"], [98.0])

    def test_download_frame_is_flattened_to_screener_tickers(self):
        # TCS carries a high and a low; 500209 and the benchmark carry neither,
        # so this covers both the present and the absent case in one file.
        idx = pd.date_range("2025-01-01", periods=3, freq="B")
        columns = pd.MultiIndex.from_tuples([
            ("Close", "TCS.NS"), ("Close", "500209.BO"), ("Close", "^NSEI"),
            ("Volume", "TCS.NS"), ("High", "TCS.NS"), ("Low", "TCS.NS"),
        ])
        nan = float("nan")
        frame = pd.DataFrame(
            [[1.0, 2.0, 3.0, 10.0, 1.5, 0.9],
             [nan, 2.5, 3.5, 11.0, 1.6, 0.95],
             [1.2, 2.6, 3.6, nan, 1.7, 1.1]],
            index=idx, columns=columns)
        text = price_history_to_csv(price_history_rows_from_download(frame, ["TCS", "500209"]))
        self.assertEqual(text.splitlines(), [
            "Date,Ticker,Open,High,Low,Close,Volume",
            "2025-01-01,500209,,,,2.0,", "2025-01-02,500209,,,,2.5,",
            "2025-01-03,500209,,,,2.6,",
            # The middle session has no close, so it is dropped entirely; an
            # absent open is written blank rather than copied from the close.
            "2025-01-01,TCS,,1.5,0.9,1.0,10", "2025-01-03,TCS,,1.7,1.1,1.2,",
            "2025-01-01,^NSEI,,,,3.0,", "2025-01-02,^NSEI,,,,3.5,",
            "2025-01-03,^NSEI,,,,3.6,",
        ])

    def test_technicals_align_benchmark_by_date(self):
        dates = [d.strftime("%Y-%m-%d") for d in pd.date_range("2024-01-01", periods=300, freq="B")]
        history = {
            "AAA": {"dates": dates, "closes": [100.0 + i for i in range(300)], "volumes": [1000.0] * 300},
            BENCHMARK_SYMBOL: {"dates": dates[::2], "closes": [50.0] * 150, "volumes": [None] * 150},
        }
        tech = technicals_from_history(history, ["AAA", "MISSING"])
        self.assertEqual(tech["AAA"]["data_status"], "COMPLETE")
        self.assertEqual(tech["AAA"]["as_of"], dates[-1])
        self.assertEqual(tech["AAA"]["volumeRatio20D"], 1.0)
        self.assertEqual(tech["MISSING"]["data_status"], "UNAVAILABLE")

    def test_no_price_history_is_reported_once_not_per_stock(self):
        self.assertEqual(calculate_technical_score(None, True), (None, ["No price history loaded"], []))
        _, _, missing = calculate_technical_score(empty_technicals(), True)
        self.assertEqual(missing, ["Technical Data Missing"])

    def test_screen_uses_price_history(self):
        engine = ScreeningEngine(dict(DEFAULT_APP_CONFIG, minimum_total_score=0), DEFAULT_SCREENING_CONFIG)
        dates = [d.strftime("%Y-%m-%d") for d in pd.date_range("2024-01-01", periods=300, freq="B")]
        history = {"ALPHA": {"dates": dates, "closes": [100.0 + 0.5 * i for i in range(300)],
                             "volumes": [None] * 300}}
        by_ticker = {e["ticker"]: e for e in engine.screen(_fixture_frame(), price_history=history)["evaluations"]}
        self.assertEqual(by_ticker["ALPHA"]["techScore"], 85.0)
        self.assertIn("Technical Data Missing", by_ticker["BETA"]["warningFlags"])
        without = engine.screen(_fixture_frame())["evaluations"][0]
        self.assertEqual(without["techBreakdown"], ["No price history loaded"])
        self.assertNotIn("Technical Data Missing", without["warningFlags"])

    # --- configuration ------------------------------------------------------
    def test_config_document_is_validated_not_clamped(self):
        app, screening, errors = validate_config_document(
            {"app": {"top_n": 10.0, "custom_symbols": [" tcs ", ""]}, "screening": {"minRocePct": 18}})
        self.assertEqual(errors, [])
        self.assertEqual((app["top_n"], app["custom_symbols"], screening["minRocePct"]), (10, ["TCS"], 18))
        self.assertEqual(screening["maxPeRatio"], DEFAULT_SCREENING_CONFIG["maxPeRatio"])
        self.assertEqual(validate_config_document(
            config_document(DEFAULT_APP_CONFIG, DEFAULT_SCREENING_CONFIG))[2], [])
        for bad in ({"app": {"top_n": 0}}, {"app": {"top_n": 2.5}}, {"app": {"paper_trading_only": True}},
                    {"screening": {"minRocePct": "18"}}, {"screening": {"requirePositiveOcf": 1}},
                    {"app": {"custom_filters": [{"field": "os.system", "operator": ">", "value": 1}]}},
                    {"app": {"universe_mode": "all"}}, {"schema_version": "v5"}, {"extra": {}}, []):
            self.assertTrue(validate_config_document(bad)[2], bad)

    # --- deltas -------------------------------------------------------------
    def test_removed_entry_keeps_its_previous_name(self):
        previous = [{"ticker": "GONE", "name": "Gone Ltd", "rank": 1, "score": 70.0, "warningFlags": []}]
        self.assertEqual(compute_ranking_changes([], previous)[0]["Name"], "Gone Ltd")

    # --- screening rules found by review --------------------------------------
    def test_negative_net_worth_is_a_hard_red_flag(self):
        result = engine_for_tests().evaluate(dict(_FULL_STOCK, debtToEquity=-3.5))
        self.assertEqual(result["redFlags"], ["Negative net worth"])
        self.assertIn("Negative net worth", result["reasons"])
        self.assertFalse(result["passed"])
        # A red flag stops scoring outright: the numbers cannot be trusted, so
        # there is nothing worth awarding points for.
        self.assertEqual(result["score"], 0.0)
        self.assertEqual(result["categoryScores"]["balanceSheetSafety"], 0.0)
        self.assertEqual(result["scoreLines"], [])
        # A negative P/B reaches the same conclusion on its own.
        self.assertEqual(
            engine_for_tests().evaluate(dict(_FULL_STOCK, pbRatio=-0.3))["redFlags"],
            ["Negative net worth"])

    def test_a_reported_zero_is_a_value_not_a_gap(self):
        """A published zero must never be described as a missing figure.

        ITC, L&T, HDFC Bank and ICICI Bank genuinely have no promoter at all.
        Guarding on `value > 0` made every such company report "Promoter
        holding missing", and the same truthiness mistake sat in five other
        fields. None of them changes the points -- zero earns zero either way --
        but the explanation was stating something untrue about the company.
        """
        zero = engine_for_tests().evaluate(dict(_FULL_STOCK, promoterHolding=0.0))
        self.assertIn("Promoter holding 0.0% (+0.0)", zero["scoreLines"])
        self.assertNotIn("Promoter holding missing (+0.0)", zero["scoreLines"])

        # A genuinely absent value still reports itself absent.
        absent = engine_for_tests().evaluate(dict(_FULL_STOCK, promoterHolding=None))
        self.assertIn("Promoter holding missing (+0.0)", absent["scoreLines"])

        # Coverage already counted the zero as present, so it is not penalised
        # a second time; this pins that it stays that way.
        self.assertEqual(zero["coverage"], 100.0)
        self.assertLess(absent["coverage"], zero["coverage"])

        for field, line in (("roce", "ROCE 0.0% (+0.0)"),
                            ("roe", "ROE 0.0% (+0.0)"),
                            ("interestCoverage", "Interest cover 0.0x (+0.0)")):
            result = engine_for_tests().evaluate(dict(_FULL_STOCK, **{field: 0.0}))
            self.assertIn(line, result["scoreLines"], field)

        bank = dict(_FULL_STOCK, sector="Banking", returnOnAssets=0.0, grossNpa=2.1,
                    netNpa=0.5, capitalAdequacy=16.0)
        self.assertIn("Return on assets 0.0% (+0.0)",
                      engine_for_tests().evaluate(bank)["scoreLines"])

        # Zero debt is the best case, not a missing one, and keeps its ten.
        self.assertIn("D/E 0.0 (+10.0)",
                      engine_for_tests().evaluate(dict(_FULL_STOCK, debtToEquity=0.0))["scoreLines"])

    def test_screener_financial_sector_names(self):
        financial = ("Banking", "Financial - Services", "Financial Services", "Capital Markets",
                     "Stock Brokers", "Asset Management", "Other Financial Services",
                     "Finance - NBFC", "Insurance", "Depository Services", "Wealth Management",
                     "Lending", "Mutual Funds", "Securities", "Stock Exchange")
        industrial = ("Capital Goods", "Trading", "Computers - Software", "Infrastructure",
                      "Metals - Non Ferrous", "Pharmaceuticals", "Abrasives")
        # Financial companies are routed to the financial model rather than
        # excluded; without the bank columns they report what is missing.
        for sector in financial:
            result = engine_for_tests().evaluate(dict(_FULL_STOCK, sector=sector))
            self.assertEqual(result["scoringModel"], "financial", sector)
            self.assertEqual(result["notScored"],
                             "Not scored: missing bank metrics (Return on assets, "
                             "Gross NPA %, Net NPA %, Capital adequacy ratio)", sector)
        for sector in industrial:
            result = engine_for_tests().evaluate(dict(_FULL_STOCK, sector=sector))
            self.assertEqual(result["scoringModel"], "general", sector)
            self.assertIsNone(result["notScored"], sector)

    def test_bank_with_its_metrics_is_scored_not_excluded(self):
        bank = dict(_FULL_STOCK, sector="Banking", returnOnAssets=1.8, grossNpa=2.1,
                    netNpa=0.5, capitalAdequacy=16.0, operatingCashFlow=-900.0)
        result = engine_for_tests().evaluate(bank)
        self.assertEqual(result["scoringModel"], "financial")
        self.assertIsNone(result["notScored"])
        # A negative operating cash flow is ordinary for a lender whose loan
        # book is growing, so it must not be a red flag here.
        self.assertEqual(result["redFlags"], [])
        self.assertGreater(result["score"], 0.0)
        self.assertTrue(any("Return on assets" in line for line in result["scoreLines"]))
        # CASA and financing margin are reported, never scored.
        casa = dict(bank, casa=44.0)
        self.assertEqual(engine_for_tests().evaluate(casa)["score"], result["score"])

    def test_passing_stocks_below_top_n_are_kept(self):
        engine = ScreeningEngine(
            dict(DEFAULT_APP_CONFIG, minimum_total_score=0, top_n=2,
                 enable_technical_confirmation=False),
            DEFAULT_SCREENING_CONFIG,
        )
        alpha = _fixture_frame().iloc[0].to_dict()
        rows = [dict(alpha, **{"Name": "%s Ltd" % t, "NSE Code": t, "BSE Code": ""})
                for t in ("AAA", "BBB", "CCC")]
        result = engine.screen(pd.DataFrame(rows))
        self.assertEqual([w["ticker"] for w in result["watchlist"]], ["AAA", "BBB"])
        self.assertEqual([(w["ticker"], w["rank"]) for w in result["passed_below_cutoff"]],
                         [("CCC", 3)])
        self.assertIn("CCC", watchlist_to_csv(result["passed_below_cutoff"]))

    def test_rupee_prefixes_parse(self):
        for text in ("Rs 1,500", "RS. 1,500", "INR 1500", "rs 1500"):
            self.assertEqual(clean_numeric(text, UNIT_PRICE), 1500.0, text)
        self.assertEqual(clean_numeric("Rs 1,500 Cr", UNIT_CRORE), 1500.0)
        self.assertIsNone(clean_numeric("RSVP", UNIT_PRICE))
        self.assertIsNone(clean_numeric("Rs", UNIT_PRICE))

    def test_min_pe_above_max_pe_is_rejected(self):
        errors = validate_config_document({"screening": {"minPeRatio": 60, "maxPeRatio": 55}})[2]
        self.assertEqual(errors, ["screening.minPeRatio (60) must not be above "
                                  "screening.maxPeRatio (55)"])
        self.assertEqual(validate_config_document({"screening": {"minPeRatio": 55}})[2], [])

    def test_malformed_snapshots_are_ignored(self):
        entry = {"ticker": "TCS", "name": "TCS Ltd", "rank": 1, "score": 80.0, "warningFlags": []}
        for bad in ({}, None, 42, "snapshot", [42], [{"ticker": "TCS"}],
                    [dict(entry, rank="one")]):
            self.assertEqual(valid_snapshot_entries(bad), [], repr(bad))
        self.assertEqual(valid_snapshot_entries([entry]), [entry])
        self.assertEqual(valid_snapshot_entries([entry, {"ticker": ""}]), [entry])

    # --- file-format edge cases -----------------------------------------------
    def test_price_history_line_endings_and_delimiter(self):
        mixed = "Date,Ticker,Close\r\n2025-01-01,TCS,1\n2025-01-02,TCS,2\n"
        cr_only = "Date,Ticker,Close\r2025-01-01,TCS,1\r2025-01-02,TCS,2\r"
        for text in (mixed, cr_only):
            history, skipped = parse_price_history_csv(text)
            self.assertEqual((history["TCS"]["closes"], skipped), ([1.0, 2.0], 0), repr(text))
        with self.assertRaises(ValueError):
            parse_price_history_csv("Date\tTicker\tClose\n2025-01-01\tTCS\t1\n")

    def test_price_history_skips_impossible_dates(self):
        text = "Date,Ticker,Close\n" + "".join(
            "%s,TCS,1\n" % d for d in ("2025-02-30", "2025-13-01", "1900-02-29", "2024-02-29", "2000-02-29"))
        history, skipped = parse_price_history_csv(text)
        self.assertEqual(skipped, 3)
        self.assertEqual(history["TCS"]["dates"], ["2000-02-29", "2024-02-29"])

    def test_volume_ratio_needs_the_latest_sessions_volume(self):
        closes = [100.0] * 30
        blank_last = compute_technical_indicators(closes, None, [1000.0] * 29 + [None])
        self.assertIsNone(blank_last["volumeRatio20D"])
        with_last = compute_technical_indicators(closes, None, [1000.0] * 29 + [2000.0])
        self.assertEqual(with_last["volumeRatio20D"], 2000.0 / (21000.0 / 20))

    def test_short_history_is_described_not_called_absent(self):
        tech = compute_technical_indicators([100.0 + i for i in range(30)])
        self.assertEqual(tech["data_status"], "UNAVAILABLE")
        _, breakdown, flags = calculate_technical_score(tech, True)
        self.assertEqual(breakdown, ["Only 30 sessions of price history; indicators need at least 50"])
        self.assertEqual(flags, ["Technical Data Missing"])

    def test_financial_sector_match_is_ascii_only(self):
        engine = ScreeningEngine(dict(DEFAULT_APP_CONFIG, enable_technical_confirmation=False),
                                 DEFAULT_SCREENING_CONFIG)
        # Unicode case folding would read the long s (U+017F) as "s" and call
        # this insurance; ASCII-only folding must not.
        long_s = "In" + chr(0x17F) + "urance"
        self.assertEqual(engine.evaluate({"ticker": "X", "sector": long_s})["scoringModel"],
                         "general")
        self.assertEqual(engine.evaluate({"ticker": "X", "sector": "INSURANCE"})["scoringModel"],
                         "financial")

    def test_config_errors_match_javascript_text_and_order(self):
        self.assertEqual(validate_config_document({"zzz": 1, "5": 2})[2],
                         ["Unknown configuration section: 5", "Unknown configuration section: zzz"])
        self.assertEqual(validate_config_document({"schema_version": 6.0})[2],
                         ["Unsupported schema_version 6 (expected v6)"])
        self.assertEqual(validate_custom_filters([{"field": None, "operator": ">", "value": 1}]),
                         ["Invalid custom filter field: null"])
        self.assertEqual(validate_custom_filters([{"field": "roce", "operator": ">", "value": [1]}]),
                         ["Invalid numeric value in custom filter for roce: [1]"])


class NetworkIntegrationTests(unittest.TestCase):
    """OPTIONAL network tests. Skipped unless RUN_NETWORK_TESTS=1.

    These are never part of the offline suite and never gate a release build.
    """

    @unittest.skipUnless(os.environ.get("RUN_NETWORK_TESTS") == "1",
                         "network tests are opt-in (set RUN_NETWORK_TESTS=1)")
    def test_live_nse_universe_matches_snapshot_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            symbols = UniverseProvider(tmp).fetch_live()
        self.assertEqual(len(set(symbols)), 100)

    @unittest.skipUnless(os.environ.get("RUN_NETWORK_TESTS") == "1",
                         "network tests are opt-in (set RUN_NETWORK_TESTS=1)")
    def test_live_price_history_download(self):
        with tempfile.TemporaryDirectory() as tmp:
            history, path, how = MarketDataProvider(tmp).load_price_history(["TCS"], allow_network=True)
            self.assertEqual(how, "downloaded")
            self.assertTrue(path.exists())
        self.assertGreaterEqual(len(history["TCS"]["dates"]), SESSIONS_52_WEEK)
        self.assertIn(BENCHMARK_SYMBOL, history)
# === END SECTION:tests ===


# === SECTION:pipeline:Execution Pipeline ===
def load_run_config(paths, explicit_path=None):
    """Settings for a run: --config path, else <data root>/config/config.json, else defaults.

    Returns (app_config, screening_config, description). An invalid file
    raises ValueError: a run never quietly falls back to defaults when a config
    file exists but asks for something the engine cannot honour.
    """
    path = Path(explicit_path).expanduser() if explicit_path else paths["config"] / CONFIG_FILENAME
    if explicit_path or path.exists():
        app, screening = load_config_file(path)
        return app, screening, str(path.resolve())
    defaults = validate_config_document({})
    return defaults[0], defaults[1], "defaults (no %s)" % path


def run_pipeline(paths, app_config, screening_config, allow_network=False, stamp=None,
                 downloader=None, today=None):
    """Execute one screening run end-to-end.

    Returns (result, artefacts) where artefacts records every file written, so
    main() can put it in the run summary. downloader is passed to
    MarketDataProvider so tests can inject price history offline, and today
    fixes the date the price cache is keyed by, so a run crossing midnight is
    reproducible.
    """
    stamp = stamp or run_timestamp()
    universe_provider = UniverseProvider(paths["cache"])
    adapter = FundamentalsAdapter(paths["fundamentals"])

    available = adapter.list_available()
    if not available:
        raise SystemExit(
            "No fundamentals CSV found in %s. Export your Screener.in query as "
            "CSV and place it there." % paths["fundamentals"]
        )
    source_file = available[0]
    frame = adapter.load(source_file)
    age_days, age_source = fundamentals_age_days(frame, source_file)
    print("Loaded %d rows from %s (%d days old, by %s)."
          % (len(frame), source_file.name, age_days, age_source))
    if age_source == "file timestamp":
        print("  The export carries no date column, so staleness uses the file's "
              "timestamp; a copied file therefore looks new.")
    if age_days > app_config.get("fundamentals_stale_after_days", 30):
        print("WARNING: fundamentals are stale (%d days). Re-export from Screener.in." % age_days)

    universe = None
    if app_config.get("universe_mode") == "nifty100":
        universe = universe_provider.get_universe("nifty100", allow_network=allow_network)
        print("Universe source: %s" % universe_provider.describe_source())
    elif app_config.get("custom_symbols"):
        universe = universe_provider.get_universe("custom", app_config["custom_symbols"])

    engine = ScreeningEngine(app_config, screening_config)
    price_history, price_file, price_source = None, None, "technical confirmation disabled"
    if app_config.get("enable_technical_confirmation"):
        # Price every company in the active universe, not just the ones this
        # export happens to contain. A 31-row export would otherwise yield 31
        # priced tickers out of a 100-name index, and the backtest needs history
        # for companies missing from today's file as much as for the ones in it.
        # With no universe filter there is nothing to widen to, so the export's
        # own tickers are all there is.
        in_export = engine.candidate_tickers(frame, universe=universe)
        tickers = sorted(set(universe) | set(in_export)) if universe else in_export
        price_source = "no tickers to price"
        if tickers:
            provider = MarketDataProvider(paths["market_data"], downloader=downloader)
            price_history, price_file, price_source = provider.load_price_history(
                tickers, allow_network, today=today)
        if price_history is None:
            print("Technical confirmation skipped: no price history (%s). "
                  "Technical scores are blank." % price_source)
        else:
            covered = sum(1 for t in tickers if t in price_history)
            as_of = max((s["dates"][-1] for s in price_history.values() if s["dates"]), default="n/a")
            print("Price history: %d of %d tickers, as of %s (%s): %s"
                  % (covered, len(tickers), as_of, price_source, price_file))
            if BENCHMARK_SYMBOL not in price_history:
                print("WARNING: benchmark %s is missing, so 6-month relative strength "
                      "is unavailable." % BENCHMARK_SYMBOL)

    result = engine.screen(frame, universe=universe, price_history=price_history)
    below = result["passed_below_cutoff"]
    print("Evaluated %d companies; %d passed (%d in the watchlist, %d below the cut-off); "
          "%d duplicates removed; %d outside the universe."
          % (len(result["evaluations"]), len(result["watchlist"]) + len(below),
             len(result["watchlist"]), len(below),
             result["duplicates_removed"], result["outside_universe"]))

    watchlist_path = paths["reports"] / ("watchlist_%s.csv" % stamp)
    watchlist_path.write_text(watchlist_to_csv(result["watchlist"]), encoding="utf-8")
    rejected_path = paths["reports"] / ("rejected_%s.csv" % stamp)
    rejected_path.write_text(rejected_to_csv(result["rejected"]), encoding="utf-8")

    below_path = None
    if below:
        below_path = paths["reports"] / ("passed_below_top_n_%s.csv" % stamp)
        below_path.write_text(watchlist_to_csv(below), encoding="utf-8")

    latest_json = paths["watchlists"] / "latest_watchlist.json"
    previous = None
    if latest_json.exists():
        try:
            stored = json.loads(latest_json.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print("Could not read previous snapshot (%s); treating as first run." % exc)
        else:
            previous = valid_snapshot_entries(stored) or None
            if previous is None:
                print("Previous snapshot %s holds no usable entries; treating as first run."
                      % latest_json.name)

    changes = compute_ranking_changes(result["watchlist"], previous)
    changes_path = paths["reports"] / "ranking_changes.csv"
    changes_path.write_text(ranking_changes_to_csv(changes), encoding="utf-8")
    if previous is None:
        print("FIRST_RUN: no previous watchlist; every candidate is a new entry.")

    snapshot = [
        {
            "ticker": item["ticker"], "name": item["name"], "rank": item["rank"],
            "score": item["score"], "warningFlags": item["warningFlags"],
        }
        for item in result["watchlist"]
    ]
    latest_json.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    artefacts = {
        "watchlist_csv": str(watchlist_path),
        "rejected_csv": str(rejected_path),
        "passed_below_top_n_csv": str(below_path) if below_path else None,
        "ranking_changes_csv": str(changes_path),
        "latest_watchlist_json": str(latest_json),
        "source_fundamentals": str(source_file),
        "fundamentals_age_days": age_days,
        "fundamentals_age_source": age_source,
        "universe_source": universe_provider.describe_source() if universe is not None else "not filtered",
        "price_history_csv": str(price_file) if price_file else None,
        "price_history_source": price_source,
        "rows_loaded": len(frame),
        "evaluated": len(result["evaluations"]),
        "passed": len(result["watchlist"]) + len(below),
        "in_watchlist": len(result["watchlist"]),
        "passed_below_cutoff": len(below),
        "rejected": len(result["rejected"]),
        "duplicates_removed": result["duplicates_removed"],
        "outside_universe": result["outside_universe"],
        "first_run": previous is None,
        "ranking_changes": len(changes),
    }
    print("Wrote:")
    for label in ("watchlist_csv", "passed_below_top_n_csv", "rejected_csv",
                  "ranking_changes_csv", "latest_watchlist_json"):
        if artefacts[label]:
            print("  %s" % artefacts[label])
    return result, artefacts


def build_arg_parser():
    parser = argparse.ArgumentParser(
        prog="engine.py",
        description="Indian Equity Quantitative Screening Engine (%s)" % SCHEMA_VERSION,
    )
    parser.add_argument("--offline", action="store_true",
                        help="no network: cached Nifty 100 snapshot, cached price history only")
    parser.add_argument("--self-test", action="store_true",
                        help="run the offline unit tests and exit")
    parser.add_argument("--data-dir", metavar="DIR",
                        help="read and write all run data and logs under DIR")
    parser.add_argument("--config", metavar="FILE",
                        help="settings file (default: <data root>/config/%s)" % CONFIG_FILENAME)
    return parser


def main(argv=None):
    """Entry point. Nothing here runs on import.

    Flags (see --help): --offline, --self-test, --data-dir DIR, --config FILE.
    """
    try:
        args = build_arg_parser().parse_args(sys.argv[1:] if argv is None else argv)
    except SystemExit as exc:  # argparse exits on --help (0) and bad flags (2)
        return exc.code

    # Process-wide settings belong to a run, never to an import.
    np.random.seed(DETERMINISTIC_SEED)
    print("Indian Equity Quantitative Screening Engine (%s)" % SCHEMA_VERSION)
    print("Deterministic seed: %d" % DETERMINISTIC_SEED)

    if args.self_test:
        suite = unittest.TestLoader().loadTestsFromTestCase(EngineTests)
        outcome = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if outcome.wasSuccessful() else 1

    allow_network = not args.offline
    paths = setup_storage_paths(base_dir=args.data_dir, mount_drive=True)
    stamp = run_timestamp()
    log_path, restore_streams = open_run_log(paths, stamp)
    status = 1
    summary = {"status": "started", "allow_network": allow_network}
    try:
        print("Run log: %s" % log_path)
        try:
            app_config, screening_config, config_source = load_run_config(paths, args.config)
        except ValueError as exc:
            summary["status"] = "invalid_config"
            summary["error"] = str(exc)
            print("Run aborted: %s" % exc)
            status = 2
            return status
        summary["config_source"] = config_source
        summary["config"] = config_document(app_config, screening_config)
        print("\nConfiguration: %s" % config_source)
        for section, values in (("app", app_config), ("screening", screening_config)):
            for key, value in values.items():
                print("  %s.%s: %s" % (section, key, value))

        print("\nRunning offline self-verification ...")
        suite = unittest.TestLoader().loadTestsFromTestCase(EngineTests)
        test_result = unittest.TextTestRunner(verbosity=1).run(suite)
        summary["self_tests_run"] = test_result.testsRun
        summary["self_tests_failed"] = len(test_result.failures) + len(test_result.errors)
        if not test_result.wasSuccessful():
            summary["status"] = "self_verification_failed"
            print("Self-verification FAILED; aborting before screening.")
            return 1

        _, artefacts = run_pipeline(
            paths, app_config, screening_config, allow_network=allow_network, stamp=stamp,
        )
        summary.update(artefacts)
        summary["status"] = "ok"
        status = 0
        return 0
    except SystemExit as exc:
        # run_pipeline raises SystemExit for expected operator errors (for
        # example, no fundamentals CSV). Record it and return its code.
        summary["status"] = "aborted"
        summary["error"] = str(exc)
        print("Run aborted: %s" % exc)
        status = exc.code if isinstance(exc.code, int) else 1
        return status
    except Exception as exc:  # noqa: BLE001 - log the failure before surfacing
        summary["status"] = "error"
        summary["error"] = repr(exc)
        print("Run FAILED: %r" % exc)
        raise
    finally:
        summary["exit_code"] = status
        summary["run_log"] = str(log_path)
        try:
            summary_path = write_run_summary(paths, stamp, summary)
            print("Run summary: %s" % summary_path)
        finally:
            restore_streams()


def _running_in_notebook():
    """True inside Jupyter or Colab.

    There, sys.argv belongs to the kernel, and sys.exit() -- even sys.exit(0) --
    is shown as an exception banner under the cell.
    """
    return "ipykernel" in sys.modules


if __name__ == "__main__":
    if _running_in_notebook():
        # A notebook cell has no __file__ and the kernel owns its argv, but
        # `%run engine.py --offline` sets both, so its flags are honoured.
        _exit_code = main(sys.argv[1:] if "__file__" in globals() else [])
        if _exit_code:
            print("Run finished with exit code %s; see the messages above." % _exit_code)
    else:
        sys.exit(main())
# === END SECTION:pipeline ===
