#!/usr/bin/env python3
"""Record this month's selections, before the month they apply to.

WHY THIS EXISTS.

There are exactly two sources of clean data in this project. The reserved window
is one: 44 periods, finite, spent the moment it is read, and currently worth a
56%-power test. Forward time is the other, and it accrues one period a month for
nothing. `knowledge/rulebook.md` names forward paper-trading as one of only two
legitimate routes past the feedback objection, and until now nobody had set it up.

WHAT MAKES IT EVIDENCE RATHER THAN A DIARY.

  1. Written BEFORE the month it applies to, and committed to git, so the
     timestamp is verifiable by someone who does not trust the author.
  2. Never revised. A correction is a NEW dated file, not an edit. This script
     refuses to overwrite.
  3. Stamped with the engine's scoring hash and the git commit, so a later reader
     knows which engine produced the entry -- the scoring has already changed
     once during this project and will change again.
  4. NO RETURNS ARE COMPUTED HERE. Scoring an entry is a separate act at a later
     date. Conflating the two is how a forward log quietly becomes a backtest:
     if the same run that picks the names also reports how they did, nothing
     stops the picking from being adjusted until the reporting looks better.

WHAT IT DOES NOT DO.

It does not touch the reserved window in the sense the holdout rules mean. It
reads prices up to today to compute a score, which is what the engine is for, and
it measures no return and makes no comparison. The returns that will eventually
score these entries have not happened yet.

Usage:
    scripts/venv-python.sh scripts/forward_log.py --prices <csv>
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
sys.path.insert(0, str(ROOT / "scripts"))

import backtest as B  # noqa: E402 - path set immediately above
import engine as E  # noqa: E402
from check_doc_figures import scoring_digest  # noqa: E402

LOG_DIR = ROOT / "knowledge/forward-log"


def git(*args):
    try:
        out = subprocess.run(["git", "-C", str(ROOT)] + list(args),
                             capture_output=True, text=True, check=False)
        return out.stdout.strip() if out.returncode == 0 else "unavailable"
    except OSError:
        return "unavailable"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Record this month's selections before the month they apply to.")
    parser.add_argument("--prices", required=True, metavar="CSV")
    parser.add_argument("--top-n", type=int, default=B.DEFAULT_TOP_N)
    parser.add_argument("--out-dir", default=str(LOG_DIR))
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    history, skipped = E.parse_price_history_csv(
        pathlib.Path(args.prices).read_text(encoding="utf-8"))
    book = B.PriceBook(history)
    calendar = B.market_calendar(history)
    if not calendar:
        raise SystemExit("no sessions in %s" % args.prices)
    signal_date = calendar[-1]
    bench_series = history[E.BENCHMARK_SYMBOL]
    bench = dict(zip(bench_series["dates"], bench_series["closes"]))
    sectors = B.load_sector_map()

    directory = pathlib.Path(args.out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ("%s.json" % signal_date)
    if path.exists():
        # Never revised. A correction is a new dated file with its own reason.
        raise SystemExit(
            "%s already exists. A forward-log entry is never edited -- if it is "
            "wrong, write a new dated entry saying so and why. Editing this file "
            "would destroy the only property that makes it evidence." % path)

    shipped = B.rank_on(book, signal_date, bench)
    reversal = B.rank_on(book, signal_date, bench, block="momentum",
                         continuous=True, neutral=True, sectors=sectors)
    if not shipped:
        raise SystemExit("nothing scoreable on %s" % signal_date)

    digest, covered = scoring_digest()
    entry = {
        "signal_date": signal_date,
        "written_at": datetime.datetime.now(datetime.timezone.utc)
                              .replace(microsecond=0).isoformat(),
        "applies_from": "the session after %s" % signal_date,
        "engine": {
            "scoring_hash": digest,
            "hash_covers": covered,
            "git_commit": git("rev-parse", "HEAD"),
            "git_describes": git("log", "-1", "--format=%s"),
            "relative_strength_skip_sessions": E.RELATIVE_STRENGTH_SKIP_SESSIONS,
        },
        "universe": {"tickers_priced": len(book.tickers()),
                     "scoreable": len(shipped), "rows_skipped": skipped},
        "shipped_top_n": [{"rank": i + 1, "ticker": t, "score": s}
                          for i, (t, s) in enumerate(shipped[:args.top_n])],
        # The pre-registered hypothesis is that momentum is ANTI-predictive at one
        # month, so the selection it implies is the LOWEST-scoring names.
        "reversal_selection": [{"rank": i + 1, "ticker": t, "momentum_score": s}
                               for i, (t, s) in enumerate(list(reversed(reversal))[:args.top_n])],
        "returns": None,
        "note": ("No returns are computed at write time, deliberately. Scoring "
                 "this entry is a separate act at a later date."),
    }
    body = json.dumps(entry, indent=2, sort_keys=True) + "\n"
    entry["content_sha256"] = hashlib.sha256(body.encode("utf-8")).hexdigest()
    path.write_text(json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("wrote %s" % path)
    print("  signal date   %s" % signal_date)
    print("  scoring hash  %s" % digest[:16])
    print("  commit        %s" % entry["engine"]["git_commit"][:12])
    print("  scoreable     %d of %d priced" % (len(shipped), len(book.tickers())))
    print("  shipped top %d: %s" % (args.top_n,
                                    ", ".join(r["ticker"] for r in entry["shipped_top_n"][:8]) + " ..."))
    print("  reversal   %d: %s" % (args.top_n,
                                   ", ".join(r["ticker"] for r in entry["reversal_selection"][:8]) + " ..."))
    print()
    print("COMMIT THIS FILE. The git timestamp is what makes the entry evidence")
    print("rather than an assertion, and it must land before the month it covers.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
