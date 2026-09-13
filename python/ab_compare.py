"""A/B the technical score across two engine revisions, on identical data.

HARNESS, NOT ENGINE CODE. analyse() rebinds `backtest.E` to the revision under
test, swapping the engine out from under the module rather than passing it in.
That is deliberate and it is the one thing a reader must be told rather than
discover: backtest.py binds its engine at import because in the repository it
sits beside exactly one engine.py, and only this comparison needs two at once.

THE TWO REVISIONS DO NOT SCORE THE SAME UNIVERSE. A minimum-session rule
decides whether a company can be scored at all, so changing it changes which
companies are rankable, not only how they rank. Comparing 9939ba7 against
f62a110, the newer revision ranked a median of 90 companies against 91, and 80
against 82 across the first two years, differing in 95 of 141 rebalances and by
as many as 80 in one month. Any difference in the numbers below is therefore
part scoring and part universe, and reporting it as like-for-like would be the
same inflation as quoting an overlapping-window t-statistic.

Usage:
    ab_compare.py --engine OLD=/path/to/cleanroom_a/python \
                  --engine NEW=/path/to/cleanroom_b/python \
                  --prices /path/to/price_history.csv

Both revisions see the same price file, the same calendar, the same execution
rule and the same costs, so any difference is the scoring and nothing else.

The headline is the NON-OVERLAPPING rank correlation. The overlapping column is
printed beside it only to make the inflation visible: a 6-month forward return
sampled monthly reuses five sixths of its window, which turned a t of 0.12 into
a t of 2.14 on the first run of this project.
"""
import argparse
import importlib.util
import math
import sys
from pathlib import Path


def load_engine(directory, name):
    """Import engine.py from a directory under its own module name.

    Two revisions coexist in one process because the engine guarantees that
    importing it has no side effects -- no Drive mount, no network, no pipeline.
    """
    path = Path(directory) / "engine.py"
    if not path.exists():
        raise SystemExit("no engine.py in %s" % directory)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summarise(values, backtest=None, hac_lag=0):
    """(mean, iid t, n, HAC t) for a series of rank correlations.

    The i.i.d. t is retained and is CORRECT for the non-overlapping series. It
    is wrong for the overlapping one, where consecutive windows share h-1
    periods and the independence it assumes does not hold -- the same defect
    backtest.py carried until HAC was added there. Fixing one tool and leaving
    the other is how this repository ended up with a claim that was true of
    ab_compare.py and false of backtest.py; see the rulebook.

    backtest is passed in rather than imported, because this module imports it
    inside main() and a module-level reference here would not resolve.
    """
    n = len(values)
    if n < 2:
        return float("nan"), float("nan"), n, float("nan")
    mean = sum(values) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))
    t = mean / (sd / math.sqrt(n)) if sd > 0 else float("nan")
    hac_t = float("nan")
    if backtest is not None:
        hac_se = backtest._newey_west_se(values, hac_lag)
        if hac_se == hac_se and hac_se > 0:
            hac_t = mean / hac_se
    return mean, t, n, hac_t


def analyse(engine, backtest, history):
    """Portfolio and ranking statistics for one engine revision."""
    backtest.E = engine  # the harness swaps the engine under test, deliberately
    book = backtest.PriceBook(history)
    calendar = backtest.market_calendar(history)
    rebalances = backtest.month_end_sessions(calendar)
    bench_series = history[engine.BENCHMARK_SYMBOL]
    bench = dict(zip(bench_series["dates"], bench_series["closes"]))

    rankings = {d: backtest.rank_on(book, d, bench) for d in rebalances}

    def ic_series(horizon, stride):
        out = []
        for i in range(0, len(rebalances) - horizon, stride):
            entry = backtest.next_session(calendar, rebalances[i])
            exit_ = backtest.next_session(calendar, rebalances[i + horizon])
            if entry is None or exit_ is None:
                continue
            pairs = []
            for ticker, score in rankings[rebalances[i]]:
                start, _ = book.execution_price(ticker, entry)
                end, _ = book.execution_price(ticker, exit_)
                if start and end:
                    pairs.append((score, end / start - 1.0))
            ic = backtest.spearman(pairs)
            if ic is not None:
                out.append(ic)
        return out

    results = backtest.backtest(history, variants_tried=1,
                               variants_note="A/B comparison, no parameter fitted.")
    return {
        "performance": results["performance"],
        "turnover": results["turnover"],
        # Reported so the banner can state the span it actually measured. This
        # function builds its rebalances through month_end_sessions(), which
        # truncates at HOLDOUT_START by default, so the span is NOT the span of
        # the price file handed in -- and a header that implies otherwise is how
        # a reader takes a partial answer for a whole one.
        "span": (rebalances[0], rebalances[-1], len(rebalances)) if rebalances else None,
        # Overlapping windows correlate out to lag h-1, which is the Newey-West
        # bandwidth; the non-overlapping series shares no days, so lag 0 there.
        "ics": {h: {"overlapping": summarise(ic_series(h, 1), backtest, h - 1),
                    "non_overlapping": summarise(ic_series(h, h), backtest, 0)}
                for h in (1, 3, 6, 12)},
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", action="append", required=True,
                        metavar="LABEL=DIR", help="repeatable: a label and a directory holding engine.py")
    parser.add_argument("--prices", required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import backtest  # noqa: E402 - path set immediately above

    labelled = []
    for entry in args.engine:
        label, _, directory = entry.partition("=")
        labelled.append((label, load_engine(directory, "engine_%s" % label.lower())))

    text = Path(args.prices).read_text(encoding="utf-8")
    outcomes = {}
    for label, engine in labelled:
        history, _skipped = engine.parse_price_history_csv(text)
        print("Analysing %s ..." % label, flush=True)
        outcomes[label] = analyse(engine, backtest, history)

    labels = [label for label, _ in labelled]
    # Every t-statistic computed in this run counts towards the adjustment: four
    # horizons per revision. Judging one in isolation is how noise gets promoted.
    total_tests = 4 * len(labels)
    print()
    print("RANK CORRELATION WITH FORWARD RETURNS")
    # State the measured span rather than letting the price file's name imply it.
    # month_end_sessions() truncates at HOLDOUT_START, so this is routinely
    # shorter than the file handed in, and silently so.
    span = next((o["span"] for o in outcomes.values() if o.get("span")), None)
    if span:
        print("Measured over %s to %s (%d rebalances). Data from %s onward is RESERVED"
              % (span[0], span[1], span[2], backtest.HOLDOUT_START))
        print("and excluded by default; see knowledge/holdout.md.")
    print("Overlapping windows are not a defect in themselves -- applying an i.i.d.")
    print("standard error to them is. The overlapping column carries a Newey-West SE")
    print("at lag h-1, so it keeps every window instead of discarding most of them.")
    print("p-values are two-sided from Student's t, adjusted for every test in this run.")
    print("The revisions do not score the same universe; see the module docstring.")
    print()
    header = "%-8s" % "horizon"
    for label in labels:
        header += " | %-28s" % ("%s  non-overlap (overlap)" % label)
    print(header)
    for horizon in (1, 3, 6, 12):
        row = "%-8s" % ("%dm" % horizon)
        for label in labels:
            non = outcomes[label]["ics"][horizon]["non_overlapping"]
            over = outcomes[label]["ics"][horizon]["overlapping"]
            mean, t_stat, n, _hac_t = non
            adjusted = backtest.bonferroni(backtest.two_sided_p(t_stat, n - 1), total_tests)
            # over is (mean, iid t, n, HAC t). The HAC figure is the one to read
            # for the overlapping series; the iid t beside it is shown only so
            # the inflation is visible rather than asserted.
            row += " | IC %+.4f t %+5.2f p* %.3f (ov HAC %+5.2f, iid %+5.2f)" % (
                mean, t_stat, adjusted, over[3], over[1])
        print(row)
    print()
    print("PORTFOLIO, top 20 monthly, versus equal-weighting the same universe")
    print()
    for period in ("full", "out_of_sample"):
        print("  %s" % period)
        for label in labels:
            block = outcomes[label]["performance"][period]
            strategy = block["strategy"].get("cagr", float("nan")) * 100
            equal = block["equal_weight"].get("cagr", float("nan")) * 100
            print("    %-6s strategy %6.2f%%   equal-weight %6.2f%%   difference %+6.2f%%"
                  % (label, strategy, equal, strategy - equal))
    print()
    for label in labels:
        print("  %-6s annual turnover %.0f%%" % (label, outcomes[label]["turnover"] * 100))
    return 0


if __name__ == "__main__":
    sys.exit(main())
