"""
===================================================================================
Backtest for the technical half of the Indian Equity Screening Engine
===================================================================================

WHAT THIS TESTS, AND WHAT IT CANNOT

This ranks companies by the engine's TECHNICAL score and measures what happened
next. It is deliberately narrow, and the limits below are not footnotes -- they
decide how much any number here is worth. They are printed with every run.

1. SURVIVORSHIP BIAS. The universe is today's Nifty 100 applied to history. Every
   company that fell out of the index over the period is absent, and those are
   disproportionately the ones that did badly. This flatters every strategy
   measured here, including the benchmarks. Reconstructing point-in-time index
   membership from NSE's change circulars is the fix; until then the numbers are
   an upper bound, not an estimate.

2. THE FUNDAMENTAL HALF IS NOT TESTED. A Screener.in export describes today, so
   applying today's fundamentals -- or today's red flags -- to 2016 would be
   look-ahead of the worst kind: it would "know" which companies turned out to
   have clean books. So this tests the technical score ALONE. It therefore does
   not test the product's actual selection rule, which gates on fundamentals
   first and uses the chart only to order what already qualified. A good decile
   spread here is not evidence that the screener works.

3. NO DIVIDENDS ON EITHER SIDE. Prices are auto-adjusted for splits and
   dividends by the downloader, and ^NSEI is a price index. The equal-weight
   benchmark is built from the same adjusted series, so the comparison is
   like-for-like even though neither is a true total-return figure.

4. COSTS YES, TAXES NO. Brokerage, STT and slippage are modelled as a flat
   per-side cost. Indian short-term capital gains tax is not modelled and at a
   monthly rebalance it is the larger drag of the two. Any figure here is
   before tax.

NO LOOK-AHEAD, BY CONSTRUCTION

A signal computed on rebalance date T uses only sessions up to and including T,
and the resulting trade is executed at the OPEN of the next session. Every
return in this file, for the portfolio and for the decile study alike, is
measured open-to-open on that same schedule. The self-test asserts it.
===================================================================================
"""
import argparse
import bisect
import datetime
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine as E  # noqa: E402  - path is set immediately above


# --- Configuration ---------------------------------------------------------
DEFAULT_TOP_N = 20
# 15 basis points a side: brokerage, STT, exchange charges and slippage, so a
# name fully sold and replaced costs 0.30%.
DEFAULT_COST_BPS_PER_SIDE = 15.0
# Everything from this date is reported separately and was not used to choose
# any parameter. Nothing in this file is fitted, but the split is kept so the
# claim stays checkable if that ever changes.
OUT_OF_SAMPLE_START = "2022-01-01"
DECILE_HORIZONS = (1, 3, 6, 12)  # in rebalances, i.e. months
MONTHS_PER_YEAR = 12


class PriceBook:
    """Per-ticker price lookup with the session index precomputed.

    The backtest asks "what did this ticker do up to date T" tens of thousands
    of times, so each ticker's date list is kept sorted once and searched with
    bisect rather than being filtered on every call.
    """

    def __init__(self, history):
        self.history = history
        self.by_date = {}
        for ticker, series in history.items():
            self.by_date[ticker] = {
                date: index for index, date in enumerate(series["dates"])
            }

    def tickers(self):
        return [t for t in self.history if t != E.BENCHMARK_SYMBOL]

    def index_upto(self, ticker, date):
        """Index of the last session on or before `date`, or None."""
        dates = self.history[ticker]["dates"]
        position = bisect.bisect_right(dates, date) - 1
        return position if position >= 0 else None

    def execution_price(self, ticker, date):
        """The price a trade dated `date` fills at: that session's open.

        Falls back to the close when the file carries no open for the session,
        which older four-column price files never do. The caller counts the
        fallbacks so a run can say how often it had to.
        """
        index = self.by_date.get(ticker, {}).get(date)
        if index is None:
            return None, False
        series = self.history[ticker]
        open_price = series["opens"][index]
        if open_price is not None and open_price > 0:
            return open_price, False
        close = series["closes"][index]
        return (close, True) if close and close > 0 else (None, False)


def market_calendar(history):
    """Every session the benchmark traded, which is the schedule we rebalance on.

    The benchmark is used rather than the union of all tickers because a
    thinly traded name should not invent a market session.
    """
    bench = history.get(E.BENCHMARK_SYMBOL)
    if not bench:
        raise ValueError(
            "price history has no %s benchmark, so there is no market calendar "
            "to rebalance on" % E.BENCHMARK_SYMBOL
        )
    return list(bench["dates"])


def month_end_sessions(calendar):
    """The last session of each month, which is when the screen is re-run."""
    out = []
    for index, date in enumerate(calendar):
        is_last = index + 1 == len(calendar) or calendar[index + 1][:7] != date[:7]
        if is_last:
            out.append(date)
    return out


def score_on(book, ticker, date, bench_by_date):
    """The engine's technical score for one ticker as at `date`, or None.

    Only sessions up to and including `date` are passed in, so the score cannot
    see the future. This calls the engine rather than reimplementing it: when
    the scoring changes, the backtest measures the new scoring.
    """
    end = book.index_upto(ticker, date)
    if end is None:
        return None
    series = book.history[ticker]
    upto = end + 1
    dates = series["dates"][:upto]
    tech = E.compute_technical_indicators(
        series["closes"][:upto],
        [bench_by_date.get(d) for d in dates],
        series["volumes"][:upto],
        source="backtest",
        dates=dates,
        highs=series["highs"][:upto],
        lows=series["lows"][:upto],
    )
    # Unpacked positionally rather than by arity: the scoring function returns
    # (score, breakdown, warnings) today and is being extended with per-block
    # subtotals, and a backtest that crashes when the thing it measures gains a
    # field is a backtest nobody reruns.
    result = E.calculate_technical_score(tech, True)
    return result[0] if isinstance(result, tuple) else result


def rank_on(book, date, bench_by_date):
    """[(ticker, score)] for every ticker scoreable as at `date`, best first.

    Ties break on ticker ascending, the same rule the screener ranks by, so the
    selection is deterministic rather than dependent on dictionary order.
    """
    scored = []
    for ticker in book.tickers():
        score = score_on(book, ticker, date, bench_by_date)
        if score is not None:
            scored.append((ticker, score))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    return scored


def next_session(calendar, date):
    """The session after `date`, which is when a signal dated `date` is traded."""
    position = bisect.bisect_right(calendar, date)
    return calendar[position] if position < len(calendar) else None


def hold_return(book, tickers, entry_date, exit_date):
    """Equal-weighted return of `tickers` bought at one open and sold at another.

    Names without a price on either date are dropped and reported, rather than
    being carried at zero return, which would quietly dilute towards the mean.
    """
    returns = []
    fallbacks = 0
    dropped = 0
    for ticker in tickers:
        entry, entry_fallback = book.execution_price(ticker, entry_date)
        exit_price, exit_fallback = book.execution_price(ticker, exit_date)
        if entry is None or exit_price is None:
            dropped += 1
            continue
        fallbacks += int(entry_fallback) + int(exit_fallback)
        returns.append(exit_price / entry - 1.0)
    if not returns:
        return 0.0, 0, dropped
    return sum(returns) / len(returns), fallbacks, dropped


def run_portfolio(book, calendar, rebalances, bench_by_date, top_n, cost_bps_per_side):
    """Monthly top-N by technical score, equal weighted, costs charged on turnover.

    Returns a list of per-period records. The period return is measured from the
    open after the signal date to the open after the following signal date, so
    the trade is never priced at a level the signal already knew about.
    """
    periods = []
    held = []
    for index in range(len(rebalances) - 1):
        signal_date = rebalances[index]
        entry_date = next_session(calendar, signal_date)
        exit_signal = rebalances[index + 1]
        exit_date = next_session(calendar, exit_signal)
        if entry_date is None or exit_date is None:
            break
        ranked = rank_on(book, signal_date, bench_by_date)
        selected = [ticker for ticker, _score in ranked[:top_n]]
        if not selected:
            continue
        gross, fallbacks, dropped = hold_return(book, selected, entry_date, exit_date)
        # Turnover is the share of the book replaced. Selling that share and
        # buying its replacement pays the per-side cost twice.
        leaving = len(set(held) - set(selected))
        turnover = leaving / float(len(selected))
        cost = 2.0 * turnover * (cost_bps_per_side / 10000.0)
        periods.append({
            "signal_date": signal_date,
            "entry_date": entry_date,
            "exit_date": exit_date,
            "holdings": selected,
            "gross_return": gross,
            "cost": cost,
            "net_return": gross - cost,
            "turnover": turnover,
            "open_fallbacks": fallbacks,
            "dropped": dropped,
            "scored_universe": len(ranked),
        })
        held = selected
    return periods


def run_equal_weight(book, calendar, rebalances):
    """Every covered ticker, equal weighted, rebalanced on the same schedule.

    This is the fairer of the two benchmarks: same universe, same price series,
    same dividend treatment, same execution rule. It answers "did picking help,
    against owning the lot".
    """
    everything = book.tickers()
    periods = []
    for index in range(len(rebalances) - 1):
        entry_date = next_session(calendar, rebalances[index])
        exit_date = next_session(calendar, rebalances[index + 1])
        if entry_date is None or exit_date is None:
            break
        gross, _fallbacks, _dropped = hold_return(book, everything, entry_date, exit_date)
        periods.append({"signal_date": rebalances[index], "net_return": gross})
    return periods


def run_benchmark_index(book, calendar, rebalances):
    """Buy and hold the benchmark index over the same dates."""
    series = book.history.get(E.BENCHMARK_SYMBOL)
    if not series:
        return []
    by_date = {d: series["closes"][i] for i, d in enumerate(series["dates"])}
    periods = []
    for index in range(len(rebalances) - 1):
        entry_date = next_session(calendar, rebalances[index])
        exit_date = next_session(calendar, rebalances[index + 1])
        if entry_date is None or exit_date is None:
            break
        start, end = by_date.get(entry_date), by_date.get(exit_date)
        if not start or not end:
            continue
        periods.append({"signal_date": rebalances[index], "net_return": end / start - 1.0})
    return periods


# --- Performance -----------------------------------------------------------
def equity_curve(periods, key="net_return"):
    value = 1.0
    curve = [1.0]
    for period in periods:
        value *= 1.0 + period[key]
        curve.append(value)
    return curve


def max_drawdown(curve):
    peak = curve[0]
    worst = 0.0
    for value in curve:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def performance(periods, key="net_return"):
    """Headline statistics. Sharpe uses a zero risk-free rate and says so."""
    if not periods:
        return {}
    returns = [p[key] for p in periods]
    curve = equity_curve(periods, key)
    years = len(returns) / float(MONTHS_PER_YEAR)
    total = curve[-1]
    cagr = total ** (1.0 / years) - 1.0 if years > 0 and total > 0 else float("nan")
    mean = sum(returns) / len(returns)
    variance = (sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
                if len(returns) > 1 else 0.0)
    monthly_vol = math.sqrt(variance)
    annual_vol = monthly_vol * math.sqrt(MONTHS_PER_YEAR)
    drawdown = max_drawdown(curve)
    rolling = []
    for start in range(0, max(0, len(returns) - MONTHS_PER_YEAR + 1)):
        window = returns[start:start + MONTHS_PER_YEAR]
        value = 1.0
        for r in window:
            value *= 1.0 + r
        rolling.append(value - 1.0)
    return {
        "months": len(returns),
        "total_return": total - 1.0,
        "cagr": cagr,
        "annual_vol": annual_vol,
        "sharpe_rf0": (mean * MONTHS_PER_YEAR) / annual_vol if annual_vol > 0 else float("nan"),
        "max_drawdown": drawdown,
        "calmar": cagr / abs(drawdown) if drawdown < 0 else float("nan"),
        "hit_rate": sum(1 for r in returns if r > 0) / float(len(returns)),
        "worst_rolling_12m": min(rolling) if rolling else float("nan"),
        "best_rolling_12m": max(rolling) if rolling else float("nan"),
    }


def yearly_returns(periods, key="net_return"):
    by_year = {}
    for period in periods:
        year = period["signal_date"][:4]
        by_year.setdefault(year, 1.0)
        by_year[year] *= 1.0 + period[key]
    return {year: value - 1.0 for year, value in sorted(by_year.items())}


# --- Does the score rank anything? -----------------------------------------
def spearman(pairs):
    """Rank correlation between two series, as plain arithmetic.

    Ties take their average rank, which matters because technical scores are
    coarse -- a handful of discrete point totals across a hundred companies.
    """
    if len(pairs) < 3:
        return None
    def ranks(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        position = 0
        while position < len(order):
            end = position
            while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
                end += 1
            average = (position + end) / 2.0 + 1.0
            for index in range(position, end + 1):
                out[order[index]] = average
            position = end + 1
        return out
    xs = ranks([p[0] for p in pairs])
    ys = ranks([p[1] for p in pairs])
    n = len(pairs)
    mean_x, mean_y = sum(xs) / n, sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    return cov / math.sqrt(var_x * var_y)


def decile_study(book, calendar, rebalances, bench_by_date, horizons=DECILE_HORIZONS):
    """Forward returns by score decile, plus the rank correlation each month.

    If the top decile does not beat the bottom, the score does not rank future
    returns, and no amount of portfolio construction on top of it will help.
    """
    buckets = {h: {d: [] for d in range(10)} for h in horizons}
    ics = {h: [] for h in horizons}
    for index, signal_date in enumerate(rebalances):
        entry_date = next_session(calendar, signal_date)
        if entry_date is None:
            continue
        ranked = rank_on(book, signal_date, bench_by_date)
        if len(ranked) < 10:
            continue
        for horizon in horizons:
            future = index + horizon
            if future >= len(rebalances):
                continue
            exit_date = next_session(calendar, rebalances[future])
            if exit_date is None:
                continue
            observed = []
            for position, (ticker, score) in enumerate(ranked):
                entry, _ = book.execution_price(ticker, entry_date)
                exit_price, _ = book.execution_price(ticker, exit_date)
                if entry is None or exit_price is None:
                    continue
                observed.append((position, score, exit_price / entry - 1.0))
            if len(observed) < 10:
                continue
            count = len(observed)
            for rank_position, (_position, _score, forward) in enumerate(observed):
                decile = min(9, rank_position * 10 // count)
                buckets[horizon][decile].append(forward)
            ic = spearman([(score, forward) for _p, score, forward in observed])
            if ic is not None:
                ics[horizon].append(ic)
    summary = {}
    for horizon in horizons:
        deciles = {}
        for decile in range(10):
            values = buckets[horizon][decile]
            deciles[decile] = {
                "observations": len(values),
                "mean_return": sum(values) / len(values) if values else float("nan"),
            }
        series = ics[horizon]
        mean_ic = sum(series) / len(series) if series else float("nan")
        if len(series) > 1:
            spread = math.sqrt(sum((v - mean_ic) ** 2 for v in series) / (len(series) - 1))
            t_stat = mean_ic / (spread / math.sqrt(len(series))) if spread > 0 else float("nan")
        else:
            t_stat = float("nan")
        summary[horizon] = {"deciles": deciles, "mean_ic": mean_ic,
                            "ic_periods": len(series), "ic_t_stat": t_stat}
    return summary


# --- Reporting -------------------------------------------------------------
LIMITATIONS = [
    "Survivorship bias: today's Nifty 100 applied to history. Companies that "
    "left the index are absent, and they are disproportionately the bad ones. "
    "Every figure here, including the benchmarks, is flattered by this.",
    "The fundamental half is NOT tested. A Screener.in export describes today, "
    "so applying today's fundamentals or red flags to past dates would be "
    "look-ahead. This measures the technical score alone, which is not the "
    "product's selection rule.",
    "No dividends on either side; ^NSEI is a price index and the equal-weight "
    "benchmark uses the same adjusted series, so the comparison is like-for-like.",
    "Costs are modelled, taxes are not. At a monthly rebalance, Indian "
    "short-term capital gains tax is the larger drag. These are pre-tax figures.",
]


def pct(value):
    return "n/a" if value is None or value != value else "%.2f%%" % (value * 100.0)


def format_report(results):
    out = []
    out.append("# Technical-score backtest")
    out.append("")
    out.append("Generated %s" % datetime.datetime.now().isoformat(timespec="seconds"))
    config = results["config"]
    out.append("")
    out.append("Universe %d tickers, %s to %s, monthly rebalance, top %d equal weighted, "
               "%.0f bps per side." % (config["universe"], config["start"], config["end"],
                                       config["top_n"], config["cost_bps_per_side"]))
    out.append("")
    out.append("## Read this before the numbers")
    out.append("")
    for item in LIMITATIONS:
        out.append("- %s" % item)
    out.append("")
    out.append("Variants tried while building this: %d. %s"
               % (config["variants_tried"], config["variants_note"]))
    out.append("")
    for label in ("full", "in_sample", "out_of_sample"):
        block = results["performance"].get(label)
        if not block or not block.get("strategy"):
            continue
        out.append("## %s" % {"full": "Whole period", "in_sample": "In sample (to 2021)",
                              "out_of_sample": "Out of sample (2022 on)"}[label])
        out.append("")
        out.append("| | Top %d | Equal weight | %s |" % (config["top_n"], E.BENCHMARK_SYMBOL))
        out.append("|---|---|---|---|")
        rows = [("Months", "months", "%d"), ("Total return", "total_return", None),
                ("CAGR", "cagr", None), ("Volatility", "annual_vol", None),
                ("Sharpe (rf=0)", "sharpe_rf0", "%.2f"),
                ("Max drawdown", "max_drawdown", None), ("Calmar", "calmar", "%.2f"),
                ("Hit rate", "hit_rate", None),
                ("Worst rolling 12m", "worst_rolling_12m", None)]
        for title, key, fmt in rows:
            cells = []
            for series in ("strategy", "equal_weight", "index"):
                stats = block.get(series) or {}
                value = stats.get(key)
                if value is None:
                    cells.append("n/a")
                elif fmt == "%d":
                    cells.append("%d" % value)
                elif fmt:
                    cells.append("n/a" if value != value else fmt % value)
                else:
                    cells.append(pct(value))
            out.append("| %s | %s |" % (title, " | ".join(cells)))
        out.append("")
    out.append("## Did the score rank anything?")
    out.append("")
    out.append("If the top decile does not beat the bottom, the score does not order "
               "future returns and no portfolio construction on top of it will help.")
    out.append("")
    for horizon, block in sorted(results["deciles"].items()):
        out.append("### %d-month forward returns" % horizon)
        out.append("")
        out.append("| Decile | Mean forward return | Observations |")
        out.append("|---|---|---|")
        for decile in range(10):
            stats = block["deciles"][decile]
            out.append("| %d%s | %s | %d |" % (
                decile + 1,
                " (best scores)" if decile == 0 else (" (worst)" if decile == 9 else ""),
                pct(stats["mean_return"]), stats["observations"]))
        top = block["deciles"][0]["mean_return"]
        bottom = block["deciles"][9]["mean_return"]
        spread = top - bottom if top == top and bottom == bottom else float("nan")
        out.append("")
        out.append("Top minus bottom: **%s**. Mean rank correlation %.4f over %d months "
                   "(t %.2f)." % (pct(spread), block["mean_ic"], block["ic_periods"],
                                  block["ic_t_stat"]))
        out.append("")
    out.append("## Execution quality")
    out.append("")
    quality = results["quality"]
    out.append("- Trades priced at the next session's open: %d of %d fills (%s fell back "
               "to that session's close because the file carried no open)."
               % (quality["open_fills"], quality["total_fills"], quality["fallbacks"]))
    out.append("- Holdings dropped for want of a price on a rebalance date: %d."
               % quality["dropped"])
    out.append("- Median scoreable universe at a rebalance: %d of %d."
               % (quality["median_scored"], config["universe"]))
    out.append("- Average annual turnover: %s." % pct(results["turnover"]))
    return "\n".join(out) + "\n"


# --- Orchestration ---------------------------------------------------------
def backtest(history, top_n=DEFAULT_TOP_N, cost_bps_per_side=DEFAULT_COST_BPS_PER_SIDE,
             variants_tried=1, variants_note=""):
    book = PriceBook(history)
    calendar = market_calendar(history)
    rebalances = month_end_sessions(calendar)
    bench = history[E.BENCHMARK_SYMBOL]
    bench_by_date = dict(zip(bench["dates"], bench["closes"]))

    periods = run_portfolio(book, calendar, rebalances, bench_by_date, top_n, cost_bps_per_side)
    equal = run_equal_weight(book, calendar, rebalances)
    index = run_benchmark_index(book, calendar, rebalances)
    deciles = decile_study(book, calendar, rebalances, bench_by_date)

    def split(records):
        inside = [r for r in records if r["signal_date"] < OUT_OF_SAMPLE_START]
        outside = [r for r in records if r["signal_date"] >= OUT_OF_SAMPLE_START]
        return inside, outside

    blocks = {}
    for label, chooser in (("full", lambda rs: rs),
                           ("in_sample", lambda rs: split(rs)[0]),
                           ("out_of_sample", lambda rs: split(rs)[1])):
        blocks[label] = {
            "strategy": performance(chooser(periods)),
            "equal_weight": performance(chooser(equal)),
            "index": performance(chooser(index)),
        }

    total_fills = sum(len(p["holdings"]) * 2 for p in periods)
    scored = sorted(p["scored_universe"] for p in periods)
    turnovers = [p["turnover"] for p in periods]
    return {
        "config": {
            "universe": len(book.tickers()),
            "start": periods[0]["entry_date"] if periods else "n/a",
            "end": periods[-1]["exit_date"] if periods else "n/a",
            "top_n": top_n,
            "cost_bps_per_side": cost_bps_per_side,
            "variants_tried": variants_tried,
            "variants_note": variants_note,
        },
        "performance": blocks,
        "deciles": deciles,
        "periods": periods,
        "yearly": {
            "strategy": yearly_returns(periods),
            "equal_weight": yearly_returns(equal),
            "index": yearly_returns(index),
        },
        "turnover": (sum(turnovers) / len(turnovers) * MONTHS_PER_YEAR) if turnovers else 0.0,
        "quality": {
            "total_fills": total_fills,
            "fallbacks": sum(p["open_fallbacks"] for p in periods),
            "open_fills": total_fills - sum(p["open_fallbacks"] for p in periods),
            "dropped": sum(p["dropped"] for p in periods),
            "median_scored": scored[len(scored) // 2] if scored else 0,
        },
    }


class BacktestTests(unittest.TestCase):
    """Offline checks on the mechanics. No network, no downloaded data."""

    @staticmethod
    def _series(dates, values):
        return {"dates": list(dates), "closes": list(values),
                "opens": list(values), "highs": list(values), "lows": list(values),
                "volumes": [1000.0] * len(values)}

    @staticmethod
    def _business_days(count, start="2024-01-01"):
        day = datetime.date.fromisoformat(start)
        out = []
        while len(out) < count:
            if day.weekday() < 5:
                out.append(day.isoformat())
            day += datetime.timedelta(days=1)
        return out

    def _history(self):
        # Long enough that the engine actually scores it. The 52-week high alone
        # needs 252 sessions, and a shorter fixture scores nothing at all --
        # which silently turns every portfolio assertion below into a test of an
        # empty list rather than of the portfolio.
        dates = self._business_days(300)
        rising = [100.0 + i for i in range(len(dates))]
        falling = [400.0 - i * 0.5 for i in range(len(dates))]
        benchmark = [1000.0 + i * 0.1 for i in range(len(dates))]
        return dates, {
            "UP": self._series(dates, rising),
            "DOWN": self._series(dates, falling),
            E.BENCHMARK_SYMBOL: self._series(dates, benchmark),
        }

    def test_month_end_sessions_are_the_last_of_each_month(self):
        # Asserted as a property rather than as pinned dates, so changing the
        # fixture's length cannot quietly invalidate it.
        dates, _ = self._history()
        ends = month_end_sessions(dates)
        last_of_month = {}
        for date in dates:
            last_of_month[date[:7]] = date
        self.assertEqual(sorted(ends), sorted(last_of_month.values()))
        self.assertEqual(len(ends), len(last_of_month))

    def test_execution_uses_the_next_session_not_the_signal_session(self):
        # Asserted against the calendar rather than pinned dates: this test used
        # to hard-code a pair from a shorter fixture, and changing the fixture
        # silently falsified it.
        dates, _history = self._history()
        for index in (0, 17, 200, len(dates) - 2):
            self.assertEqual(next_session(dates, dates[index]), dates[index + 1])
            self.assertNotEqual(next_session(dates, dates[index]), dates[index])
        # A signal on the last date has no session to trade in, so it is dropped
        # rather than filled at a price the signal already saw.
        self.assertIsNone(next_session(dates, dates[-1]))

    def test_a_score_cannot_see_past_its_date(self):
        dates, history = self._history()
        book = PriceBook(history)
        bench = dict(zip(dates, history[E.BENCHMARK_SYMBOL]["closes"]))
        # Truncating the future away must not change the score for a past date.
        cut = 280
        truncated = {t: {k: v[:cut + 1] for k, v in s.items()} for t, s in history.items()}
        later = score_on(book, "UP", "2024-04-01", bench)
        earlier = score_on(PriceBook(truncated), "UP", "2024-04-01", bench)
        self.assertEqual(later, earlier)

    def test_costs_are_charged_on_turnover_only(self):
        dates, history = self._history()
        book = PriceBook(history)
        bench = dict(zip(dates, history[E.BENCHMARK_SYMBOL]["closes"]))
        periods = run_portfolio(book, dates, month_end_sessions(dates), bench, 1, 15.0)
        self.assertTrue(periods)
        for period in periods:
            expected = 2.0 * period["turnover"] * 0.0015
            self.assertAlmostEqual(period["cost"], expected, places=12)
            self.assertAlmostEqual(period["net_return"],
                                   period["gross_return"] - period["cost"], places=12)

    def test_performance_arithmetic_on_a_known_series(self):
        periods = [{"net_return": 0.10, "signal_date": "2024-01-31"},
                   {"net_return": -0.10, "signal_date": "2024-02-29"}]
        stats = performance(periods)
        self.assertAlmostEqual(stats["total_return"], 1.10 * 0.90 - 1.0, places=12)
        self.assertAlmostEqual(stats["hit_rate"], 0.5, places=12)
        self.assertLess(stats["max_drawdown"], 0.0)

    def test_spearman_detects_perfect_and_inverse_order(self):
        self.assertAlmostEqual(spearman([(1, 1), (2, 2), (3, 3), (4, 4)]), 1.0, places=12)
        self.assertAlmostEqual(spearman([(1, 4), (2, 3), (3, 2), (4, 1)]), -1.0, places=12)
        self.assertIsNone(spearman([(1, 1), (1, 1), (1, 1)]))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="backtest.py",
        description="Backtest the technical half of the screening engine.")
    parser.add_argument("--prices", metavar="CSV",
                        help="price-history CSV (Date,Ticker,Open,High,Low,Close,Volume)")
    parser.add_argument("--top-n", type=int, default=DEFAULT_TOP_N)
    parser.add_argument("--cost-bps", type=float, default=DEFAULT_COST_BPS_PER_SIDE,
                        help="cost per side in basis points (default 15, so 0.30%% round trip)")
    parser.add_argument("--out-dir", metavar="DIR", help="write report.md and results.json here")
    parser.add_argument("--variants-tried", type=int, default=1,
                        help="how many parameter variants were run in total, reported verbatim")
    parser.add_argument("--variants-note", default="No parameter was fitted to the data.")
    parser.add_argument("--self-test", action="store_true", help="run the offline checks and exit")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.self_test:
        suite = unittest.TestLoader().loadTestsFromTestCase(BacktestTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1

    if not args.prices:
        parser.error("--prices is required unless --self-test is given")
    history, skipped = E.parse_price_history_csv(Path(args.prices).read_text(encoding="utf-8"))
    print("Loaded %d tickers (%d rows skipped)." % (len(history), skipped))
    results = backtest(history, args.top_n, args.cost_bps,
                       args.variants_tried, args.variants_note)
    report = format_report(results)
    print(report)
    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(report, encoding="utf-8")
        serialisable = {k: v for k, v in results.items() if k != "periods"}
        serialisable["periods"] = [
            {k: v for k, v in p.items() if k != "holdings"} for p in results["periods"]
        ]
        (out / "results.json").write_text(json.dumps(serialisable, indent=2, default=str),
                                          encoding="utf-8")
        print("Wrote %s and %s" % (out / "report.md", out / "results.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
