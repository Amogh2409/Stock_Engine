#!/usr/bin/env python3
"""How much survivorship bias can actually be removed, and what remains.

Compares the official point-in-time Nifty 100 against the static current list
that every study so far has used, and reports how much of each historical index
the expanded price panel can actually price. Produces no research result and
reads no forward return.

Usage:
    scripts/venv-python.sh scripts/survivorship_audit.py
"""
from __future__ import annotations

import csv
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
PIT = ROOT / "data-store" / "universe" / "pit_nifty100.csv"
PANEL = ROOT / "data-store" / "market_data" / "pit-union" / "price_history_union.csv"
TODAY = ROOT / "data" / "nifty100_source.csv"
TRANSITIONS = ROOT / "data" / "symbol_transitions.csv"
MANIFEST = ROOT / "data-store" / "universe" / "manifest.jsonl"


def main():
    rows = list(csv.DictReader(PIT.open(encoding="utf-8")))
    by_date = collections.defaultdict(set)
    for row in rows:
        by_date[row["report_date"]].add(row["symbol"])
    dates = sorted(by_date)
    union = {r["symbol"] for r in rows}
    today = {r["Symbol"].strip() for r in csv.DictReader(TODAY.open(encoding="utf-8"))
             if r.get("Symbol")}
    panel = {r["Ticker"] for r in csv.DictReader(PANEL.open(encoding="utf-8"))}
    register = {r["old_symbol"]: r for r in csv.DictReader(TRANSITIONS.open(encoding="utf-8"))}
    manifest = [json.loads(l) for l in MANIFEST.read_text(encoding="utf-8").splitlines()]
    accepted = [m for m in manifest if m["accepted"]]

    out = []
    add = out.append
    add("=" * 68)
    add("HISTORICAL PIT UNIVERSE COVERAGE")
    add("=" * 68)
    add("")
    add("Official monthly reports retrieved   %d" % len(manifest))
    add("Reports parsed and accepted          %d" % len(accepted))
    add("Reports rejected                     %d" % (len(manifest) - len(accepted)))
    add("Coverage window                      %s .. %s" % (dates[0], dates[-1]))
    spread = collections.Counter(len(v) for v in by_date.values())
    add("Constituents per report              %s"
        % ", ".join("%d x%d" % (k, v) for k, v in sorted(spread.items())))
    add("")
    add("Unique historical constituents       %d" % len(union))
    priced = union & panel
    add("  priceable in the expanded panel    %d" % len(priced))
    add("  NOT priceable                      %d" % len(union - panel))
    add("")
    kinds = collections.Counter(register[s]["event_type"] for s in union - panel
                                if s in register)
    for kind, count in sorted(kinds.items()):
        add("     %-24s %d" % (kind, count))
    unregistered = sorted((union - panel) - set(register))
    if unregistered:
        add("     %-24s %d  %s" % ("UNREGISTERED", len(unregistered),
                                   ", ".join(unregistered[:6])))
    stitched = [s for s, r in register.items() if r["stitch_allowed"] == "yes"]
    add("")
    add("  price series stitched across a transition: %d  %s"
        % (len(stitched), "(none -- no fabricated continuity)" if not stitched else stitched))
    add("")

    add("-" * 68)
    add("PRICE COVERAGE OF EACH HISTORICAL INDEX")
    add("-" * 68)
    buckets = collections.Counter()
    per_year = collections.defaultdict(list)
    for date in dates:
        members = by_date[date]
        share = len(members & panel) / len(members)
        per_year[date[:4]].append(share)
        if share == 1.0:
            buckets["100%"] += 1
        elif share >= 0.99:
            buckets["99-99.9%"] += 1
        elif share >= 0.95:
            buckets["95-98.9%"] += 1
        elif share >= 0.90:
            buckets["90-94.9%"] += 1
        else:
            buckets["<90%"] += 1
    for label in ("100%", "99-99.9%", "95-98.9%", "90-94.9%", "<90%"):
        add("  reports with %-10s price coverage : %3d" % (label, buckets[label]))
    add("")
    add("  %-6s %-8s %-9s %-9s %s" % ("year", "reports", "min cov", "mean cov", "max cov"))
    for year in sorted(per_year):
        shares = per_year[year]
        add("  %-6s %-8d %-9.1f%% %-9.1f%% %.1f%%"
            % (year, len(shares), 100 * min(shares),
               100 * sum(shares) / len(shares), 100 * max(shares)))
    add("")

    add("-" * 68)
    add("SURVIVORSHIP BIAS: PIT INDEX vs TODAY'S STATIC LIST")
    add("-" * 68)
    add("  %-12s %-8s %-10s %-12s %s"
        % ("report", "official", "overlap", "hist-only", "today-only injected"))
    sampled = [dates[0]] + dates[len(dates)//4::len(dates)//4][:3] + [dates[-1]]
    for date in sorted(set(sampled)):
        members = by_date[date]
        add("  %-12s %-8d %-10d %-12d %d"
            % (date, len(members), len(members & today),
               len(members - today), len(today - members)))
    add("")
    overlaps = [len(by_date[d] & today) / len(by_date[d]) for d in dates]
    add("  overlap with today's list: min %.1f%%  mean %.1f%%  max %.1f%%"
        % (100 * min(overlaps), 100 * sum(overlaps) / len(overlaps), 100 * max(overlaps)))
    add("")
    add("  Total unique PIT constituents                    %d" % len(union))
    add("  Historical members absent from today's list      %d" % len(union - today))
    add("  Today's names never in the covered window        %d" % len(today - union))
    add("")
    add("  A static backtest over this window ranked %d names." % len(today))
    add("  The official index contained %d distinct securities." % len(union))
    add("  %d of them (%.0f%%) were invisible to every study run so far."
        % (len(union - today), 100 * len(union - today) / len(union)))
    report = "\n".join(out)
    (ROOT / "data-store" / "universe" / "survivorship_audit.txt").write_text(
        report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
