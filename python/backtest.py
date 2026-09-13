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
import random
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


def score_on(book, ticker, date, bench_by_date, rsi_flip=False):
    """The engine's technical score for one ticker as at `date`, or None.

    Only sessions up to and including `date` are passed in, so the score cannot
    see the future. This calls the engine rather than reimplementing it: when
    the scoring changes, the backtest measures the new scoring.
    """
    end = book.index_upto(ticker, date)
    if end is None:
        # (None, None), not a bare None. Every other path here returns a
        # 2-tuple, and callers unpack it; this guard kept its old scalar shape
        # through the change and crashed the first real run on the first ticker
        # that had not listed yet. No fixture caught it because every fixture
        # gives every ticker every date -- a guard for absent data can only be
        # exercised by absent data.
        return None, None
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
    # The function returns (score, breakdown, warnings, blocks). Element zero is
    # the composite total; element three is the per-block subtotals. Both are
    # returned now: the composite answers whether the total ranks returns, and
    # the blocks answer which of them carries or drags, which the composite
    # cannot. Unpacked positionally rather than by arity so the backtest keeps
    # running when the thing it measures gains a field -- one that crashes for
    # that reason is one nobody reruns, and rerunning after every scoring change
    # is the whole point.
    result = E.calculate_technical_score(tech, True)
    if not isinstance(result, tuple):
        return result, None
    blocks = result[3] if len(result) > 3 else None
    if rsi_flip:
        return _flip_rsi(result[0], blocks, tech)
    return result[0], blocks


# The engine awards RSI_MOMENTUM_AWARD when rsi14 > RSI_MOMENTUM_FLOOR and
# nothing otherwise (engine.py, the momentum block). Read off the code rather
# than off the rulebook, because a measurement built on a number quoted in prose
# is a measurement of the prose.
RSI_MOMENTUM_AWARD = 15.0


def _flip_rsi(total, blocks, tech):
    """The score with the RSI comparison inverted: points for rsi14 BELOW 50.

    Open item 1 in the rulebook. TSaM pp.389-390 reports that the RSI's sign
    flipped around 1998 -- a trend indicator before, a mean-reverting one since
    -- so scoring continuation encodes a constant where the source documents a
    variable. This measures the other side of that choice.

    Implemented here and NEVER by editing RSI_MOMENTUM_FLOOR, because changing
    the shipped comparison to see whether it backtests better is adoption, not
    measurement, and the engine must keep scoring what it actually ships.

    The momentum block is recomputed and re-clamped rather than adjusted by
    arithmetic on the total. MACD also awards 15 into a block capped at 30, so
    a name holding both sits exactly at the cap; subtracting works by
    coincidence there and would fail the moment either award or the cap moved.
    rsi exactly at the floor scores zero on both sides, so the comparison stays
    symmetric.
    """
    rsi = tech.get("rsi14")
    if total is None or blocks is None or rsi is None:
        return total, blocks
    flipped = dict(blocks)
    current = flipped.get("momentum")
    if current is None:
        return total, blocks
    was = RSI_MOMENTUM_AWARD if rsi > E.RSI_MOMENTUM_FLOOR else 0.0
    now = RSI_MOMENTUM_AWARD if rsi < E.RSI_MOMENTUM_FLOOR else 0.0
    cap = E.TECHNICAL_BLOCK_MAX["momentum"]
    flipped["momentum"] = E.round1(E.clamp(current - was + now, 0, cap))
    return E.round1(total - current + flipped["momentum"]), flipped


def rank_on(book, date, bench_by_date, block=None, rsi_flip=False):
    """[(ticker, score)] for every ticker scoreable as at `date`, best first.

    Ties break on ticker ascending, the same rule the screener ranks by, so the
    selection is deterministic rather than dependent on dictionary order.

    block=None ranks on the composite technical total, which is what the
    portfolio trades. Naming one of TECHNICAL_BLOCK_NAMES ranks on that
    subtotal alone, which is how the blocks get measured separately: the
    composite is a weighted sum, and a near-zero result for the sum is
    consistent with one block carrying and another dragging by the same amount.
    """
    scored = []
    for ticker in book.tickers():
        score, blocks = score_on(book, ticker, date, bench_by_date, rsi_flip=rsi_flip)
        if block is not None:
            # A company with no block breakdown cannot be ranked on a block.
            # Dropping it is right: substituting zero would rank "not measured"
            # below every measured company, which is a claim nobody made.
            score = None if not blocks else blocks.get(block)
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


def run_portfolio(book, calendar, rebalances, bench_by_date, top_n, cost_bps_per_side,
                  rsi_flip=False):
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
        ranked = rank_on(book, signal_date, bench_by_date, rsi_flip=rsi_flip)
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
def _betacf(a, b, x):
    """Continued fraction for the incomplete beta function, by Lentz's method."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 3e-16:
            break
    return h


def _betainc(a, b, x):
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_front = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                 + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return math.exp(log_front) * _betacf(a, b, x) / a
    return 1.0 - math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                          + b * math.log(1.0 - x) + a * math.log(x)) * _betacf(b, a, 1.0 - x) / b


def two_sided_p(t_stat, degrees_of_freedom):
    """Two-sided p-value from Student's t.

    Student's t, NOT a normal approximation. The samples here are small -- ten
    independent windows at the twelve-month horizon -- and at nine degrees of
    freedom the normal understates the p-value badly: t=2.05 is p=0.04 under a
    normal and p=0.07 under t. That difference decides whether a result reads as
    significant, so the approximation was worth removing rather than caveating.
    """
    if degrees_of_freedom <= 0 or t_stat != t_stat:
        return float("nan")
    df = float(degrees_of_freedom)
    return _betainc(df / 2.0, 0.5, df / (df + t_stat * t_stat))


def bonferroni(p_value, tests):
    """p adjusted for how many tests were run, capped at 1.

    A backtest computes a t-stat per horizon, and comparing two scoring
    revisions doubles that. Two of eight clearing t=2 is close to what noise
    produces, so the unadjusted figure invites exactly the wrong conclusion.
    """
    if p_value != p_value:
        return float("nan")
    return min(1.0, p_value * max(1, tests))


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


# One-sided normal deviate for 80% power. Paired with a two-sided critical t
# below, which is the usual convention for a detectable-effect calculation.
Z_FOR_80_PERCENT_POWER = 0.8416


def _t_critical(df, alpha=0.05):
    """Two-sided critical t for `df`, found by bisection on two_sided_p.

    No lookup table and no new dependency: two_sided_p is already in this file
    and is already anchored to published values by
    test_p_values_come_from_t_not_from_a_normal, so this inherits that check
    rather than introducing a second source of truth for the same distribution.
    """
    if df < 1:
        return float("nan")
    low, high = 0.0, 1000.0
    for _ in range(200):
        mid = (low + high) / 2.0
        if two_sided_p(mid, df) > alpha:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


# Bootstrap draws and seed. Seeded deliberately: this repository's whole
# discipline is that a number can be reproduced exactly by whoever reads it
# next, and a confidence interval that moved every run would be the one figure
# in the file nobody could check. Changing the seed changes the interval in the
# third decimal, not the conclusion.
BOOTSTRAP_DRAWS = 2000
BOOTSTRAP_SEED = 20260913


def _newey_west_se(series, lag):
    """HAC standard error of the mean (Newey-West, Bartlett kernel).

    Overlapping h-period windows are serially correlated BY CONSTRUCTION: two
    windows one period apart share h-1 periods of data. The i.i.d. standard
    error sd/sqrt(n) is therefore the wrong estimator for them, and wrong in the
    direction that inflates t.

    That is a defect in the standard error, NOT a reason to discard overlapping
    observations. Discarding them is what the non-overlapping headline did, and
    at 12 months it threw away 109 of 119 observations to buy an SE it could
    trust -- leaving the horizon that actually survives Indian STCG with n = 10
    and no power, while the horizon with power (1 month) is untradeable at 754%
    turnover. Backwards.

        S  = g0 + 2 * sum_{k=1..L} (1 - k/(L+1)) * gk
        se = sqrt(S / n)

    where gk is the lag-k autocovariance. The Bartlett weight (1 - k/(L+1))
    guarantees a non-negative S, which Hansen-Hodrick's unweighted sum does not.
    L = h-1 is the standard choice for h-period overlap.

    lag = 0 reduces to the i.i.d. standard error up to the degrees-of-freedom
    convention: autocovariances here are divided by n, as Newey-West specifies,
    while the sample standard deviation beside it divides by n-1, so the two
    differ by exactly sqrt(n/(n-1)) and converge as n grows. The estimator
    follows the standard rather than being bent to make the two figures print
    identically. Either way lag 0 is the correct choice for a genuinely
    non-overlapping series, so both go through one code path.
    """
    n = len(series)
    if n < 2:
        return float("nan")
    mean = sum(series) / n
    deviations = [v - mean for v in series]
    gamma0 = sum(d * d for d in deviations) / n
    total = gamma0
    for k in range(1, min(lag, n - 1) + 1):
        gamma_k = sum(deviations[t] * deviations[t - k] for t in range(k, n)) / n
        total += 2.0 * (1.0 - k / (lag + 1.0)) * gamma_k
    if total <= 0:
        # Bartlett weights make this rare rather than impossible at tiny n.
        # Reporting NaN is honest; substituting the i.i.d. figure would silently
        # hand back the number this function exists to replace.
        return float("nan")
    return math.sqrt(total / n)


def _stationary_bootstrap_se(series, mean_block, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED):
    """(standard error, 2.5th pct, 97.5th pct) by the Politis-Romano bootstrap.

    A third, independent estimate, and it is here because HAC is known to be
    UNDERSIZED in small samples -- it under-states the variance and so
    over-rejects, exactly where our n is smallest. Two estimators that disagree
    are more informative than one that cannot be checked.

    The stationary bootstrap resamples blocks whose lengths are geometric with
    mean `mean_block`, wrapping circularly, which preserves serial dependence up
    to roughly that length while keeping the resampled series stationary. Fixed
    blocks would not be stationary; a plain i.i.d. bootstrap would destroy the
    dependence this is trying to respect.
    """
    n = len(series)
    if n < 3 or mean_block < 1:
        return float("nan"), float("nan"), float("nan")
    rng = random.Random(seed)
    p = 1.0 / mean_block
    means = []
    for _ in range(draws):
        total = 0.0
        index = rng.randrange(n)
        for _step in range(n):
            total += series[index]
            if rng.random() < p:
                index = rng.randrange(n)
            else:
                index = (index + 1) % n
        means.append(total / n)
    means.sort()
    centre = sum(means) / draws
    variance = sum((m - centre) ** 2 for m in means) / (draws - 1)
    lo = means[int(0.025 * draws)]
    hi = means[min(draws - 1, int(0.975 * draws))]
    return math.sqrt(variance), lo, hi


def _ic_statistics(series, family_size, hac_lag=0):
    """Mean, n and THREE standard errors for one series of monthly rank correlations.

    Pulled out of decile_study so the composite and every block compute their
    significance by one code path. Two of them drifting apart would be the kind
    of difference nobody notices until a number is quoted.

    Three estimators are reported side by side and none replaces another:

      iid        mean / (sd/sqrt(n)). Correct only if the observations are
                 independent, which overlapping windows are not.
      HAC        Newey-West at lag h-1. Valid under the serial correlation that
                 overlapping windows create by construction. Known to be
                 undersized in small samples, so it over-rejects where n is
                 smallest -- which is why the third estimator exists.
      bootstrap  Politis-Romano stationary bootstrap, mean block h. Makes no
                 normality assumption and is the check on HAC.

    Where the three disagree, the disagreement is the finding.
    """
    n = len(series)
    mean_ic = sum(series) / n if n else float("nan")
    if n > 1:
        spread = math.sqrt(sum((v - mean_ic) ** 2 for v in series) / (n - 1))
        t_stat = mean_ic / (spread / math.sqrt(n)) if spread > 0 else float("nan")
    else:
        spread = float("nan")
        t_stat = float("nan")

    hac_se = _newey_west_se(series, hac_lag) if n > 1 else float("nan")
    hac_t = (mean_ic / hac_se) if hac_se == hac_se and hac_se > 0 else float("nan")
    hac_p = two_sided_p(hac_t, n - 1)
    boot_se, boot_lo, boot_hi = _stationary_bootstrap_se(series, max(1, hac_lag + 1))
    boot_t = (mean_ic / boot_se) if boot_se == boot_se and boot_se > 0 else float("nan")
    # Computed here rather than by hand afterwards, so the significance of a
    # result is reproducible from the repository by whoever reads it next.
    p_value = two_sided_p(t_stat, n - 1)
    # The smallest mean IC this many observations could distinguish from zero at
    # 80% power. Reported beside every result because a null is only evidence of
    # absence when the test could have seen a presence, and at 12 months there
    # are about ten independent observations.
    #
    # The multiplier is t_critical(df) + z(0.80), NOT the flat 2.8 that holds
    # only for large samples. At df=9 the critical t is 2.262 rather than 1.96,
    # so 2.8 understates the detectable effect by about a tenth -- at precisely
    # the horizon where a reader is likeliest to read no-power as no-effect,
    # which is the misreading this figure exists to prevent.
    detectable = ((_t_critical(n - 1) + Z_FOR_80_PERCENT_POWER) * spread / math.sqrt(n)) \
        if n > 1 and spread == spread and spread > 0 else float("nan")
    return {
        "mean_ic": mean_ic,
        "ic_periods": n,
        "ic_sd": spread,
        "ic_t_stat": t_stat,
        "ic_p_value": p_value,
        "ic_p_bonferroni": bonferroni(p_value, family_size),
        "tests_in_family": family_size,
        "detectable_ic_80pct": detectable,
        # --- the two estimators that do not assume independence ---
        "hac_lag": hac_lag,
        "hac_se": hac_se,
        "hac_t_stat": hac_t,
        "hac_p_value": hac_p,
        "hac_p_bonferroni": bonferroni(hac_p, family_size),
        "bootstrap_se": boot_se,
        "bootstrap_t_stat": boot_t,
        "bootstrap_ci_lo": boot_lo,
        "bootstrap_ci_hi": boot_hi,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        # A bootstrap interval that straddles zero says the same thing as a
        # failed t-test without assuming normality, so it is the figure to quote
        # when HAC and iid disagree.
        "bootstrap_excludes_zero": (boot_lo == boot_lo and boot_hi == boot_hi
                                    and (boot_lo > 0) == (boot_hi > 0)),
    }


def decile_study(book, calendar, rebalances, bench_by_date, horizons=DECILE_HORIZONS,
                 block=None, family_size=None, rsi_flip=False):
    """Forward returns by score decile, plus the rank correlation each month.

    If the top decile does not beat the bottom, the score does not rank future
    returns, and no amount of portfolio construction on top of it will help.

    Two samplings are reported for every horizon, because they answer different
    questions and only one of them is honest as a headline:

      overlapping      every rebalance is a sample, so a 12-month horizon
                       sampled monthly reuses eleven twelfths of each window.
                       Observations are plentiful and NOT independent, so the
                       t-statistic is inflated -- this was previously the only
                       figure computed here, while the non-overlapping estimate
                       lived solely in ab_compare.py.
      non_overlapping  stride equals the horizon, so no two windows share a day.
                       Far fewer observations, and the t-statistic means what it
                       says. This is the headline.

    A sign that flips between the two is a phase artefact, not an edge: the
    non-overlapping series keeps one of `horizon` possible phase offsets and
    discards the rest.

    block=None measures the composite total. Naming a block measures that
    subtotal alone. family_size is the number of t-statistics computed across
    the whole run, which is what Bonferroni must divide by -- leaving it at the
    horizon count while adding four blocks would understate the correction
    precisely where the extra tests are being added.
    """
    if family_size is None:
        family_size = len(horizons)
    buckets = {h: {d: [] for d in range(10)} for h in horizons}
    ics = {h: {"overlapping": [], "non_overlapping": []} for h in horizons}
    for index, signal_date in enumerate(rebalances):
        entry_date = next_session(calendar, signal_date)
        if entry_date is None:
            continue
        ranked = rank_on(book, signal_date, bench_by_date, block=block, rsi_flip=rsi_flip)
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
            if ic is None:
                # A block whose scores are all equal has no rank correlation at
                # all. Volume takes only 0, 5 or 10, so whole months tie and
                # drop out here -- which is why every block reports its own n
                # rather than inheriting the composite's.
                continue
            ics[horizon]["overlapping"].append(ic)
            if index % horizon == 0:
                ics[horizon]["non_overlapping"].append(ic)
    summary = {}
    for horizon in horizons:
        deciles = {}
        for decile in range(10):
            values = buckets[horizon][decile]
            deciles[decile] = {
                "observations": len(values),
                "mean_return": sum(values) / len(values) if values else float("nan"),
            }
        # Overlapping windows at horizon h are correlated out to lag h-1, which
        # is exactly the Newey-West bandwidth. The non-overlapping series shares
        # no days between windows, so lag 0 is correct there and the HAC figure
        # collapses onto the i.i.d. one -- which is itself a useful check: if
        # those two ever diverge for the non-overlapping series, the estimator
        # is wrong rather than the data.
        overlapping = _ic_statistics(ics[horizon]["overlapping"], family_size,
                                     hac_lag=horizon - 1)
        non_overlapping = _ic_statistics(ics[horizon]["non_overlapping"], family_size,
                                         hac_lag=0)
        summary[horizon] = {
            "deciles": deciles,
            "overlapping": overlapping,
            "non_overlapping": non_overlapping,
            # The headline is the non-overlapping estimate. These flattened keys
            # keep the shape older readers expect, and they now carry the honest
            # figure rather than the inflated one.
            "mean_ic": non_overlapping["mean_ic"],
            "ic_periods": non_overlapping["ic_periods"],
            "ic_t_stat": non_overlapping["ic_t_stat"],
            "ic_p_value": non_overlapping["ic_p_value"],
            "ic_p_bonferroni": non_overlapping["ic_p_bonferroni"],
            "tests_in_family": family_size,
            "detectable_ic_80pct": non_overlapping["detectable_ic_80pct"],
            "sign_flips": (overlapping["mean_ic"] == overlapping["mean_ic"]
                           and non_overlapping["mean_ic"] == non_overlapping["mean_ic"]
                           and (overlapping["mean_ic"] > 0) != (non_overlapping["mean_ic"] > 0)),
        }
    return summary


# --- Reporting -------------------------------------------------------------
def _ic_sentence(block):
    """One line carrying the headline IC, its n, and what n could have detected.

    The detectable figure is not decoration. Reporting a non-overlapping null
    without it invites the mirror of the error this file just fixed: the
    overlapping estimate inflates t, so quoting it overstates a finding, and the
    non-overlapping estimate at 12 months rests on about ten observations, so
    quoting THAT without its power understates one. A null is evidence of
    absence only where the test could have seen a presence.
    """
    non = block["non_overlapping"]
    over = block["overlapping"]
    # At horizon 1 there is no overlap, so the i.i.d. SE is the correct estimator
    # and HAC agrees with it to two decimals. Labelling it invalid there would
    # tell the reader a sound number is unsound -- the mirror of the error this
    # whole section fixes.
    iid_note = " (**invalid at this overlap**)" if over.get("hac_lag") else " (valid: no overlap)"
    text = ("IC %+.4f on n %d (all windows). t: iid %+.2f%s, "
            "HAC %+.2f, bootstrap %+.2f. HAC p %.3f after Bonferroni "
            "over %d tests; bootstrap 95%% CI [%+.4f, %+.4f]%s. "
            "Discarding overlap instead: IC %+.4f, t %+.2f on n %d, "
            "detectable at 80%% power %.3f."
            % (over["mean_ic"], over["ic_periods"],
               over["ic_t_stat"], iid_note, over["hac_t_stat"], over["bootstrap_t_stat"],
               over["hac_p_bonferroni"], over["tests_in_family"],
               over["bootstrap_ci_lo"], over["bootstrap_ci_hi"],
               "" if not over.get("bootstrap_excludes_zero") else " **excludes zero**",
               non["mean_ic"], non["ic_t_stat"], non["ic_periods"],
               non["detectable_ic_80pct"]))
    if block.get("sign_flips"):
        text += (" -- sign flips between the two samplings; with a valid SE this is "
                 "a sampling-phase difference rather than evidence either way")
    return text


def _ic_lines(block):
    """The block-level IC paragraph for the composite sections."""
    return [
        "Mean rank correlation: %s" % _ic_sentence(block),
        "",
        "**Three standard errors, one point estimate.** Overlapping windows are "
        "serially correlated by construction -- at horizon h, consecutive windows "
        "share h-1 periods -- so the i.i.d. standard error sd/sqrt(n) is the wrong "
        "estimator for them and inflates t. That is a defect in the SE, not a reason "
        "to throw the observations away. Newey-West at lag h-1 keeps all n windows "
        "with a valid SE; the Politis-Romano stationary bootstrap is an independent "
        "check on it, because HAC is known to be undersized in small samples and so "
        "over-rejects exactly where n is smallest. Where HAC and the bootstrap "
        "disagree, trust neither without saying so.",
        "",
        "The discard-the-overlap figure is retained as a robustness check, not as the "
        "headline it used to be. At 12 months it keeps 1 window in 12 and cannot "
        "detect any plausible effect; reading its null as evidence of absence is the "
        "mirror of reading the inflated i.i.d. t as evidence of presence.",
    ]


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
    "What is measured is the composite technical TOTAL, not the four blocks "
    "behind it. A near-zero result says that one particular weighted sum of the "
    "indicators does not rank returns. It does not say which block carries or "
    "drags, and it is not evidence that each indicator is individually useless.",
    "Several t-statistics are computed per run, across horizons and engine "
    "revisions. Two of eight clearing t=2 is roughly what noise produces, so "
    "judge any single significant figure against how many were computed, and "
    "distrust one whose sign flips between the overlapping and non-overlapping "
    "estimates.",
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
        out.append("Top minus bottom: **%s**." % pct(spread))
        out.append("")
        out.extend(_ic_lines(block))
        out.append("")
    if results.get("block_deciles"):
        out.append("## Which block carries, and which drags")
        out.append("")
        out.append("The composite is a weighted sum of four blocks, so a near-zero total is "
                   "equally consistent with four dead blocks and with two that cancel. Each "
                   "block below is ranked on its own subtotal. Every t-statistic in this run, "
                   "composite and blocks together, counts towards one Bonferroni family.")
        out.append("")
        for name in sorted(results["block_deciles"]):
            out.append("### %s" % name)
            out.append("")
            for horizon, block in sorted(results["block_deciles"][name].items()):
                out.append("- **%d-month**: %s" % (horizon, _ic_sentence(block)))
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
             variants_tried=1, variants_note="", rsi_flip=False):
    book = PriceBook(history)
    calendar = market_calendar(history)
    rebalances = month_end_sessions(calendar)
    bench = history[E.BENCHMARK_SYMBOL]
    bench_by_date = dict(zip(bench["dates"], bench["closes"]))

    periods = run_portfolio(book, calendar, rebalances, bench_by_date, top_n, cost_bps_per_side,
                            rsi_flip=rsi_flip)
    equal = run_equal_weight(book, calendar, rebalances)
    index = run_benchmark_index(book, calendar, rebalances)
    # The composite, then each block on its own. backtest.py's own LIMITATIONS
    # say the composite result "does not say which block carries or drags", and
    # that is the question a near-zero total leaves open: a weighted sum of four
    # things can be zero because all four are zero, or because two cancel.
    #
    # The Bonferroni family covers every t-statistic the run computes -- four
    # horizons for the composite plus four for each of four blocks -- because
    # adding sixteen tests while still dividing by four would understate the
    # correction exactly where the new tests are being added.
    block_names = sorted(E.TECHNICAL_BLOCK_MAX)
    family = len(DECILE_HORIZONS) * (1 + len(block_names))
    deciles = decile_study(book, calendar, rebalances, bench_by_date, family_size=family,
                           rsi_flip=rsi_flip)
    block_deciles = {
        name: decile_study(book, calendar, rebalances, bench_by_date,
                           block=name, family_size=family, rsi_flip=rsi_flip)
        for name in block_names
    }

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
        "block_deciles": block_deciles,
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
        # Session 252 of the fixture, not session 66. The date used to be
        # 2024-04-01, which is 66 sessions in -- below the 200 the engine needs
        # to score at all -- so BOTH sides were None and the assertion compared
        # one absence to another. A broken slicing implementation would have
        # passed it just as happily. 252 is chosen so the 52-week high is live,
        # because that is the indicator most likely to leak the future if the
        # slicing were wrong, and it sits below the cut at 280 so the truncated
        # book still reaches it.
        probe = dates[251]
        later, later_blocks = score_on(book, "UP", probe, bench)
        earlier, earlier_blocks = score_on(PriceBook(truncated), "UP", probe, bench)
        # Unpacked rather than compared as tuples. score_on used to return a
        # bare score and now returns (score, blocks); comparing the tuples would
        # still pass while asserting less, and would pass identically if both
        # sides were (None, None) -- which is the one outcome this test exists
        # to rule out.
        self.assertIsNotNone(later)
        self.assertEqual(later, earlier)
        self.assertEqual(later_blocks, earlier_blocks)

    def test_a_ticker_that_has_not_listed_yet_is_skipped_not_crashed(self):
        # The real universe lists companies at different times, so at any early
        # rebalance some tickers have no sessions at all. score_on guards that
        # with an early return, and when its other paths became 2-tuples this
        # one stayed a bare None -- which crashed rank_on's unpack on the first
        # such ticker of a full run, after three minutes of compute.
        #
        # Every other fixture here gives every ticker every date, so none of
        # them can reach this branch. That is the point of this one: a guard for
        # missing data is only tested by missing data.
        dates, history = self._history()
        history = dict(history)
        history["LATE"] = self._series(dates[-20:], [50.0 + i for i in range(20)])
        book = PriceBook(history)
        bench = dict(zip(dates, history[E.BENCHMARK_SYMBOL]["closes"]))
        early = dates[100]
        self.assertIsNone(book.index_upto("LATE", early))
        score, blocks = score_on(book, "LATE", early, bench)  # must not raise
        self.assertIsNone(score)
        self.assertIsNone(blocks)
        # And the ticker is absent from the ranking rather than ranked at zero,
        # which would place "not listed" above every company that scored badly.
        ranked = rank_on(book, early, bench)
        self.assertNotIn("LATE", [ticker for ticker, _ in ranked])

    def test_the_rsi_flip_reaches_the_ranking_and_changes_it(self):
        # --rsi-flip must actually reach the ranking, not merely be accepted as
        # a parameter. A function that takes a flag and never uses it passes
        # every grep ever written, so this asserts on behaviour instead.
        #
        # Fourteen tickers, because decile_study skips any month where fewer
        # than ten companies score. The first version of this check used six,
        # produced zero observations, and compared two NaN means -- which are
        # "different" since nan != nan, so it passed while proving nothing.
        dates = self._business_days(420, start="2022-01-01")
        history = {}
        for k in range(14):
            drift = 0.06 if k % 2 else -0.04
            history["T%02d" % k] = self._series(
                dates, [100.0 + math.sin(i / (6.0 + k)) * 9.0 + i * drift
                        for i in range(len(dates))])
        history[E.BENCHMARK_SYMBOL] = self._series(
            dates, [1000.0 + i * 0.08 for i in range(len(dates))])
        book = PriceBook(history)
        calendar = market_calendar(history)
        rebalances = month_end_sessions(calendar)
        bench = dict(zip(dates, history[E.BENCHMARK_SYMBOL]["closes"]))

        normal = decile_study(book, calendar, rebalances, bench,
                              horizons=(1,), family_size=4)[1]["overlapping"]
        flipped = decile_study(book, calendar, rebalances, bench, horizons=(1,),
                               family_size=4, rsi_flip=True)[1]["overlapping"]
        # Guard before asserting: with no observations both means are NaN and
        # any inequality check below would pass vacuously.
        self.assertGreater(normal["ic_periods"], 0)
        self.assertEqual(normal["ic_periods"], flipped["ic_periods"])
        self.assertFalse(math.isnan(normal["mean_ic"]))
        self.assertFalse(math.isnan(flipped["mean_ic"]))
        # A magnitude, not mere inequality: two floats differing in the last bit
        # are "not equal" but would not show the flag had done anything. The
        # observed gap on this fixture is about 3.4e-3, so 1e-3 separates a real
        # effect from float noise while still failing loudly if the flag goes
        # inert.
        self.assertGreater(abs(normal["mean_ic"] - flipped["mean_ic"]), 1e-3)

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

    def test_p_values_come_from_t_not_from_a_normal(self):
        # Anchors that can be checked against a table rather than against this
        # implementation: t converges on the normal as df grows, df=1 is Cauchy,
        # and 2.2281 is the textbook 5% two-sided critical value at df=10.
        self.assertAlmostEqual(two_sided_p(1.96, 1000000), 0.05, places=4)
        self.assertAlmostEqual(two_sided_p(1.0, 1), 0.5, places=6)
        self.assertAlmostEqual(two_sided_p(2.2281, 10), 0.05, places=4)
        # The case that made this worth fixing: at nine degrees of freedom a
        # normal approximation reports 0.040 where t reports 0.071, which is the
        # difference between "significant" and not.
        self.assertAlmostEqual(two_sided_p(2.05, 9), 0.0706, places=4)
        self.assertGreater(two_sided_p(2.05, 9), math.erfc(2.05 / math.sqrt(2.0)))

    def test_hac_matches_iid_on_white_noise_and_exceeds_it_under_autocorrelation(self):
        # The whole reason HAC exists here. On independent draws it should agree
        # with the i.i.d. standard error; on a positively autocorrelated series
        # -- which is what overlapping windows produce by construction -- it must
        # be LARGER, because the i.i.d. figure understates the variance there and
        # so inflates t. A HAC implementation that did not do this would leave
        # the same wrong answer with more machinery in front of it.
        rng = random.Random(11)
        white = [rng.gauss(0.0, 1.0) for _ in range(400)]
        n = len(white)
        sd = math.sqrt(sum((v - sum(white) / n) ** 2 for v in white) / (n - 1))
        iid_se = sd / math.sqrt(n)
        self.assertAlmostEqual(_newey_west_se(white, 0), iid_se * math.sqrt((n - 1) / n), places=12)
        # Lag 0 and the i.i.d. figure differ only by the n vs n-1 convention.
        self.assertAlmostEqual(_newey_west_se(white, 0) / iid_se, math.sqrt((n - 1) / n), places=12)
        # White noise: adding lags should not inflate it much.
        self.assertLess(_newey_west_se(white, 11) / iid_se, 1.35)
        # Strong positive autocorrelation: an AR(1) with phi=0.8.
        ar, prev = [], 0.0
        for _ in range(400):
            prev = 0.8 * prev + rng.gauss(0.0, 1.0)
            ar.append(prev)
        m = sum(ar) / len(ar)
        ar_sd = math.sqrt(sum((v - m) ** 2 for v in ar) / (len(ar) - 1))
        ar_iid = ar_sd / math.sqrt(len(ar))
        self.assertGreater(_newey_west_se(ar, 11), ar_iid * 1.5)

    def test_the_stationary_bootstrap_is_reproducible_and_sane(self):
        # Reproducibility is not decoration in this repository: a confidence
        # interval that moved between runs would be the one number nobody could
        # check against a previous report.
        rng = random.Random(5)
        series = [rng.gauss(0.02, 0.2) for _ in range(120)]
        a = _stationary_bootstrap_se(series, 4)
        b = _stationary_bootstrap_se(series, 4)
        self.assertEqual(a, b)
        se, lo, hi = a
        self.assertTrue(se > 0 and lo < hi)
        # The interval must bracket the sample mean it was drawn from.
        mean = sum(series) / len(series)
        self.assertLess(lo, mean)
        self.assertGreater(hi, mean)
        # A different seed gives a different interval but the same ballpark.
        se2, _, _ = _stationary_bootstrap_se(series, 4, seed=BOOTSTRAP_SEED + 1)
        self.assertNotEqual(se, se2)
        self.assertLess(abs(se - se2) / se, 0.25)

    def test_bonferroni_scales_and_caps(self):
        self.assertAlmostEqual(bonferroni(0.0175, 8), 0.14, places=6)
        self.assertEqual(bonferroni(0.5, 8), 1.0)
        self.assertAlmostEqual(bonferroni(0.01, 1), 0.01, places=12)


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
    parser.add_argument("--rsi-flip", action="store_true",
                        help="score rsi14 BELOW the momentum floor instead of above it "
                             "(rulebook open item 1). A measurement only: the shipped "
                             "engine is untouched and RSI_MOMENTUM_FLOOR is not edited, "
                             "because changing the live comparison to see whether it "
                             "backtests better is adoption rather than measurement.")
    parser.add_argument("--self-test", action="store_true", help="run the offline checks and exit")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.self_test:
        suite = unittest.TestLoader().loadTestsFromTestCase(BacktestTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1

    if not args.prices:
        parser.error("--prices is required unless --self-test is given")
    history, skipped = E.parse_price_history_csv(Path(args.prices).read_text(encoding="utf-8"))
    print("Loaded %d tickers (%d rows skipped)." % (len(history), skipped))
    if args.rsi_flip:
        print("RSI SIGN FLIPPED: scoring rsi14 below %s instead of above it. "
              "This measures the alternative; it does not change the engine."
              % E.RSI_MOMENTUM_FLOOR)
    results = backtest(history, args.top_n, args.cost_bps,
                       args.variants_tried, args.variants_note, rsi_flip=args.rsi_flip)
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
