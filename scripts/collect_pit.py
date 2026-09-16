#!/usr/bin/env python3
"""Collect one point-in-time fundamentals vintage, safely and repeatably.

WHY THIS EXISTS. The fundamental half of the engine cannot be tested at all:
Yahoo serves only current values, so applying today's balance sheet to 2016 is
look-ahead. The only route to a testable fundamental model is an archive that
accumulates one honest vintage per month, and the engine itself says a
fundamental backtest needs about twelve. That clock does not start until
collection runs without a human remembering to run it.

WHAT THIS ADDS over calling the adapter directly:

  IDEMPOTENT PER MONTH. The engine's archive de-duplicates by content hash,
  which is the right rule for an export someone re-uploads. It is the WRONG
  rule for a scheduled job: Yahoo's numbers drift between minutes, so a job
  that ran twice in March would file two March vintages that differ by a
  rounding and pretend to be two observations. One vintage per month is the
  contract; a second run in the same month is a no-op unless forced.

  DRIFT DETECTED BEFORE THE WRITE, NOT AFTER. A silently changed convention is
  the failure this archive cannot survive -- if Yahoo flips `dividendYield`
  back to a fraction, every later vintage is wrong in a way no later inspection
  can distinguish from a real collapse in yields. So the unit contract is
  re-verified against live data on every collection, by reconstruction, and a
  failure ABORTS rather than writes. An empty month is recoverable. A month of
  quietly mis-scaled data is not.

  PROVENANCE BEYOND THE NUMBERS. Each vintage records the adapter's source
  hash, the yfinance version, the contract-check result, and per-column
  coverage. "Yahoo meant X but our September adapter read it as Y" is only
  repairable if the manifest says which adapter that was.

Usage:
    scripts/venv-python.sh scripts/collect_pit.py [--force] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

ARCHIVE = ROOT / "data-store" / "fundamentals" / "archive"
MANIFEST = ARCHIVE / "manifest.jsonl"
LIVE_DIR = ROOT / "data-store" / "fundamentals"
RAW_DIR = LIVE_DIR / "raw"

# Small, fixed, and chosen so a convention flip cannot hide: a bank (fields
# Yahoo often omits), an IT firm reporting in USD, a high-yield payer, and a
# leveraged name. Four tickers is enough to distinguish a unit change from one
# company's bad day, and cheap enough to run every month.
CONTRACT_SAMPLE = ["TCS", "HDFCBANK", "VEDL", "INFY"]

# A contract check needs a majority to agree before it will let a write happen.
# Requiring unanimity would make one delisted or halted ticker block the month.
MIN_AGREEING = 2


def month_key(today=None):
    return (today or dt.date.today()).strftime("%Y-%m")


def existing_vintages(month):
    """Manifest entries already filed for `month`, newest last."""
    if not MANIFEST.exists():
        return []
    out = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(entry.get("as_of", "")).startswith(month):
            out.append(entry)
    return out


def adapter_fingerprint():
    """Hash of the code that did the normalising, not just of its output."""
    body = (ROOT / "scripts" / "yahoo_fundamentals.py").read_bytes()
    return hashlib.sha256(body).hexdigest()


def check_contract(yf):
    """Re-verify the unit contract against live data. Returns (ok, report).

    Reconstruction, not assertion: each field is rebuilt from the statements
    and compared on SCALE. This is the same machinery as the audit, run as a
    gate instead of as a report.
    """
    from yahoo_contract_audit import audit_one, fetch

    watched = ("debtToEquity", "returnOnEquity", "dividendYield", "marketCap")
    tally = {field: {"agree": 0, "disagree": 0, "absent": 0} for field in watched}
    detail = {}
    for symbol in CONTRACT_SAMPLE:
        payload = fetch(yf, symbol)
        if "error" in payload:
            for field in watched:
                tally[field]["absent"] += 1
            detail[symbol] = "fetch failed"
            continue
        checks = audit_one(payload)
        detail[symbol] = {}
        for field in watched:
            verdict = checks.get(field, {}).get("agrees")
            bucket = ("agree" if verdict is True
                      else "disagree" if verdict is False else "absent")
            tally[field][bucket] += 1
            detail[symbol][field] = bucket

    failures = []
    for field, counts in tally.items():
        if counts["agree"] < MIN_AGREEING:
            failures.append(
                "%s: only %d of %d agreed (%d disagreed, %d unavailable)"
                % (field, counts["agree"], len(CONTRACT_SAMPLE),
                   counts["disagree"], counts["absent"]))
    return (not failures), {"tally": tally, "per_ticker": detail,
                            "failures": failures}


def check_schema(path, expected_columns):
    """Header drift. A renamed or dropped column must stop the run."""
    with path.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle), [])
    missing = [c for c in expected_columns if c not in header]
    extra = [c for c in header if c not in expected_columns]
    return (not missing and not extra), {"missing": missing, "extra": extra}


def coverage(path):
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {}, 0
    return ({column: sum(1 for r in rows if r.get(column))
             for column in rows[0]}, len(rows))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--force", action="store_true",
                        help="collect even though this month already has a vintage")
    parser.add_argument("--dry-run", action="store_true",
                        help="run every check, write nothing")
    parser.add_argument("--skip-contract-check", action="store_true",
                        help="NOT for scheduled use; skips the drift gate")
    args = parser.parse_args()

    warnings.filterwarnings("ignore")
    today = dt.date.today()
    month = month_key(today)
    print("PIT collection for %s" % month)

    already = existing_vintages(month)
    if already and not args.force:
        print("  SKIP: %d vintage(s) already filed for %s (%s)."
              % (len(already), month,
                 ", ".join(Path(e["archived_path"]).name for e in already)))
        print("  One vintage per month is the contract. Use --force to override.")
        return 0

    try:
        import yfinance as yf
    except ImportError:
        print("  ABORT: yfinance is not installed.", file=sys.stderr)
        return 1

    import yahoo_fundamentals as adapter

    if args.skip_contract_check:
        contract_ok, contract_report = None, {"skipped": True}
        print("  contract check SKIPPED by flag")
    else:
        print("  checking the unit contract against live data ...")
        contract_ok, contract_report = check_contract(yf)
        for field, counts in contract_report["tally"].items():
            print("     %-16s agree %d  disagree %d  unavailable %d"
                  % (field, counts["agree"], counts["disagree"], counts["absent"]))
        if not contract_ok:
            print("\n  ABORT: the unit contract no longer holds.", file=sys.stderr)
            for failure in contract_report["failures"]:
                print("     %s" % failure, file=sys.stderr)
            print("\n  Nothing was written. A missing month is recoverable; a "
                  "month of mis-scaled data is not.\n"
                  "  Re-run scripts/yahoo_contract_audit.py and update "
                  "knowledge/yahoo-data-contract.md before collecting again.",
                  file=sys.stderr)
            return 2
        print("  contract holds.")

    # Raw snapshots first: if normalising is wrong, only these can repair it.
    if not args.dry_run:
        from yahoo_contract_audit import fetch as audit_fetch, snapshot
        stamp = today.strftime("%Y%m%d")
        for symbol in CONTRACT_SAMPLE:
            payload = audit_fetch(yf, symbol)
            if "error" not in payload:
                snapshot(payload, RAW_DIR, stamp)
        print("  raw responses snapshotted for %d ticker(s)" % len(CONTRACT_SAMPLE))

    print("  building the export ...")
    universe = [r for r in csv.DictReader(
        (ROOT / "data" / "nifty100_source.csv").open(encoding="utf-8"))
        if r.get("Symbol")]
    rows, failures, fx_cache = [], [], {}
    for entry in universe:
        symbol = entry["Symbol"].strip()
        row, notes = adapter.fetch_one(yf, symbol,
                                       entry.get("Company Name", "").strip(),
                                       entry.get("Industry", "").strip(), fx_cache)
        if row is None:
            failures.append(symbol)
            continue
        alarms, rejections = adapter.validate_row(row)
        if rejections:
            print("     %-12s %s" % (symbol, "; ".join(rejections)))
        rows.append(row)

    if not rows:
        print("  ABORT: nothing fetched.", file=sys.stderr)
        return 1

    target = LIVE_DIR / ("yahoo_fundamentals_%s.csv" % today.strftime("%Y%m%d"))
    if args.dry_run:
        print("  DRY RUN: %d rows ready, %d skipped. Nothing written."
              % (len(rows), len(failures)))
        return 0

    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=adapter.COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    schema_ok, schema_report = check_schema(target, adapter.COLUMNS)
    if not schema_ok:
        print("  ABORT: schema drift -- missing %s, unexpected %s"
              % (schema_report["missing"], schema_report["extra"]), file=sys.stderr)
        target.unlink()
        return 3

    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    filled, row_count = coverage(target)
    month_dir = ARCHIVE / month
    month_dir.mkdir(parents=True, exist_ok=True)
    archived = month_dir / ("%s_%s.csv" % (today.isoformat(), digest[:12]))
    archived.write_bytes(target.read_bytes())

    record = {
        "archived_at": today.isoformat(), "as_of": today.isoformat(),
        "as_of_source": "collect_pit.py run date",
        "archived_path": str(archived), "original_name": target.name,
        "sha256": digest, "rows": row_count, "columns": len(adapter.COLUMNS),
        "collector": "collect_pit.py",
        "adapter_sha256": adapter_fingerprint(),
        "yfinance_version": getattr(yf, "__version__", "unknown"),
        "contract_check": contract_report,
        "coverage": filled,
        "skipped_tickers": failures,
    }
    with MANIFEST.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")

    print("\n  wrote %s" % target.name)
    print("  archived %s" % archived.name)
    print("  %d rows, %d skipped, adapter %s, yfinance %s"
          % (row_count, len(failures), record["adapter_sha256"][:12],
             record["yfinance_version"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
