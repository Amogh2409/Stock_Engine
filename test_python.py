#!/usr/bin/env python3
"""Standalone Python test suite for the shipped Colab notebook.

Loads the engine from the GENERATED notebook (not from python/engine.py), so it
verifies the artifact users actually download. It then runs the notebook's own
offline EngineTests plus additional parity and contract tests defined here.

FAIL-CLOSED. Any of the following exits non-zero:
  * the notebook file is absent or unreadable
  * the notebook has no code cells
  * pandas / numpy are missing
  * the engine module lacks a required symbol
  * any single subtest fails

CANONICAL TYPES (documented once, asserted below):
  ScreeningEngine.evaluate() -> dict where
      "reasons"      is a list[str]  -- one entry per rejection reason
      "warningFlags" is a list[str]  -- one entry per warning
  The CSV writers are the only place those lists become strings, joined with
  "; " (reasons) and ", " (warnings). Nothing iterates a joined string, so a
  reason is never walked character by character.

Run:  python3 test_python.py            (offline; the release gate uses this)
      RUN_NETWORK_TESTS=1 python3 test_python.py   (adds optional network tests)
"""
from __future__ import annotations

import contextlib
import datetime
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NOTEBOOK = ROOT / "Indian_Equity_Quantitative_Engine.ipynb"

REQUIRED_SYMBOLS = (
    "clamp", "round1", "parse_strict_decimal", "clean_numeric", "escape_csv_cell",
    "write_safe_csv", "resolve_columns", "parse_row_values", "dedupe_stocks",
    "compute_technical_indicators", "calculate_technical_score",
    "ScreeningEngine", "UniverseProvider", "FundamentalsAdapter",
    "MarketDataProvider", "compute_ranking_changes", "ranking_changes_to_csv",
    "watchlist_to_csv", "rejected_to_csv", "build_explanation",
    "setup_storage_paths", "resolve_data_root", "project_root", "run_pipeline",
    "open_run_log", "write_run_summary", "run_timestamp", "main", "EngineTests",
    "DATA_DIR_ENV_VAR", "DEFAULT_DATA_DIR_NAME", "STORAGE_SUBDIRS",
    "NIFTY100_FALLBACK_SYMBOLS", "NIFTY100_PROVENANCE",
    "UNIT_CRORE", "UNIT_PERCENT", "UNIT_RATIO", "UNIT_PRICE",
    "SESSIONS_52_WEEK", "RANKING_CHANGE_COLUMNS", "DEFAULT_APP_CONFIG",
    "DEFAULT_SCREENING_CONFIG", "js_trim", "js_number_to_string", "normalise_symbols",
    "validate_custom_filters", "validate_config_document", "config_document",
    "load_config_file", "load_run_config", "build_arg_parser", "CONFIG_LIMITS",
    "CONFIG_FILENAME", "BENCHMARK_SYMBOL", "yahoo_symbol", "price_history_rows_from_download",
    "price_history_to_csv", "parse_price_history_csv", "technicals_from_history",
    "fundamentals_as_of", "fundamentals_age_days", "FINANCIAL_SECTOR_RE",
    "FINANCIAL_SECTOR_TERMS", "read_fundamentals_csv", "valid_snapshot_entries",
)


def _global_state():
    """Process-wide state an import must leave alone: warning filters, NumPy's RNG, pandas options."""
    import numpy
    import pandas

    rng = numpy.random.get_state()
    return (
        list(warnings.filters),
        rng[1].tobytes(), rng[2],
        pandas.get_option("display.max_columns"),
        pandas.get_option("display.float_format"),
    )


_STATE_AROUND_IMPORT = {}


@contextlib.contextmanager
def without_data_dir_env():
    """Run with TRADEBOT_DATA_DIR unset, whatever the caller's environment holds.

    The README tells you to set it, and the tests that assert the *default* data
    root would then fail and turn the release gate red.
    """
    previous = os.environ.pop(E.DATA_DIR_ENV_VAR, None)
    try:
        yield
    finally:
        if previous is not None:
            os.environ[E.DATA_DIR_ENV_VAR] = previous


def quiet(fn, *args, **kwargs):
    """Call fn with stdout/stderr captured, so pipeline chatter stays out of test output."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


def fatal(message: str) -> "types.NoReturn":
    print("FATAL: %s" % message, file=sys.stderr)
    raise SystemExit(1)


def load_engine_from_notebook() -> types.ModuleType:
    """Extract and import the notebook's Python. Fails closed at every step."""
    try:
        import pandas  # noqa: F401
        import numpy  # noqa: F401
    except ImportError as exc:
        fatal("required dependency missing (%s). Install -r requirements-test.txt" % exc)

    if not NOTEBOOK.exists():
        fatal("notebook not found at %s. Run: npm run generate:notebook" % NOTEBOOK)
    try:
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fatal("could not read or parse the notebook: %s" % exc)

    cells = [c for c in notebook.get("cells", []) if c.get("cell_type") == "code"]
    if not cells:
        fatal("notebook contains no code cells")
    source = "\n".join("".join(cell["source"]) for cell in cells)
    if not source.strip():
        fatal("notebook code cells are empty")

    target = ROOT / "_notebook_engine_under_test.py"
    target.write_text(source, encoding="utf-8")
    try:
        spec = importlib.util.spec_from_file_location("notebook_engine_under_test", target)
        if spec is None or spec.loader is None:
            fatal("could not create a module spec for the extracted engine")
        module = importlib.util.module_from_spec(spec)
        # Importing must not mount Drive, hit the network or run the pipeline,
        # and must not change process-wide state (checked by ImportPurity).
        _STATE_AROUND_IMPORT["before"] = _global_state()
        spec.loader.exec_module(module)
        _STATE_AROUND_IMPORT["after"] = _global_state()
    except Exception as exc:  # noqa: BLE001 - any import failure is fatal
        fatal("importing the notebook engine failed: %r" % (exc,))
    finally:
        target.unlink(missing_ok=True)

    missing = [name for name in REQUIRED_SYMBOLS if not hasattr(module, name)]
    if missing:
        fatal("engine is missing required symbols: %s" % ", ".join(missing))
    return module


def _snapshot_data_tree():
    """Files under the default data root, as a set of relative paths."""
    root = ROOT / "data-store"
    if not root.exists():
        return None
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


# Recorded before the import so the purity test can compare, rather than
# assuming the data root is absent. A released tree ships an empty skeleton and
# a working tree holds real run output; neither may change on import.
_DATA_TREE_BEFORE_IMPORT = _snapshot_data_tree()
_LEGACY_DIR_BEFORE_IMPORT = (ROOT / "IndianStockEngine").exists()

E = load_engine_from_notebook()


def prices(n: int, start: float = 100.0, step: float = 0.5):
    import pandas as pd

    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.Series([start + step * i for i in range(n)], index=idx)


def engine(**app_overrides) -> "E.ScreeningEngine":
    app = dict(E.DEFAULT_APP_CONFIG)
    app.update({"minimum_total_score": 0, "enable_technical_confirmation": False})
    app.update(app_overrides)
    return E.ScreeningEngine(app, E.DEFAULT_SCREENING_CONFIG)


FULL_STOCK = {
    "ticker": "TEST", "name": "Test Co", "bseCode": None,
    "sector": "Computers - Software", "currentPrice": 100.0, "marketCap": 10000.0,
    "salesGrowth": 20.0, "profitGrowth": 20.0, "roce": 25.0, "roe": 25.0,
    "debtToEquity": 0.0, "interestCoverage": 10.0, "operatingCashFlow": 100.0,
    "promoterHolding": 60.0, "promoterPledge": 0.0, "peRatio": 15.0,
    "pbRatio": 2.0, "dividendYield": 1.0,
}


class CanonicalTypeContract(unittest.TestCase):
    """Reasons and warnings are lists of strings -- never joined strings."""

    def test_reasons_and_warnings_are_lists_of_strings(self):
        # A pledged stake above the limit is a hard red flag. Weak returns are
        # not: they cost points, so they no longer produce a rejection reason.
        result = engine().evaluate(dict(FULL_STOCK, promoterPledge=50.0))
        self.assertIsInstance(result["reasons"], list)
        self.assertIsInstance(result["warningFlags"], list)
        self.assertTrue(result["reasons"], "a failing stock must report reasons")
        for entry in result["reasons"] + result["warningFlags"]:
            self.assertIsInstance(entry, str)
            # A single-character entry would mean a joined string got iterated.
            self.assertGreater(len(entry), 1, "reason/warning looks character-split: %r" % entry)

    def test_reasons_are_whole_phrases_not_characters(self):
        # Low promoter holding is one of the old hurdles, so it only produces a
        # rejection reason when the strict screen is on.
        result = engine(strict_screen=True).evaluate(dict(FULL_STOCK, promoterHolding=5.0))
        self.assertIn("Low Promoter Holding", result["reasons"])
        # Membership must be by element, so a substring is NOT a member.
        self.assertNotIn("L", result["reasons"])

    def test_csv_writers_join_lists_with_documented_separators(self):
        row = dict(FULL_STOCK, dividendYield=0.0, marketCap=400.0, promoterPledge=5.0)
        evaluated = engine().evaluate(row)
        evaluated["rank"] = 1
        watchlist_csv = E.watchlist_to_csv([evaluated])
        self.assertIn("Low Dividend Yield, Micro Cap, Promoter Pledged", watchlist_csv)
        # Two hard red flags on one row, so the join separator is visible.
        two_flags = dict(FULL_STOCK, promoterPledge=50.0, operatingCashFlow=-5.0)
        rejected_csv = E.rejected_to_csv([engine().evaluate(two_flags)])
        self.assertIn("High Promoter Pledge; Negative OCF", rejected_csv)
        self.assertIn("; ", rejected_csv, "rejection reasons join with '; '")


class UniverseProviderContract(unittest.TestCase):
    """Uses the real UniverseProvider class (there is no UniverseManager)."""

    def test_class_exists_with_the_documented_name(self):
        self.assertTrue(hasattr(E, "UniverseProvider"))
        self.assertFalse(hasattr(E, "UniverseManager"),
                         "UniverseManager never existed; do not reintroduce it")

    def test_offline_snapshot_is_exactly_100_unique(self):
        provider = E.UniverseProvider(ROOT / "_test_cache")
        symbols = provider.get_universe("nifty100", allow_network=False)
        self.assertEqual(len(symbols), 100)
        self.assertEqual(len(set(symbols)), 100)

    def test_offline_source_is_labelled_cached_with_a_date(self):
        provider = E.UniverseProvider(ROOT / "_test_cache")
        provider.get_universe("nifty100", allow_network=False)
        description = provider.describe_source()
        self.assertIn("cached snapshot", description)
        self.assertIn(E.NIFTY100_PROVENANCE["as_of_date"], description)

    def test_snapshot_contains_constituents_a_count_check_would_miss(self):
        symbols = set(E.UniverseProvider(ROOT / "_test_cache").snapshot_symbols())
        for expected in ("RELIANCE", "TCS", "TITAN", "WIPRO", "ULTRACEMCO", "ZYDUSLIFE", "TATASTEEL"):
            self.assertIn(expected, symbols, expected)

    def test_provenance_is_complete(self):
        prov = E.NIFTY100_PROVENANCE
        for key in ("source_url", "retrieved_at_utc", "as_of_date", "sha256_of_source_csv"):
            self.assertTrue(prov.get(key), key)
        self.assertEqual(len(prov["sha256_of_source_csv"]), 64)
        self.assertEqual(prov["count"], 100)

    def test_custom_mode_normalises_symbols(self):
        provider = E.UniverseProvider(ROOT / "_test_cache")
        self.assertEqual(provider.get_universe("custom", [" tcs ", "infy", ""]), ["TCS", "INFY"])


class CleanNumericSignature(unittest.TestCase):
    """clean_numeric takes a field-aware unit argument; it is called that way."""

    def test_signature_accepts_a_unit_argument(self):
        import inspect

        params = list(inspect.signature(E.clean_numeric).parameters)
        self.assertEqual(params, ["value", "unit"])

    def test_crore_contract(self):
        self.assertEqual(E.clean_numeric("1 CRORE", E.UNIT_CRORE), 1.0)
        self.assertEqual(E.clean_numeric("1 CR", E.UNIT_CRORE), 1.0)
        self.assertEqual(E.clean_numeric("100 LAKH", E.UNIT_CRORE), 1.0)
        self.assertAlmostEqual(E.clean_numeric("10 LAKH", E.UNIT_CRORE), 0.1, places=12)

    def test_monetary_suffix_rejected_on_percent_and_ratio(self):
        self.assertIsNone(E.clean_numeric("15 CR", E.UNIT_PERCENT))
        self.assertIsNone(E.clean_numeric("15 LAKH", E.UNIT_PERCENT))
        self.assertIsNone(E.clean_numeric("1 CR", E.UNIT_RATIO))
        self.assertIsNone(E.clean_numeric("1500 CR", E.UNIT_PRICE))

    def test_percent_allowed_only_on_percent_fields(self):
        self.assertEqual(E.clean_numeric("15.5%", E.UNIT_PERCENT), 15.5)
        self.assertIsNone(E.clean_numeric("0.5%", E.UNIT_RATIO))

    def test_hex_and_underscore_literals_rejected(self):
        # Python's float() and JavaScript's Number() disagree about these, so
        # both engines pin the accepted shape explicitly.
        self.assertIsNone(E.clean_numeric("0x10", E.UNIT_RATIO))
        self.assertIsNone(E.clean_numeric("1_0", E.UNIT_RATIO))
        self.assertIsNone(E.clean_numeric("inf", E.UNIT_RATIO))
        self.assertIsNone(E.clean_numeric("nan", E.UNIT_RATIO))

    def test_field_units_are_applied_by_parse_row_values(self):
        import pandas as pd

        frame = pd.DataFrame([{
            "Name": "A", "NSE Code": "AAA",
            "Market Capitalization": "100 LAKH",   # -> 1 crore
            "Return on equity": "15 CR",           # -> rejected, wrong unit
        }])
        mapping = E.resolve_columns(frame.columns)
        parsed = E.parse_row_values(frame.iloc[0], mapping)
        self.assertEqual(parsed["marketCap"], 1.0)
        self.assertIsNone(parsed["roe"])


class IdentifierMappingParity(unittest.TestCase):
    def test_nse_and_bse_do_not_consume_each_other(self):
        mapping = E.resolve_columns(["Name", "NSE Code", "BSE Code"])
        self.assertEqual(mapping["ticker"], "NSE Code")
        self.assertEqual(mapping["bseCode"], "BSE Code")

    def test_bse_only_keeps_both_ticker_fallback_and_bse_code(self):
        mapping = E.resolve_columns(["Name", "BSE Code"])
        self.assertEqual(mapping["ticker"], "BSE Code")
        self.assertEqual(mapping["bseCode"], "BSE Code")

    def test_nse_only(self):
        mapping = E.resolve_columns(["Name", "NSE Code"])
        self.assertEqual(mapping["ticker"], "NSE Code")
        self.assertNotIn("bseCode", mapping)

    def test_header_order_is_irrelevant(self):
        forward = E.resolve_columns(["Name", "NSE Code", "BSE Code", "Price to Earning"])
        reverse = E.resolve_columns(["Price to Earning", "BSE Code", "NSE Code", "Name"])
        self.assertEqual(forward, reverse)

    def test_dedupe_matches_the_documented_rule_set(self):
        rows = [
            {"ticker": "A", "bseCode": "1", "name": "Alpha"},
            {"ticker": "A", "bseCode": "9", "name": "Other"},
            {"ticker": "B", "bseCode": "1", "name": "Beta"},
            {"ticker": "C", "bseCode": "3", "name": "Alpha"},
            {"ticker": "D", "bseCode": "4", "name": "Delta"},
        ]
        unique, removed = E.dedupe_stocks(rows)
        self.assertEqual([r["ticker"] for r in unique], ["A", "D"])
        self.assertEqual(removed, 3)


class TechnicalHistorySemantics(unittest.TestCase):
    def test_52_week_high_thresholds(self):
        for n, expected in ((20, False), (199, False), (200, False),
                            (251, False), (252, True), (300, True)):
            tech = E.compute_technical_indicators(prices(n))
            self.assertEqual(tech["available"]["high52Week"], expected, "n=%d" % n)
            if not expected:
                self.assertIsNone(tech["high52Week"], "n=%d" % n)
                self.assertIsNone(tech["distFrom52WHighPct"], "n=%d" % n)

    def test_200_day_max_is_not_called_a_52_week_high(self):
        tech = E.compute_technical_indicators(prices(200))
        self.assertTrue(tech["available"]["sma200"])
        self.assertFalse(tech["available"]["high52Week"])
        self.assertIsNone(tech["high52Week"])

    def test_unavailable_52_week_high_scores_zero_points(self):
        with_high = E.compute_technical_indicators(prices(252), bench_series=prices(252, 50.0, 0.1))
        without = E.compute_technical_indicators(prices(251), bench_series=prices(251, 50.0, 0.1))
        score_with, _, _ = E.calculate_technical_score(with_high, True)
        score_without, breakdown, _ = E.calculate_technical_score(without, True)
        self.assertEqual(score_with - score_without, 15.0)
        self.assertTrue(any("52W high unavailable" in line for line in breakdown))

    def test_availability_is_explicit_per_indicator(self):
        tech = E.compute_technical_indicators(prices(60))
        self.assertEqual(
            set(tech["available"]),
            {"sma50", "sma200", "smaCross", "relativeStrength6M", "high52Week"},
        )
        self.assertTrue(tech["available"]["sma50"])
        self.assertFalse(tech["available"]["sma200"])
        self.assertEqual(tech["data_status"], "PARTIAL")

    def test_history_window_is_a_start_date_with_room_for_a_backtest(self):
        # A fixed start date, not a yfinance "period": that vocabulary has no
        # value between 10y and max, and the window has to be reproducible.
        self.assertEqual(E.HISTORY_START, "2015-01-01")
        self.assertFalse(hasattr(E, "MIN_HISTORY_PERIOD"),
                         "the old period constant must not linger alongside HISTORY_START")
        self.assertEqual(E.SESSIONS_52_WEEK, 252)
        # Ten years of business days is far more than the longest indicator
        # window, so no indicator is starved by the download itself.
        start = datetime.date.fromisoformat(E.HISTORY_START)
        self.assertGreater((datetime.date.today() - start).days / 365.0, 10.0)


class CsvExportSafety(unittest.TestCase):
    def test_all_four_dangerous_leads(self):
        for value, expected in (("=cmd|", "'=cmd|"), ("+1+1", "'+1+1"),
                                ("-500", "'-500"), ("@SUM(A1)", "'@SUM(A1)")):
            self.assertEqual(E.escape_csv_cell(value), expected)

    def test_leading_whitespace_still_guarded(self):
        self.assertEqual(E.escape_csv_cell("  =lead"), "'  =lead")
        self.assertEqual(E.escape_csv_cell("\t@tab"), "'\t@tab")
        self.assertEqual(E.escape_csv_cell("\n-nl"), "'\n-nl")
        self.assertEqual(E.escape_csv_cell(" +plus"), "' +plus")

    def test_numeric_columns_are_not_stringified(self):
        self.assertEqual(E.escape_csv_cell(-500), -500)
        self.assertEqual(E.escape_csv_cell(12.5), 12.5)
        evaluated = engine().evaluate(dict(FULL_STOCK, ticker="AAA"))
        evaluated["rank"] = 1
        row = E.watchlist_to_csv([evaluated]).splitlines()[1].split(",")
        self.assertEqual(row[0], "1")
        self.assertFalse(row[6].startswith("'"), "score must stay numeric")

    def test_every_user_controlled_csv_is_guarded(self):
        hostile = dict(FULL_STOCK, ticker="=EVIL", name="-Corp", sector="@Sector",
                       dividendYield=0.0, promoterPledge=5.0)
        evaluated = engine().evaluate(hostile)
        evaluated["rank"] = 1
        for text in (E.watchlist_to_csv([evaluated]),
                     E.rejected_to_csv([engine().evaluate(dict(hostile, roce=1.0))])):
            self.assertIn("'=EVIL", text)
            self.assertIn("'-Corp", text)
            self.assertIn("'@Sector", text)
        changes = E.compute_ranking_changes(
            [{"ticker": "=X", "name": "-Y", "rank": 1, "score": 80.0, "warningFlags": ["@Z"]}], None)
        changes_csv = E.ranking_changes_to_csv(changes)
        self.assertIn("'=X", changes_csv)
        self.assertIn("'-Y", changes_csv)
        self.assertIn("'@Z", changes_csv)


class DeltaSchema(unittest.TestCase):
    def test_columns_are_canonical(self):
        self.assertEqual(E.RANKING_CHANGE_COLUMNS, [
            "Ticker", "Name", "ChangeType", "PreviousRank", "CurrentRank",
            "RankDelta", "PreviousScore", "CurrentScore", "ScoreDelta", "NewWarnings",
        ])

    def test_change_types_and_rank_delta_sign(self):
        previous = [
            {"ticker": "POLY", "name": "P", "rank": 1, "score": 84.0, "warningFlags": []},
            {"ticker": "AIA", "name": "A", "rank": 2, "score": 89.0, "warningFlags": []},
            {"ticker": "HOLD", "name": "H", "rank": 3, "score": 80.0, "warningFlags": []},
            {"ticker": "GONE", "name": "G", "rank": 4, "score": 70.0, "warningFlags": []},
        ]
        current = [
            {"ticker": "AIA", "name": "A", "rank": 1, "score": 88.0, "warningFlags": ["Micro Cap"]},
            {"ticker": "POLY", "name": "P", "rank": 2, "score": 84.0, "warningFlags": []},
            {"ticker": "HOLD", "name": "H", "rank": 3, "score": 80.0, "warningFlags": []},
            {"ticker": "NEW", "name": "N", "rank": 4, "score": 75.0, "warningFlags": []},
        ]
        by_ticker = {c["Ticker"]: c for c in E.compute_ranking_changes(current, previous)}
        self.assertEqual(by_ticker["AIA"]["ChangeType"], "RANK_UP")
        self.assertEqual(by_ticker["AIA"]["RankDelta"], 1)
        self.assertEqual(by_ticker["AIA"]["NewWarnings"], ["Micro Cap"])
        self.assertEqual(by_ticker["POLY"]["ChangeType"], "RANK_DOWN")
        self.assertEqual(by_ticker["POLY"]["RankDelta"], -1)
        self.assertEqual(by_ticker["HOLD"]["ChangeType"], "STABLE")
        self.assertEqual(by_ticker["HOLD"]["RankDelta"], 0)
        self.assertEqual(by_ticker["NEW"]["ChangeType"], "NEW_ENTRY")
        self.assertEqual(by_ticker["GONE"]["ChangeType"], "REMOVED_ENTRY")

    def test_undefined_deltas_are_blank_in_csv(self):
        previous = [{"ticker": "GONE", "name": "G", "rank": 1, "score": 70.0, "warningFlags": []}]
        current = [{"ticker": "NEW", "name": "N", "rank": 1, "score": 75.0, "warningFlags": []}]
        lines = E.ranking_changes_to_csv(E.compute_ranking_changes(current, previous)).splitlines()
        self.assertEqual(lines[0], ",".join(E.RANKING_CHANGE_COLUMNS))
        self.assertEqual(lines[1], "NEW,N,NEW_ENTRY,,1,,,75.0,,")
        # A removed entry keeps the name recorded in the previous snapshot.
        self.assertEqual(lines[2], "GONE,G,REMOVED_ENTRY,1,,,70.0,,,")


class ScoringAndOrdering(unittest.TestCase):
    def test_pinned_score_for_fully_specified_inputs(self):
        # Valuation is judged against the file's own sectors, so a single stock
        # evaluated with no yardstick scores nothing for valuation and says so,
        # rather than being flattered by an absolute threshold.
        # quality 2x9.4 + growth 2x8.3 + safety 10+10 + valuation 0 + governance 4+5
        result = engine().evaluate(FULL_STOCK)
        self.assertEqual(result["score"], 64.4)
        self.assertTrue(result["passed"], result["reasons"])
        self.assertEqual(result["coverage"], 100.0)
        self.assertEqual(result["categoryScores"]["valuation"], 0.0)
        self.assertTrue(any("no P/E yardstick" in line for line in result["scoreLines"]),
                        result["scoreLines"])

    def test_valuation_is_scored_against_the_sector_median(self):
        # Five identical companies make their industry its own median, so this
        # stock sits exactly on the yardstick and earns half the valuation marks.
        peers = [dict(FULL_STOCK, ticker="P%d" % i) for i in range(5)]
        medians = E.sector_medians(peers)
        result = engine().evaluate(FULL_STOCK, None, medians)
        self.assertEqual(result["categoryScores"]["valuation"], 7.5)
        self.assertEqual(result["score"], 71.9)
        self.assertTrue(any("Computers - Software median" in line
                            for line in result["scoreLines"]), result["scoreLines"])
        # Half the sector's P/E earns full marks; half again above it earns none.
        cheap = engine().evaluate(dict(FULL_STOCK, peRatio=7.5, pbRatio=1.0), None, medians)
        dear = engine().evaluate(dict(FULL_STOCK, peRatio=30.0, pbRatio=4.0), None, medians)
        self.assertEqual(cheap["categoryScores"]["valuation"], 15.0)
        self.assertEqual(dear["categoryScores"]["valuation"], 0.0)

    def test_round1_is_half_up_not_bankers(self):
        self.assertEqual(E.round1(74.55), 74.6)
        self.assertEqual(E.round1(81.45), 81.5)
        self.assertEqual(E.round1(0.05), 0.1)
        # 0.25 is exactly representable, so this is a true half-way case:
        # builtin round() rounds to even (0.2); round1 must round up (0.3).
        self.assertEqual(E.round1(0.25), 0.3)
        self.assertEqual(round(0.25, 1), 0.2)
        self.assertNotEqual(E.round1(0.25), round(0.25, 1))

    def test_watchlist_sorts_by_score_then_ticker(self):
        import pandas as pd

        rows = []
        for ticker, holding in (("ZZZ", 60.0), ("AAA", 60.0), ("MMM", 75.0)):
            rows.append({
                "Name": ticker, "NSE Code": ticker, "Industry": "IT",
                "Market Capitalization": "10000", "Sales growth 3Years": "20%",
                "Profit growth 3Years": "20%", "Return on capital employed": "25%",
                "Return on equity": "25%", "Debt to equity": "0",
                "Interest Coverage": "10", "Cash flow from operations": "100",
                "Promoter holding": "%s%%" % holding, "Pledged percentage": "0%",
                "Price to Earning": "15", "Price to book value": "2",
                "Dividend yield": "1%",
            })
        result = engine(top_n=10).screen(pd.DataFrame(rows))
        self.assertEqual([w["ticker"] for w in result["watchlist"]], ["MMM", "AAA", "ZZZ"])
        self.assertEqual([w["rank"] for w in result["watchlist"]], [1, 2, 3])

    def test_explanation_is_factual_and_non_empty(self):
        result = engine().evaluate(FULL_STOCK)
        self.assertIn("Total fundamental score 64.4/100", result["explanation"])
        self.assertIn("Strongest factor", result["explanation"])
        self.assertIn("ROCE 25.0%", result["explanation"])
        rejected = engine().evaluate(dict(FULL_STOCK, promoterPledge=50.0))
        self.assertIn("Rejected because", rejected["explanation"])

    def test_custom_filters_are_whitelisted_and_never_executed(self):
        for bad in ({"field": "os.system", "operator": ">", "value": 1},
                    {"field": "roce", "operator": "exec", "value": 1},
                    {"field": "roce", "operator": ">", "value": "__import__('os')"}):
            with self.assertRaises(ValueError):
                E.ScreeningEngine(dict(E.DEFAULT_APP_CONFIG, custom_filters=[bad]),
                                  E.DEFAULT_SCREENING_CONFIG)


class StorageAndLogging(unittest.TestCase):
    """Every run writes its data and its log under one resolved data root."""

    def test_data_root_precedence(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            explicit, how = E.resolve_data_root(base_dir=tmp, mount_drive=False)
            self.assertEqual(explicit, Path(tmp).resolve())
            self.assertIn("explicit", how)

        old = os.environ.get(E.DATA_DIR_ENV_VAR)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.environ[E.DATA_DIR_ENV_VAR] = tmp
                from_env, how = E.resolve_data_root(mount_drive=False)
                self.assertEqual(from_env, Path(tmp).resolve())
                self.assertIn(E.DATA_DIR_ENV_VAR, how)
        finally:
            if old is None:
                os.environ.pop(E.DATA_DIR_ENV_VAR, None)
            else:
                os.environ[E.DATA_DIR_ENV_VAR] = old

        with without_data_dir_env():
            default, how = E.resolve_data_root(mount_drive=False)
        self.assertEqual(default.name, E.DEFAULT_DATA_DIR_NAME)
        self.assertIn("project-local", how)

    def test_setup_creates_every_subdirectory(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = E.setup_storage_paths(base_dir=tmp, mount_drive=False)
            for sub in E.STORAGE_SUBDIRS:
                self.assertIn(sub, paths, sub)
                self.assertTrue(paths[sub].is_dir(), sub)
            self.assertEqual(paths["root"], Path(tmp).resolve())

    def test_run_log_captures_console_output(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = E.setup_storage_paths(base_dir=tmp, mount_drive=False)
            stamp = E.run_timestamp()
            log_path, restore = E.open_run_log(paths, stamp)
            try:
                print("marker-inside-run-log")
            finally:
                restore()
            self.assertTrue(log_path.exists())
            text = log_path.read_text(encoding="utf-8")
            self.assertIn("marker-inside-run-log", text)
            self.assertIn("data root:", text)
            self.assertIn(E.SCHEMA_VERSION, text)

    def test_run_log_restores_streams_even_on_error(self):
        import tempfile

        original = sys.stdout
        with tempfile.TemporaryDirectory() as tmp:
            paths = E.setup_storage_paths(base_dir=tmp, mount_drive=False)
            _, restore = E.open_run_log(paths, E.run_timestamp())
            self.assertIsNot(sys.stdout, original)
            restore()
        self.assertIs(sys.stdout, original)

    def test_run_summary_is_valid_json(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            paths = E.setup_storage_paths(base_dir=tmp, mount_drive=False)
            stamp = E.run_timestamp()
            summary_path = E.write_run_summary(paths, stamp, {"status": "ok", "passed": 3})
            payload = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["passed"], 3)
            self.assertEqual(payload["timestamp"], stamp)
            self.assertEqual(payload["schema_version"], E.SCHEMA_VERSION)
            self.assertEqual(payload["data_root"], str(paths["root"]))

    def test_logs_directory_is_part_of_the_layout(self):
        self.assertIn("logs", E.STORAGE_SUBDIRS)
        self.assertIn("reports", E.STORAGE_SUBDIRS)
        self.assertIn("watchlists", E.STORAGE_SUBDIRS)
        self.assertIn("fundamentals", E.STORAGE_SUBDIRS)


class ImportPurity(unittest.TestCase):
    def test_import_did_not_touch_the_data_root(self):
        # setup_storage_paths is reachable only from main(), so importing must
        # neither create the data root nor add a single file to it.
        after = _snapshot_data_tree()
        self.assertEqual(
            after, _DATA_TREE_BEFORE_IMPORT,
            "importing the engine changed the data root; it must have no side effects",
        )

    def test_import_left_process_state_alone(self):
        # The engine used to silence every warning, reseed NumPy and change
        # pandas display options at import time. Now only main() seeds NumPy,
        # and nothing changes warning filters or pandas options at all.
        self.assertEqual(_STATE_AROUND_IMPORT["after"], _STATE_AROUND_IMPORT["before"])

    def test_import_did_not_create_the_legacy_directory(self):
        self.assertEqual((ROOT / "IndianStockEngine").exists(), _LEGACY_DIR_BEFORE_IMPORT,
                         "the legacy IndianStockEngine directory must not reappear")

    def test_default_data_root_is_project_local(self):
        # The README tells you to set TRADEBOT_DATA_DIR; these two tests assert
        # the default, so they must not inherit it from the environment.
        with without_data_dir_env():
            root, how = E.resolve_data_root(mount_drive=False)
        self.assertEqual(root.name, E.DEFAULT_DATA_DIR_NAME)
        self.assertIn("project-local", how)

    def test_xlsx_is_rejected_by_the_adapter(self):
        adapter = E.FundamentalsAdapter(ROOT)
        with self.assertRaises(ValueError):
            adapter.load(Path("book.xlsx"))
        self.assertEqual(E.FundamentalsAdapter.SUPPORTED_SUFFIXES, (".csv",))

    def test_market_data_provider_is_injectable(self):
        calls = []
        provider = E.MarketDataProvider(ROOT, downloader=lambda s, p: calls.append((s, p)) or "F")
        self.assertEqual(provider.fetch(["TCS"], "2015-01-01"), "F")
        self.assertEqual(calls, [(["TCS"], "2015-01-01")])


def fake_download(calls, priced=None):
    """A yfinance-shaped downloader: 300 rising sessions per symbol plus the benchmark.

    priced limits which requested tickers get prices (None means all), to
    imitate a partial, rate-limited download.
    """
    import pandas as pd

    def download(symbols, period):
        calls.append((tuple(symbols), period))
        index = pd.date_range("2024-01-01", periods=300, freq="B")
        data = {}
        chosen = [s for s in symbols if priced is None or s in priced]
        for n, symbol in enumerate([E.yahoo_symbol(s) for s in chosen] + [E.BENCHMARK_SYMBOL]):
            data[("Close", symbol)] = [100.0 + n + 0.5 * i for i in range(300)]
            data[("Volume", symbol)] = [1000.0 + i for i in range(300)]
        return pd.DataFrame(data, index=index)

    return download


class PipelineWithPriceHistory(unittest.TestCase):
    """run_pipeline end to end, offline, with an injected yfinance-shaped download."""

    APP = dict(E.DEFAULT_APP_CONFIG, universe_mode="custom", custom_symbols=[], minimum_total_score=0)

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.paths = quiet(E.setup_storage_paths, base_dir=self._tmp.name, mount_drive=False)
        E._fixture_frame().to_csv(self.paths["fundamentals"] / "export.csv", index=False)
        self.calls = []

    def tearDown(self):
        self._tmp.cleanup()

    # A fixed date, so a run that crosses midnight cannot change which cache
    # file counts as "today".
    TODAY = datetime.date(2026, 9, 12)

    def run_once(self, stamp, allow_network=True, priced=None):
        return quiet(E.run_pipeline, self.paths, self.APP, E.DEFAULT_SCREENING_CONFIG,
                     allow_network=allow_network, stamp=stamp, today=self.TODAY,
                     downloader=fake_download(self.calls, priced))

    def age_todays_file(self, artefacts):
        """Rename the price file a run saved so it looks like it came from 2000-01-01."""
        saved = Path(artefacts["price_history_csv"])
        self.assertIn(self.TODAY.strftime("%Y%m%d"), saved.name)
        older = saved.with_name(saved.name.replace(saved.name.split("_")[2], "20000101"))
        saved.rename(older)
        return older

    def test_partial_download_never_hides_a_more_complete_file(self):
        _, first = self.run_once("t1")
        older = self.age_todays_file(first)
        result, artefacts = self.run_once("t2", priced={"ALPHA"})
        self.assertEqual(Path(artefacts["price_history_csv"]), older)
        self.assertIn("today's download priced only 1 of 2 tickers", artefacts["price_history_source"])
        self.assertIsNotNone({e["ticker"]: e for e in result["evaluations"]}["BETA"]["techScore"])

    def test_benchmark_only_download_counts_as_no_prices(self):
        result, artefacts = self.run_once("t1", priced=set())
        self.assertIsNone(artefacts["price_history_csv"])
        self.assertIn("no prices for these tickers", artefacts["price_history_source"])
        self.assertEqual(result["evaluations"][0]["techBreakdown"], ["No price history loaded"])

    def test_partial_file_from_today_is_retried(self):
        _, partial = self.run_once("t1", priced={"ALPHA"})
        self.assertEqual(partial["price_history_source"], "downloaded (1 of 2 tickers)")
        _, full = self.run_once("t2")
        self.assertEqual(full["price_history_source"], "downloaded")
        _, again = self.run_once("t3")
        self.assertEqual(again["price_history_source"], "cached earlier today")
        self.assertEqual(len(self.calls), 2)

    def test_download_feeds_technical_scores_and_is_saved(self):
        result, artefacts = self.run_once("t1")
        self.assertEqual(artefacts["price_history_source"], "downloaded")
        saved = Path(artefacts["price_history_csv"])
        self.assertTrue(saved.exists())
        self.assertEqual(saved.parent, self.paths["market_data"])
        self.assertEqual(saved.read_text(encoding="utf-8").splitlines()[0],
                         "Date,Ticker,Open,High,Low,Close,Volume")
        by_ticker = {e["ticker"]: e for e in result["evaluations"]}
        self.assertEqual(by_ticker["ALPHA"]["techScore"], 100.0)
        self.assertEqual(by_ticker["ALPHA"]["dataStatus"], "COMPLETE")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(sorted(self.calls[0][0]), ["ALPHA", "BETA"])
        watchlist_row = Path(artefacts["watchlist_csv"]).read_text(encoding="utf-8").splitlines()[1]
        self.assertEqual(watchlist_row.split(",")[7], "100.0")

    def test_same_day_rerun_reuses_the_saved_file(self):
        self.run_once("t1")
        _, artefacts = self.run_once("t2")
        self.assertEqual(artefacts["price_history_source"], "cached earlier today")
        self.assertEqual(len(self.calls), 1, "the second run must not download again")

    def test_offline_run_without_cache_has_no_per_stock_warning(self):
        result, artefacts = self.run_once("t1", allow_network=False)
        self.assertIsNone(artefacts["price_history_csv"])
        self.assertEqual(artefacts["price_history_source"], "offline run")
        self.assertEqual(self.calls, [])
        for evaluation in result["evaluations"]:
            self.assertIsNone(evaluation["techScore"])
            self.assertEqual(evaluation["techBreakdown"], ["No price history loaded"])
            self.assertNotIn("Technical Data Missing", evaluation["warningFlags"])

    def test_offline_run_uses_an_earlier_cached_file(self):
        _, first = self.run_once("t1")
        older = self.age_todays_file(first)
        result, artefacts = self.run_once("t2", allow_network=False)
        self.assertEqual(Path(artefacts["price_history_csv"]), older)
        self.assertEqual(artefacts["price_history_source"], "cached on 2000-01-01, because offline run")
        self.assertIsNotNone({e["ticker"]: e for e in result["evaluations"]}["ALPHA"]["techScore"])

    def test_failed_download_is_reported_not_raised(self):
        def broken(symbols, period):
            raise OSError("no route to host")

        result, artefacts = quiet(E.run_pipeline, self.paths, self.APP, E.DEFAULT_SCREENING_CONFIG,
                                  allow_network=True, stamp="t1", downloader=broken)
        self.assertIn("no route to host", artefacts["price_history_source"])
        self.assertIsNone(result["evaluations"][0]["techScore"])


class FundamentalsParsing(unittest.TestCase):
    def test_text_cells_are_kept_as_text(self):
        # pandas would turn "NA", "None" and "N/A" into blanks by default,
        # losing a ticker the browser keeps.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "export.csv"
            path.write_text("Name,NSE Code,Industry,Market Capitalization\n"
                            "None,NA,N/A,5000\nReal Ltd,REAL,,\n", encoding="utf-8")
            stocks, _, _ = engine().prepare(E.FundamentalsAdapter(tmp).load(path))
        self.assertEqual([(s["ticker"], s["name"], s["sector"]) for s in stocks],
                         [("NA", "None", "N/A"), ("REAL", "Real Ltd", "")])
        self.assertEqual(stocks[0]["marketCap"], 5000.0)
        self.assertIsNone(stocks[1]["marketCap"])


class FundamentalsDate(unittest.TestCase):
    """The staleness check must use the data's date, not the file's mtime."""

    HEADER = "Name,NSE Code,Market Capitalization"

    def write(self, directory, name, text):
        path = Path(directory) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_date_column_in_the_export_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "export.csv",
                              "%s,Date\nAlpha Ltd,AAA,5000,2026-09-01\nBeta Ltd,BBB,6000,2026-08-30\n"
                              % self.HEADER)
            frame = E.read_fundamentals_csv(path)
            as_of, source = E.fundamentals_as_of(frame, path)
            self.assertEqual(as_of, datetime.date(2026, 9, 1))
            self.assertEqual(source, "data date")

    def test_iso_date_in_the_file_name_is_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "screener_export_2026-08-15.csv",
                              "%s\nAlpha Ltd,AAA,5000\n" % self.HEADER)
            as_of, source = E.fundamentals_as_of(E.read_fundamentals_csv(path), path)
            self.assertEqual(as_of, datetime.date(2026, 8, 15))
            self.assertEqual(source, "file name")

    def test_file_timestamp_is_the_labelled_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "export.csv", "%s\nAlpha Ltd,AAA,5000\n" % self.HEADER)
            os.utime(path, (1757000000, 1757000000))
            as_of, source = E.fundamentals_as_of(E.read_fundamentals_csv(path), path)
            self.assertEqual(as_of, datetime.date.fromtimestamp(1757000000))
            self.assertEqual(source, "file timestamp")

    def test_a_copied_old_export_is_still_reported_stale(self):
        # The bug: copying an old export reset its mtime and the run called it
        # "0 days old" even though the data inside was months old.
        with tempfile.TemporaryDirectory() as tmp:
            path = self.write(tmp, "export.csv",
                              "%s,Date\nAlpha Ltd,AAA,5000,2026-01-05\n" % self.HEADER)
            age, source = E.fundamentals_age_days(E.read_fundamentals_csv(path), path)
            self.assertEqual(source, "data date")
            self.assertEqual(age, (datetime.date.today() - datetime.date(2026, 1, 5)).days)


class UniverseCache(unittest.TestCase):
    """A live refresh writes cache/nifty100_constituents_cache.csv; it must be read back."""

    def write_cache(self, directory, symbols, when):
        path = Path(directory) / "nifty100_constituents_cache.csv"
        rows = "\n".join("Co %s,Industry,%s,EQ,INE000A0%04d" % (s, s, i)
                         for i, s in enumerate(symbols))
        path.write_text("Company Name,Industry,Symbol,Series,ISIN Code\n%s\n" % rows, encoding="utf-8")
        stamp = datetime.datetime.combine(when, datetime.time(12, 0)).timestamp()
        os.utime(path, (stamp, stamp))
        return path

    def newer_symbols(self):
        symbols = list(E.NIFTY100_FALLBACK_SYMBOLS)
        symbols[0] = "NEWLISTING"
        return symbols

    def test_a_newer_cache_is_used_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_date = datetime.date.fromisoformat(E.NIFTY100_PROVENANCE["as_of_date"])
            self.write_cache(tmp, self.newer_symbols(), snapshot_date + datetime.timedelta(days=30))
            provider = E.UniverseProvider(tmp)
            symbols = quiet(provider.get_universe, "nifty100", allow_network=False)
            self.assertIn("NEWLISTING", symbols)
            self.assertEqual(len(symbols), 100)
            self.assertIn("cached NSE list", provider.describe_source())

    def test_a_cache_older_than_the_snapshot_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot_date = datetime.date.fromisoformat(E.NIFTY100_PROVENANCE["as_of_date"])
            self.write_cache(tmp, self.newer_symbols(), snapshot_date - datetime.timedelta(days=5))
            provider = E.UniverseProvider(tmp)
            symbols = quiet(provider.get_universe, "nifty100", allow_network=False)
            self.assertNotIn("NEWLISTING", symbols)
            self.assertIn("cached snapshot", provider.describe_source())

    def test_a_malformed_cache_falls_back_to_the_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nifty100_constituents_cache.csv"
            path.write_text("not,a,constituent,list\n1,2,3,4\n", encoding="utf-8")
            provider = E.UniverseProvider(tmp)
            symbols = quiet(provider.get_universe, "nifty100", allow_network=False)
            self.assertEqual(symbols, list(E.NIFTY100_FALLBACK_SYMBOLS))
            self.assertIn("cached snapshot", provider.describe_source())


class RunConfiguration(unittest.TestCase):
    def test_config_file_in_the_data_root_is_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = quiet(E.setup_storage_paths, base_dir=tmp, mount_drive=False)
            (paths["config"] / E.CONFIG_FILENAME).write_text(json.dumps({"app": {"top_n": 5}}))
            app, screening, source = E.load_run_config(paths)
            self.assertEqual(app["top_n"], 5)
            self.assertEqual(screening, E.DEFAULT_SCREENING_CONFIG)
            self.assertTrue(source.endswith(E.CONFIG_FILENAME))

    def test_defaults_apply_without_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = quiet(E.setup_storage_paths, base_dir=tmp, mount_drive=False)
            app, _, source = E.load_run_config(paths)
            self.assertEqual(app, E.DEFAULT_APP_CONFIG)
            self.assertTrue(source.startswith("defaults"))

    def test_invalid_config_stops_the_run_with_exit_code_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({"app": {"top_n": 0, "paper_trading_only": True}}))
            code = quiet(E.main, ["--data-dir", tmp, "--config", str(bad), "--offline"])
            self.assertEqual(code, 2)
            summary = json.loads(next((Path(tmp) / "logs").glob("run_*.json")).read_text())
            self.assertEqual(summary["status"], "invalid_config")
            self.assertEqual(summary["exit_code"], 2)
            self.assertIn("app.top_n must be between 1 and 100", summary["error"])
            self.assertIn("Unknown app setting: paper_trading_only", summary["error"])

    def test_configured_run_records_its_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = quiet(E.setup_storage_paths, base_dir=tmp, mount_drive=False)
            E._fixture_frame().to_csv(paths["fundamentals"] / "export.csv", index=False)
            config = Path(tmp) / "mine.json"
            config.write_text(json.dumps({"app": {"universe_mode": "custom", "top_n": 3}}))
            self.assertEqual(quiet(E.main, ["--data-dir", tmp, "--config", str(config), "--offline"]), 0)
            summary = json.loads(next((Path(tmp) / "logs").glob("run_*.json")).read_text())
            self.assertEqual(summary["status"], "ok")
            self.assertEqual(summary["config"]["app"]["top_n"], 3)
            self.assertEqual(summary["config_source"], str(config.resolve()))

    def test_command_line_flags(self):
        self.assertEqual(quiet(E.main, ["--help"]), 0)
        self.assertEqual(quiet(E.main, ["--no-such-flag"]), 2)


def build_suite() -> unittest.TestSuite:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    # 1. The notebook's own offline tests.
    suite.addTests(loader.loadTestsFromTestCase(E.EngineTests))
    # 2. The additional contract and parity tests defined above.
    for case in (CanonicalTypeContract, UniverseProviderContract, CleanNumericSignature,
                 IdentifierMappingParity, TechnicalHistorySemantics, CsvExportSafety,
                 DeltaSchema, ScoringAndOrdering, StorageAndLogging, ImportPurity,
                 PipelineWithPriceHistory, FundamentalsParsing, FundamentalsDate,
                 UniverseCache, RunConfiguration):
        suite.addTests(loader.loadTestsFromTestCase(case))
    # 3. Optional network tests, only when explicitly enabled.
    if os.environ.get("RUN_NETWORK_TESTS") == "1":
        suite.addTests(loader.loadTestsFromTestCase(E.NetworkIntegrationTests))
    return suite


if __name__ == "__main__":
    print("Engine loaded from %s" % NOTEBOOK.name)
    print("Universe snapshot: cached as of %s" % E.NIFTY100_PROVENANCE["as_of_date"])
    print("Network tests: %s"
          % ("ENABLED" if os.environ.get("RUN_NETWORK_TESTS") == "1" else "skipped (optional)"))
    runner = unittest.TextTestRunner(verbosity=2)
    outcome = runner.run(build_suite())
    print("\nran=%d failures=%d errors=%d skipped=%d"
          % (outcome.testsRun, len(outcome.failures), len(outcome.errors), len(outcome.skipped)))
    # Any failed subtest exits non-zero.
    raise SystemExit(0 if outcome.wasSuccessful() else 1)
