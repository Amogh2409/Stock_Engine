"""Cross-engine parity driver.

Reads a JSON job from stdin, imports the engine module extracted from the
GENERATED notebook (path given as argv[1]), and writes one JSON object to
stdout.

Fails closed. Any missing dependency, malformed job, absent engine symbol or
unexpected row count raises, which exits non-zero and fails the calling test.
There is no fallback output and no hard-coded expected result anywhere in this
file -- if the engine cannot run, the test must not pass.
"""
import importlib.util
import io
import json
import sys


def die(message):
    sys.stderr.write("parity_driver: %s\n" % message)
    sys.exit(1)


def load_engine(module_path):
    spec = importlib.util.spec_from_file_location("notebook_engine", module_path)
    if spec is None or spec.loader is None:
        die("could not create module spec for %s" % module_path)
    module = importlib.util.module_from_spec(spec)
    # Importing must not mount Drive, hit the network or run the pipeline.
    spec.loader.exec_module(module)
    required = [
        "ScreeningEngine", "resolve_columns", "clean_numeric", "round1",
        "escape_csv_cell", "compute_ranking_changes", "ranking_changes_to_csv",
        "watchlist_to_csv", "rejected_to_csv", "compute_technical_indicators",
        "dedupe_stocks", "NIFTY100_FALLBACK_SYMBOLS", "NIFTY100_PROVENANCE",
        "parse_price_history_csv", "technicals_from_history", "js_number_to_string",
        "parse_strict_decimal", "normalize_header", "js_trim", "validate_config_document",
        "CONFIG_LIMITS", "read_fundamentals_csv",
    ]
    missing = [name for name in required if not hasattr(module, name)]
    if missing:
        die("engine module is missing required symbols: %s" % ", ".join(missing))
    return module


def run_screen(engine, pd, spec, expected_rows=None):
    """One screen, set up the way processScreenerPipeline() sets it up in TS."""
    frame = engine.read_fundamentals_csv(io.StringIO(spec["csv"]))
    if expected_rows is not None and len(frame) != expected_rows:
        die("input CSV has %d rows, job expected %d" % (len(frame), expected_rows))
    app = spec["app_config"]
    universe = None
    if app.get("universe_mode") == "nifty100":
        universe = list(engine.NIFTY100_FALLBACK_SYMBOLS)
    elif app.get("custom_symbols"):
        # Through the same normalisation the real pipeline applies, so a custom
        # list with stray case or spaces is compared like for like.
        universe = engine.normalise_symbols(app["custom_symbols"])

    history, skipped = None, None
    if spec.get("price_csv") is not None:
        history, skipped = engine.parse_price_history_csv(spec["price_csv"])

    mapping = engine.resolve_columns(frame.columns)
    screener = engine.ScreeningEngine(app, spec["screening_config"])
    result = screener.screen(frame, mapping=mapping, universe=universe, price_history=history)
    tickers = [item["ticker"] for item in result["evaluations"]]
    return {
        "mapping": mapping,
        "duplicates_removed": result["duplicates_removed"],
        "outside_universe": result["outside_universe"],
        "price_rows_skipped": skipped,
        "evaluations": [
            {
                "ticker": item["ticker"],
                "passed": bool(item["passed"]),
                "score": item["score"],
                "composite": item["composite"],
                "compositeBasis": item["compositeBasis"],
                "verdict": item["verdict"],
                "coverage": item["coverage"],
                "reasons": list(item["reasons"]),
                "warningFlags": list(item["warningFlags"]),
                "categoryScores": item["categoryScores"],
                "redFlags": list(item["redFlags"]),
                "notScored": item["notScored"],
                "scoringModel": item["scoringModel"],
                "scoreLines": list(item["scoreLines"]),
                "sectorGroup": item["sectorGroup"],
                # Cross-sectional, so it is attached after scoring. Compared
                # here because a peer median computed differently in the two
                # engines would otherwise be invisible.
                "sectorRelativeStrength6M": item["sectorRelativeStrength6M"],
                "sectorRelativeStrengthBasis": item["sectorRelativeStrengthBasis"],
                "techScore": item["techScore"],
                "techBreakdown": list(item["techBreakdown"]),
                # The four block subtotals, so the engines are compared on the
                # breakdown rather than merely on the total they add up to.
                "technicalBlocks": item["technicalBlocks"],
                "dataStatus": item["dataStatus"],
                "explanation": item["explanation"],
            }
            for item in result["evaluations"]
        ],
        "watchlist": [
            {"ticker": item["ticker"], "rank": item["rank"], "score": item["score"]}
            for item in result["watchlist"]
        ],
        "passed_below_cutoff": [
            {"ticker": item["ticker"], "rank": item["rank"], "score": item["score"]}
            for item in result["passed_below_cutoff"]
        ],
        # Passing companies this run could not price, ranked apart from the ones
        # it could: a composite with no technical half is not on the same scale.
        "fundamental_only": [
            {"ticker": item["ticker"], "rank": item["rank"], "score": item["score"]}
            for item in result["fundamental_only"]
        ],
        "watchlist_csv": engine.watchlist_to_csv(result["watchlist"]),
        "passed_below_csv": engine.watchlist_to_csv(result["passed_below_cutoff"]),
        "rejected_csv": engine.rejected_to_csv(result["rejected"]),
        "technicals": None if history is None else engine.technicals_from_history(history, tickers),
    }


def main():
    if len(sys.argv) < 2:
        die("usage: parity_driver.py <engine_module.py>")
    try:
        import pandas as pd  # required; absence must fail the test
    except ImportError as exc:
        die("required Python dependency missing: %s" % exc)

    engine = load_engine(sys.argv[1])

    try:
        job = json.loads(sys.stdin.read())
    except ValueError as exc:
        die("could not parse job JSON from stdin: %s" % exc)

    for key in ("csv", "app_config", "screening_config", "delta_fixture"):
        if key not in job:
            die("job is missing required key: %s" % key)

    base = run_screen(engine, pd, job, job.get("expected_rows"))
    fixture = job["delta_fixture"]
    changes = engine.compute_ranking_changes(fixture["current"], fixture["previous"])

    config_results = []
    for document in job.get("config_cases", []):
        app, screening, errors = engine.validate_config_document(document)
        config_results.append({"valid": not errors, "errors": errors, "app": app, "screening": screening})

    price_parse_results = []
    for text in job.get("price_parse_cases", []):
        try:
            history, skipped = engine.parse_price_history_csv(text)
            price_parse_results.append({"error": False, "history": history, "skipped": skipped})
        except ValueError:
            price_parse_results.append({"error": True})

    payload = {
        "engine": "python",
        "mapping": base["mapping"],
        "duplicates_removed": base["duplicates_removed"],
        "evaluations": base["evaluations"],
        "watchlist": base["watchlist"],
        "watchlist_csv": base["watchlist_csv"],
        "rejected_csv": base["rejected_csv"],
        "ranking_changes_csv": engine.ranking_changes_to_csv(changes),
        "screens": {spec["label"]: run_screen(engine, pd, spec) for spec in job.get("screens", [])},
        "universe": {
            "count": len(engine.NIFTY100_FALLBACK_SYMBOLS),
            "symbols": list(engine.NIFTY100_FALLBACK_SYMBOLS),
            "provenance": engine.NIFTY100_PROVENANCE,
        },
        "unit_parsing": {
            case["label"]: engine.clean_numeric(case["value"], case["unit"])
            for case in job.get("unit_cases", [])
        },
        "csv_escapes": {
            case: engine.escape_csv_cell(case) for case in job.get("escape_cases", [])
        },
        "technical_availability": {
            str(n): engine.compute_technical_indicators(
                [100.0 + i * 0.5 for i in range(n)]
            )["available"]["high52Week"]
            for n in job.get("technical_sizes", [])
        },
        "identifier_mappings": {
            case["label"]: engine.resolve_columns(case["headers"])
            for case in job.get("mapping_cases", [])
        },
        "number_text": [engine.js_number_to_string(n) for n in job.get("number_cases", [])],
        "strict_decimals": [engine.parse_strict_decimal(s) for s in job.get("strict_decimal_cases", [])],
        "whitespace_numbers": [engine.clean_numeric(s, "ratio") for s in job.get("whitespace_cases", [])],
        "trimmed": [engine.js_trim(s) for s in job.get("whitespace_cases", [])],
        "headers": [engine.normalize_header(h) for h in job.get("header_cases", [])],
        "config_limits": {key: list(bounds) for key, bounds in engine.CONFIG_LIMITS.items()},
        "config_results": config_results,
        "price_parse_results": price_parse_results,
    }

    if not payload["evaluations"]:
        die("engine produced zero evaluations; refusing to report success")

    json.dump(payload, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
