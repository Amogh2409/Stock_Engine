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
PIT = ROOT / "data-store" / "universe" / "pit_nifty100_extended.csv"
PANEL = ROOT / "data-store" / "market_data" / "pit-union" / "price_history_union_v2.csv"
TODAY = ROOT / "data" / "nifty100_source.csv"
TRANSITIONS = ROOT / "data" / "symbol_transitions.csv"
MANIFEST = ROOT / "data-store" / "universe" / "manifest.jsonl"


def weight_and_bias():
    """Coverage by INDEX WEIGHT, and whether what is missing is systematic.

    Count coverage and weight coverage answer different questions: missing ten
    tail constituents is not the same failure as missing ten that carry a
    quarter of the index. Both are reported; neither excuses the other.

    The bias check uses ONLY information available in the official reports at
    the time -- weight, index market cap, industry, year. No forward return is
    read, because the question is whether the missing group is systematically
    different, not whether it performed differently.
    """
    rows = list(csv.DictReader(PIT.open(encoding="utf-8")))
    panel = {r["Ticker"] for r in csv.DictReader(PANEL.open(encoding="utf-8"))}
    by_date = collections.defaultdict(list)
    for row in rows:
        by_date[row["report_date"]].append(row)

    out = ["", "-" * 68, "COUNT vs INDEX-WEIGHT COVERAGE", "-" * 68]
    counts, weights = [], []
    per_year = collections.defaultdict(lambda: ([], []))
    for date in sorted(by_date):
        members = by_date[date]
        total_w = sum(float(r["weight_pct"] or 0) for r in members)
        have_w = sum(float(r["weight_pct"] or 0) for r in members if r["symbol"] in panel)
        c = sum(1 for r in members if r["symbol"] in panel) / len(members)
        w = (have_w / total_w) if total_w else float("nan")
        counts.append(c); weights.append(w)
        per_year[date[:4]][0].append(c); per_year[date[:4]][1].append(w)

    def pct(v):
        return 100 * v

    def quantile(values, q):
        ordered = sorted(values)
        return ordered[min(len(ordered) - 1, int(q * len(ordered)))]

    out.append("  mean constituent-count coverage   %.1f%%" % pct(sum(counts) / len(counts)))
    out.append("  mean INDEX-WEIGHT coverage        %.1f%%" % pct(sum(weights) / len(weights)))
    out.append("  median count / weight             %.1f%% / %.1f%%"
               % (pct(quantile(counts, 0.5)), pct(quantile(weights, 0.5))))
    out.append("  p5 count / weight                 %.1f%% / %.1f%%"
               % (pct(quantile(counts, 0.05)), pct(quantile(weights, 0.05))))
    out.append("  minimum count / weight            %.1f%% / %.1f%%"
               % (pct(min(counts)), pct(min(weights))))
    out.append("")
    for label, threshold in (("100%", 1.0), (">=99%", 0.99), (">=98%", 0.98),
                             (">=95%", 0.95), (">=90%", 0.90)):
        out.append("  months with %-6s count / weight : %3d / %3d"
                   % (label, sum(1 for c in counts if c >= threshold - 1e-9),
                      sum(1 for w in weights if w >= threshold - 1e-9)))
    out.append("")
    out.append("  %-6s %-10s %-10s" % ("year", "count cov", "weight cov"))
    for year in sorted(per_year):
        c, w = per_year[year]
        out.append("  %-6s %-10.1f %-10.1f" % (year, 100 * sum(c) / len(c), 100 * sum(w) / len(w)))

    out += ["", "-" * 68, "MISSINGNESS BIAS  (PIT information only)", "-" * 68]
    seen_w, seen_m, seen_i, seen_y = {}, {}, {}, {}
    for row in rows:
        symbol = row["symbol"]
        seen_w.setdefault(symbol, []).append(float(row["weight_pct"] or 0))
        seen_m.setdefault(symbol, []).append(float(row["index_mcap_cr"] or 0))
        seen_i.setdefault(symbol, row["industry"])
        seen_y.setdefault(symbol, []).append(row["report_date"][:4])
    have = [s for s in seen_w if s in panel]
    lack = [s for s in seen_w if s not in panel]

    def mean(xs):
        return sum(xs) / len(xs) if xs else float("nan")

    out.append("  securities covered / missing      %d / %d" % (len(have), len(lack)))
    out.append("  mean index weight   covered %.3f%%   missing %.3f%%"
               % (mean([mean(seen_w[s]) for s in have]),
                  mean([mean(seen_w[s]) for s in lack])))
    out.append("  median index weight covered %.3f%%   missing %.3f%%"
               % (quantile([mean(seen_w[s]) for s in have], 0.5),
                  quantile([mean(seen_w[s]) for s in lack], 0.5)))
    out.append("  mean index mcap Cr  covered %,.0f   missing %,.0f"
               .replace(",", "") % (mean([mean(seen_m[s]) for s in have]),
                                    mean([mean(seen_m[s]) for s in lack])))
    out.append("  mean months in index covered %.1f   missing %.1f"
               % (mean([len(seen_w[s]) for s in have]),
                  mean([len(seen_w[s]) for s in lack])))
    out.append("  last year present   covered %s   missing %s"
               % (collections.Counter(max(seen_y[s]) for s in have).most_common(1)[0][0],
                  collections.Counter(max(seen_y[s]) for s in lack).most_common(1)[0][0]))
    out.append("")
    out.append("  missing securities by last year in the index:")
    for year, n in sorted(collections.Counter(max(seen_y[s]) for s in lack).items()):
        out.append("     %s  %d" % (year, n))
    out.append("")
    out.append("  missing securities by industry:")
    for industry, n in collections.Counter(seen_i[s] for s in lack).most_common(8):
        out.append("     %-34s %d" % (industry[:34], n))
    return "\n".join(out)


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
    out.append(weight_and_bias())
    report = "\n".join(out)
    (ROOT / "data-store" / "universe" / "survivorship_audit.txt").write_text(
        report + "\n", encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
