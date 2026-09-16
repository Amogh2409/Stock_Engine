#!/usr/bin/env python3
"""Is the point-in-time archive actually fit to test a fundamental model yet?

WHY THIS EXISTS. The archive is now the scarce asset in this project: the
technical family has been measured to exhaustion and frozen, and every
remaining fundamental question -- block attribution, the 50-point gate, the
fundamental weights -- is blocked on having vintages that were true when they
were written. That makes the archive's own condition a thing to measure rather
than assume.

The question this answers is not "how many files are there". It is: if a
fundamental backtest were run today, what would it silently be built on? A
missing month is a gap in the panel. A column that quietly stopped being
populated is worse -- it looks like data and behaves like absence. A superseded
vintage that nobody marked is worst of all, because it is a known-wrong
observation still presenting itself as evidence.

Usage:
    scripts/venv-python.sh scripts/archive_health.py [--json OUT]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "data-store" / "fundamentals" / "archive"
MANIFEST = ARCHIVE / "manifest.jsonl"
RAW = ROOT / "data-store" / "fundamentals" / "raw"
UNIVERSE = ROOT / "data" / "nifty100_source.csv"

# The engine's own statement of what a fundamental backtest needs. Repeated
# here as a number so the report can say how far off it is rather than leaving
# the reader to judge.
VINTAGES_NEEDED = 12

# Columns whose absence is not a defect: they are empty by design and the
# reasons are in the adapter's docstring.
EMPTY_BY_DESIGN = {"BSE code", "Pledged percentage", "Gross NPA %",
                   "Net NPA %", "Capital adequacy ratio"}


def read_manifest():
    if not MANIFEST.exists():
        return []
    out = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def months_between(first, last):
    """Every YYYY-MM from first to last inclusive, so gaps can be named."""
    out, year, month = [], first.year, first.month
    while (year, month) <= (last.year, last.month):
        out.append("%04d-%02d" % (year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def load_rows(path):
    try:
        with Path(path).open(newline="", encoding="utf-8") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    entries = read_manifest()
    if not entries:
        print("No archive manifest. Nothing has been collected yet.")
        return 1

    # A superseded vintage is known-wrong data that still looks like evidence,
    # so it is excluded from the usable panel but never deleted -- it records
    # what was believed on the day.
    superseded_hashes = {e["supersedes"] for e in entries if e.get("supersedes")}
    usable = [e for e in entries if e.get("sha256") not in superseded_hashes]
    retired = [e for e in entries if e.get("sha256") in superseded_hashes]

    by_month = {}
    for entry in usable:
        by_month.setdefault(str(entry.get("as_of", ""))[:7], []).append(entry)

    dates = sorted(dt.date.fromisoformat(e["as_of"]) for e in usable
                   if e.get("as_of"))
    span = months_between(dates[0], dates[-1]) if dates else []
    missing = [m for m in span if m not in by_month]
    duplicated = {m: len(v) for m, v in by_month.items() if len(v) > 1}

    print("=" * 72)
    print("PIT FUNDAMENTALS ARCHIVE -- HEALTH")
    print("=" * 72)
    print()
    print("Vintages      %d usable (%d retired as superseded)"
          % (len(usable), len(retired)))
    print("Span          %s to %s -- %d month(s)"
          % (span[0] if span else "-", span[-1] if span else "-", len(span)))
    print("Months held   %d of %d in span" % (len(by_month), len(span)))
    if missing:
        print("MISSING       %s" % ", ".join(missing))
    if duplicated:
        print("DUPLICATED    %s"
              % ", ".join("%s x%d" % (m, n) for m, n in sorted(duplicated.items())))
    print()
    shortfall = VINTAGES_NEEDED - len(by_month)
    if shortfall > 0:
        print("NOT YET TESTABLE. %d distinct month(s) held; a fundamental "
              "backtest needs about %d." % (len(by_month), VINTAGES_NEEDED))
        print("At one vintage per month that is %d more month(s) of collection."
              % shortfall)
    else:
        print("The panel has reached %d months. A fundamental backtest is now "
              "possible on span, though not necessarily on quality -- read on."
              % len(by_month))
    print()

    # --- universe coverage and field health, vintage by vintage -------------
    universe = {r["Symbol"].strip() for r in csv.DictReader(
        UNIVERSE.open(encoding="utf-8")) if r.get("Symbol")}
    print("-" * 72)
    print("PER VINTAGE")
    print("-" * 72)
    print("%-12s %6s %7s %9s %-28s" % ("as_of", "rows", "univ%", "adapter", "notes"))
    per_vintage, previous_filled = [], None
    for entry in sorted(usable, key=lambda e: e.get("as_of", "")):
        rows = load_rows(entry.get("archived_path", ""))
        if rows is None:
            print("%-12s %6s %7s %9s %s"
                  % (entry.get("as_of", "?"), "-", "-", "-", "FILE MISSING"))
            continue
        codes = {r.get("NSE code", "").strip() for r in rows}
        overlap = len(codes & universe)
        filled = {c: sum(1 for r in rows if r.get(c)) for c in (rows[0] if rows else {})}
        notes = []
        if entry.get("collector") != "collect_pit.py":
            notes.append("hand-run")
        # A column that was populated last month and is empty now is the
        # failure this report exists to surface.
        if previous_filled:
            for column, count in filled.items():
                if column in EMPTY_BY_DESIGN:
                    continue
                before = previous_filled.get(column, 0)
                if before > 0 and count == 0:
                    notes.append("LOST %s" % column)
                elif before and count < before * 0.75:
                    notes.append("%s %d->%d" % (column, before, count))
        print("%-12s %6d %6.0f%% %9s %s"
              % (entry.get("as_of", "?"), len(rows),
                 100.0 * overlap / max(1, len(universe)),
                 (entry.get("adapter_sha256") or "unknown")[:8],
                 "; ".join(notes) if notes else ""))
        per_vintage.append({"as_of": entry.get("as_of"), "rows": len(rows),
                            "universe_overlap": overlap, "notes": notes})
        previous_filled = filled

    # --- adapter changes across the panel ----------------------------------
    adapters = [e.get("adapter_sha256") for e in sorted(
        usable, key=lambda e: e.get("as_of", "")) if e.get("adapter_sha256")]
    distinct = sorted(set(adapters))
    print()
    print("-" * 72)
    print("PROVENANCE")
    print("-" * 72)
    unknown = len(usable) - len(adapters)
    print("Adapter versions across the panel: %d distinct%s"
          % (len(distinct), (", %d vintage(s) recorded none" % unknown) if unknown else ""))
    if len(distinct) > 1:
        print("  A changed adapter between vintages means two months were "
              "normalised by different code. That is not automatically wrong, "
              "but it is a confound and must be stated in any result.")
    raw_files = sorted(RAW.glob("*.json")) if RAW.exists() else []
    print("Raw provider snapshots: %d file(s)%s"
          % (len(raw_files),
             "" if raw_files else "  -- NONE. Normalisation errors would be unrepairable."))
    if retired:
        print("Retired vintages (kept, excluded from the panel):")
        for entry in retired:
            print("   %s  %s" % (entry.get("as_of"),
                                 (entry.get("sha256") or "")[:12]))

    if args.json:
        Path(args.json).write_text(json.dumps({
            "vintages_usable": len(usable), "vintages_retired": len(retired),
            "months_held": len(by_month), "months_missing": missing,
            "months_duplicated": duplicated, "shortfall": max(0, shortfall),
            "adapter_versions": distinct, "raw_snapshots": len(raw_files),
            "per_vintage": per_vintage,
        }, indent=1), encoding="utf-8")
        print("\nwritten to %s" % args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
