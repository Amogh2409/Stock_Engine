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
import csv
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
# The in/out split predates the holdout and is now largely superseded by it.
# With HOLDOUT_START at 2023-01-01 these two constants bracket a single calendar
# year, so the out_of_sample block holds eleven rebalances and its CAGR is an
# annualisation of one year's luck. The split is kept because it describes how
# the engine was developed -- everything before 2022 was seen during design --
# but the reserved window in knowledge/holdout.md is the one that now carries
# the evidential weight. Reporting both without saying which is which is how a
# one-year number gets quoted as an out-of-sample result.
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


# Reserved data. See knowledge/holdout.md for what this window is and, more
# importantly, what it is not: it was observed once on 2026-09-13, though no
# engine parameter has been changed in response. Used once for observation,
# never for fitting.
HOLDOUT_START = "2023-01-01"


def month_end_sessions(calendar, respect_holdout=True):
    """The last session of each month, which is when the screen is re-run.

    Truncated at HOLDOUT_START by default. The cut lives here rather than in
    each caller because this is the single point every consumer goes through --
    backtest() and ab_compare's analyse() both build their rebalances from it --
    so a new caller inherits the protection instead of having to remember it.

    The technical half is entirely price-driven, so reserving a window costs
    nothing but data and needs no fundamentals export. It does cost data: the
    cut surrenders roughly 44 of 130 rebalances, which at 12 months leaves about
    seven independent observations. A 12-month claim was not settleable on this
    span before the cut and is less so after it. That is a real price, paid
    because a window measured twice answers nothing the second time.
    """
    every_month = []
    for index, date in enumerate(calendar):
        is_last = index + 1 == len(calendar) or calendar[index + 1][:7] != date[:7]
        if is_last:
            every_month.append(date)
    if not respect_holdout:
        return every_month
    kept = [d for d in every_month if d < HOLDOUT_START]
    if every_month and not kept:
        # Refusing rather than returning []. An empty rebalance list produces a
        # portfolio of nothing, a report of nothing, and an exit code of zero --
        # a run that looks completed and carries no information. That is the
        # failure mode this repository keeps rediscovering, so it fails loudly
        # here instead of silently downstream.
        raise SystemExit(
            "Every month in this price file falls inside the reserved window "
            "(%s onward), so respecting the holdout leaves nothing to measure. "
            "The file spans %s to %s. Supply price history that reaches back "
            "before %s, or pass --no-respect-holdout if this is the single "
            "final test described in knowledge/holdout.md."
            % (HOLDOUT_START, every_month[0], every_month[-1], HOLDOUT_START))
    return kept


def _apply_no_skip_month(tech, closes_raw, bench_raw):
    """Rewrite relative strength back to t-h..t-1, the pre-2026-09-14 window.

    The ENGINE now skips the most recent month by default (see
    E.RELATIVE_STRENGTH_SKIP_SESSIONS), because CFA rf-v2016-n4-1#71 sources the
    2-12 construction. This flag restores the old window so the change remains
    measurable from the harness, exactly as --rsi-flip keeps the other side of
    the RSI question measurable. It does not edit the engine.

    Short-horizon reversal contaminates the most recent month, which is why the
    academic momentum construction (Jegadeesh-Titman) skips it. The engine
    measures to t-1. This measures the skip-month form WITHOUT touching
    engine.py, for the reason --rsi-flip does not touch it: changing the shipped
    comparison to see whether it backtests better is adoption, not measurement.

    The START stays anchored at t-h and only the END moves back one month, which
    is the 12-2 construction. Shifting the whole window instead would give
    t-13..t-1, which is a different quantity and not the one asked for.

    The pairs are rebuilt exactly as compute_technical_indicators builds them,
    through the engine's own helpers, so the window is the only difference.
    """
    closes = [E._finite_or_nan(v) for v in closes_raw]
    n = len(closes)
    valid = [i for i in range(n) if not math.isnan(closes[i])]
    if not valid:
        return
    bench = E._align_to_end([E._finite_or_nan(v) for v in bench_raw], n, float("nan"))
    pairs = [(closes[i], bench[i]) for i in valid if not math.isnan(bench[i])]
    for key, sessions in (("relativeStrength3M", E.SESSIONS_3_MONTH),
                          ("relativeStrength6M", E.SESSIONS_6_MONTH),
                          ("relativeStrength12M", E.SESSIONS_12_MONTH)):
        tech[key] = E._relative_strength(pairs, sessions)
    tech["available"]["relativeStrength6M"] = tech["relativeStrength6M"] is not None


def technicals_on(book, ticker, date, bench_by_date, no_skip_month=False):
    """The engine's raw technical indicators for one ticker as at `date`, or None.

    Lifted out of score_on so a cross-sectional scorer can reach the underlying
    continuous values rather than the points they are thresholded into. score_on
    still routes through it, so there is exactly one place that decides which
    slice of history a ticker is scored on and both modes see the same slice.

    Only sessions up to and including `date` are passed in, so nothing here can
    see the future.
    """
    end = book.index_upto(ticker, date)
    if end is None:
        return None
    series = book.history[ticker]
    upto = end + 1
    dates = series["dates"][:upto]
    bench_raw = [bench_by_date.get(d) for d in dates]
    tech = E.compute_technical_indicators(
        series["closes"][:upto],
        bench_raw,
        series["volumes"][:upto],
        source="backtest",
        dates=dates,
        highs=series["highs"][:upto],
        lows=series["lows"][:upto],
    )
    if no_skip_month:
        _apply_no_skip_month(tech, series["closes"][:upto], bench_raw)
    return tech


def score_on(book, ticker, date, bench_by_date, rsi_flip=False, no_skip_month=False):
    """The engine's technical score for one ticker as at `date`, or None.

    Only sessions up to and including `date` are passed in, so the score cannot
    see the future. This calls the engine rather than reimplementing it: when
    the scoring changes, the backtest measures the new scoring.
    """
    tech = technicals_on(book, ticker, date, bench_by_date, no_skip_month=no_skip_month)
    if tech is None:
        # (None, None), not a bare None. Every other path here returns a
        # 2-tuple, and callers unpack it; this guard kept its old scalar shape
        # through the change and crashed the first real run on the first ticker
        # that had not listed yet. No fixture caught it because every fixture
        # gives every ticker every date -- a guard for absent data can only be
        # exercised by absent data.
        return None, None
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


# --- Continuous scoring, a measurement variant -----------------------------
# The points model binarizes every feature it scores: "rsi14 > 50 -> 15 points"
# makes RSI 51 and RSI 89 identical, and "relativeStrength6M > 0 -> 10 points"
# throws away the difference between beating the index by 0.1% and by 80%. This
# scores the same twelve quantities on their magnitudes instead.
#
# It keeps the engine's own weights -- the within-block weights ARE the point
# awards, and the blocks combine at TECHNICAL_BLOCK_MAX -- so a difference
# between the two measures thresholding alone. Rebuilding the weights at the
# same time would confound the two and answer neither question.
#
# Implemented here and never in engine.py, for the reason --rsi-flip is: the
# engine must keep scoring what it ships, and a cross-sectional score cannot be
# mirrored into TypeScript anyway, because "the cross-section" there is whatever
# CSV a user uploaded. Parity would assert equality between two different
# quantities.

# Fixed before any measurement was run and never tuned. Winsorising at all is a
# judgement; 2.5% is the conventional choice and adopting a different one
# because it improved an IC would be fitting. Recorded in the rulebook.
WINSOR_TAIL = 0.025

# (block, name, extractor, weight). The weight is the engine's own point award
# for that feature, read off calculate_technical_score rather than off prose.
# Every extractor is oriented so that larger is better, matching the direction
# the points model awards in.
CONTINUOUS_FEATURES = (
    ("trend", "priceOverSma200", lambda t: _ratio(t.get("currentPrice"), t.get("sma200")), 12.0),
    ("trend", "priceOverSma50", lambda t: _ratio(t.get("currentPrice"), t.get("sma50")), 8.0),
    ("trend", "smaCross", lambda t: _ratio(t.get("sma50"), t.get("sma200")), 8.0),
    ("trend", "adx14", lambda t: t.get("adx14"), 4.0),
    ("trend", "distFrom52WHighPct", lambda t: t.get("distFrom52WHighPct"), 8.0),
    ("momentum", "macdHistogramPct", lambda t: _pct_of_price(t.get("macdHistogram"),
                                                             t.get("currentPrice")), 15.0),
    ("momentum", "rsi14", lambda t: t.get("rsi14"), 15.0),
    ("relStrength", "relativeStrength3M", lambda t: t.get("relativeStrength3M"), 5.0),
    ("relStrength", "relativeStrength6M", lambda t: t.get("relativeStrength6M"), 10.0),
    ("relStrength", "relativeStrength12M", lambda t: t.get("relativeStrength12M"), 5.0),
    ("volume", "volumeRatio20D", lambda t: t.get("volumeRatio20D"), 5.0),
    ("volume", "obvPressure20D", lambda t: t.get("obvPressure20D"), 5.0),
)


def _ratio(numerator, denominator):
    """numerator/denominator - 1, or None. The engine stores only the boolean."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator - 1.0


def _pct_of_price(value, price):
    """The engine's own normalisation for the MACD histogram (percent of price)."""
    if value is None or price is None or price == 0:
        return None
    return value / price * 100.0


def _winsorised_z(values, tail=WINSOR_TAIL):
    """Cross-sectional z-scores after clipping both tails. Ties are not broken.

    Returns a list the same length as `values`, or None when the cross-section
    has no spread -- in which case the feature orders nothing that month and
    contributing zero is the honest answer rather than an arbitrary one.
    """
    n = len(values)
    if n < 2:
        return None
    ordered = sorted(values)
    # Index rather than interpolate: with ~90 names the difference is under one
    # rank and an interpolated quantile is a second convention to keep in step
    # with the TypeScript side if this ever moves.
    # int(n * tail) is ZERO for every n below 40 at tail=0.025, which silently
    # disables clipping altogether -- no error, no warning, and the only symptom
    # is a slightly wrong number. It does not bite on the full universe (80 to 95
    # scoreable names across every pre-holdout period) but it would bite the
    # moment anything z-scores within a smaller group, which is exactly where a
    # single outlier does the most damage.
    #
    # Floor it at one point per tail, then refuse to clip so hard that fewer than
    # three points survive in the middle: at n=3 or 4 there is no tail to speak
    # of, and destroying the spread would be worse than leaving it alone.
    cut = min(max(1, int(n * tail)), max(0, (n - 3) // 2))
    lo, hi = ordered[cut], ordered[n - 1 - cut]
    clipped = [clamp_value(v, lo, hi) for v in values]
    mean = sum(clipped) / n
    variance = sum((v - mean) ** 2 for v in clipped) / (n - 1)
    if variance <= 0:
        return None
    sd = math.sqrt(variance)
    return [(v - mean) / sd for v in clipped]


def clamp_value(value, low, high):
    return low if value < low else (high if value > high else value)


def _population_sd(values):
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / n)


def continuous_scores(entries, block=None, points_blocks=None):
    """{ticker: score} from [(ticker, tech)], scored on magnitudes not thresholds.

    block=None gives the composite; naming one of TECHNICAL_BLOCK_MAX gives that
    subtotal alone, so the blocks can be measured separately exactly as they are
    for the points model.

    Cross-sectional by construction, so it lives here rather than in score_on:
    a z-score needs the whole cross-section at one date, and a per-ticker
    function cannot see it.

    TWO THINGS ARE MATCHED TO THE POINTS MODEL ON PURPOSE, so that a difference
    between the two measures thresholding and nothing else. An earlier revision
    claimed that without doing either, and the claim was false in both places.

    1. A feature the engine could not compute takes the MINIMUM z rather than
       the mean. Absent data is not evidence of a low value, and on its own
       merits the mean is the better choice -- but the points model awards
       nothing for an absent feature, which is exactly what it awards for one
       that fails its test. Matching it keeps the comparison clean. It affects
       3.6% of observations, on distFrom52WHighPct and relativeStrength12M only.

    2. Each block is rescaled so its cross-sectional spread equals the spread of
       the points model's own subtotal for that block, on that date, over the
       same names. What a block contributes to a ranking is its spread, not its
       nominal cap, and NEITHER mode realises 40:30:20:10 -- measured over 87
       dates the points model realises 36.1 / 32.0 / 22.7 / 9.2 and the
       unmatched continuous form realises 38.2 / 32.1 / 21.3 / 8.4, because the
       block SD is BLOCK_MAX * sqrt(w'Rw)/sum(w) and the within-block feature
       correlation R differs by block. Trend's five features are near-collinear;
       volume's two are not. Left unmatched the two modes differ by up to 9.4%
       in realised block share, and an IC difference would be part thresholding
       and part reweighting with no way to separate them.

    points_blocks is {ticker: {block: subtotal}} from the engine. Without it the
    nominal caps are used and the comparison is NOT clean; rank_on always passes
    it.
    """
    if not entries:
        return {}
    tickers = [ticker for ticker, _tech in entries]
    zeros = {ticker: 0.0 for ticker in tickers}
    block_weight = {block: 0.0 for block in E.TECHNICAL_BLOCK_MAX}
    block_total = {block: dict(zeros) for block in E.TECHNICAL_BLOCK_MAX}
    # NOT `for block, ...`: that shadows the `block` parameter, and after the
    # loop every call would return whichever block came last in
    # CONTINUOUS_FEATURES. It did, silently -- composite and all four blocks
    # returned the volume subtotal, and the only symptom was that a fixture
    # produced fewer distinct scores than the points model it was supposed to
    # out-resolve.
    for feature_block, _name, extract, weight in CONTINUOUS_FEATURES:
        raw = [extract(tech) for _ticker, tech in entries]
        present = [(i, v) for i, v in enumerate(raw) if v is not None]
        if len(present) < 2:
            continue
        z = _winsorised_z([v for _i, v in present])
        if z is None:
            continue
        block_weight[feature_block] += weight
        # Absent takes the MINIMUM, not the mean, because that is what the
        # points model does: it awards nothing for a feature it could not
        # compute and nothing for one that failed its test, so the two are
        # indistinguishable there and must be here too.
        floor_z = min(z)
        for ticker in tickers:
            block_total[feature_block][ticker] += weight * floor_z
        for (index, _v), score in zip(present, z):
            block_total[feature_block][tickers[index]] += weight * (score - floor_z)

    # Rescale each block to the spread the points model actually realises for
    # it, on this date, over these names. Without this the two modes weight the
    # blocks differently -- measured 38.2/32.1/21.3/8.4 against 36.1/32.0/22.7/9.2
    # -- and an IC difference would be part thresholding and part reweighting.
    scale = {}
    for name in E.TECHNICAL_BLOCK_MAX:
        if block_weight[name] <= 0:
            scale[name] = 0.0
            continue
        spread = _population_sd([block_total[name][t] / block_weight[name] for t in tickers])
        target = None
        if points_blocks:
            subtotals = [points_blocks[t].get(name) for t in tickers
                         if points_blocks.get(t) is not None]
            if len(subtotals) == len(tickers) and all(v is not None for v in subtotals):
                target = _population_sd(subtotals)
        if target is None:
            # No points subtotals to match: fall back to the nominal cap and
            # accept that the comparison is not clean. rank_on always supplies
            # them, so this is the direct-call path only.
            scale[name] = E.TECHNICAL_BLOCK_MAX[name]
        else:
            scale[name] = (target / spread) if spread > 0 else 0.0

    wanted = sorted(E.TECHNICAL_BLOCK_MAX) if block is None else [block]
    out = {}
    for ticker in tickers:
        total = 0.0
        for name in wanted:
            if block_weight.get(name, 0.0) > 0:
                total += scale[name] * block_total[name][ticker] / block_weight[name]
        out[ticker] = total
    return out


# --- Sector and size neutralisation, a measurement variant -----------------
# Both inputs are honest about what they are, and they are NOT the same kind of
# thing:
#
# SECTOR is real, and stale. data/nifty100_source.csv is the NSE index file and
# carries an Industry column for all 100 constituents. It is a snapshot as of
# 2026-09-10, so applying it to 2015-2022 is look-ahead -- but of a categorically
# milder kind than market cap. Today's market cap is a monotone function of the
# cumulative return over the very window being predicted, so neutralising on it
# would regress the signal against the answer. An industry label is not a
# function of returns; its leak is confined to reclassification, and index
# membership survivorship is already a standing limitation on every figure here
# rather than a new one.
#
# SIZE IS A SUBSTITUTE AND IS NAMED AS ONE. There is no historical market cap in
# this repository -- no shares outstanding, no free float, and the only
# fundamentals file is an undated snapshot covering 11 of 101 tickers. What is
# used instead is log trailing median daily turnover, which is fully
# point-in-time and available for every name. It is a LIQUIDITY control that
# correlates with size. It is not log market cap and is never reported as such.

SECTOR_SOURCE = Path(__file__).resolve().parent.parent / "data" / "nifty100_source.csv"
SECTOR_AS_OF = "2026-09-10"
# Below this, a bucket is pooled into "Other". Demeaning a bucket of ONE does
# not weaken that name's signal, it sets it to exactly zero -- which reads as
# "average" and means "alone in its sector". Pooling is not a way of
# neutralising those names properly; it is a way of keeping them in the ranking
# while being honest that they cannot be neutralised.
MIN_SECTOR_BUCKET = 3
SESSIONS_FOR_TURNOVER = E.SESSIONS_52_WEEK


def load_sector_map(path=SECTOR_SOURCE):
    """{ticker: industry} from the NSE constituents file, or {} if absent."""
    if not path.exists():
        return {}
    out = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = (row.get("Symbol") or "").strip()
            industry = (row.get("Industry") or "").strip()
            if symbol and industry:
                out[symbol] = industry
    return out


def trailing_log_turnover(book, ticker, date, sessions=SESSIONS_FOR_TURNOVER):
    """log(median daily close*volume) over the trailing window, or None.

    The median rather than the mean, because a single block trade moves a mean
    by an order of magnitude and this is meant to describe the typical session.
    Only sessions up to and including `date` are read, so it cannot see forward.
    """
    end = book.index_upto(ticker, date)
    if end is None:
        return None
    series = book.history[ticker]
    closes = series["closes"][:end + 1][-sessions:]
    volumes = series["volumes"][:end + 1][-sessions:]
    values = [c * v for c, v in zip(closes, volumes)
              if c is not None and v is not None
              and c == c and v == v and c > 0 and v > 0]
    if len(values) < 2:
        return None
    values.sort()
    middle = len(values) // 2
    median = (values[middle] if len(values) % 2
              else (values[middle - 1] + values[middle]) / 2.0)
    return math.log(median) if median > 0 else None


def sector_buckets(tickers, sectors, floor=MIN_SECTOR_BUCKET):
    """{ticker: bucket}, pooling every industry below `floor` into "Other".

    Applied to the names ELIGIBLE ON THIS DATE, not to the index as a whole: a
    four-name industry can fall to two once the session minimum is applied, and
    a floor enforced against the index would miss it.
    """
    counts = {}
    for ticker in tickers:
        counts[sectors.get(ticker, "Unclassified")] = \
            counts.get(sectors.get(ticker, "Unclassified"), 0) + 1
    return {ticker: (sectors.get(ticker, "Unclassified")
                     if counts[sectors.get(ticker, "Unclassified")] >= floor else "Other")
            for ticker in tickers}


def neutralise(scores, buckets, sizes):
    """Residualise scores on sector dummies and log size, jointly.

    Done as demean-within-bucket, then a univariate regression of the demeaned
    score on the demeaned size. By Frisch-Waugh that residual IS the joint OLS
    residual against sector dummies plus size, so it needs no matrix inversion
    and no second convention to keep in step.

    A name whose size is unavailable keeps its sector-demeaned score: it is
    excluded from the size regression rather than assigned a value.
    """
    tickers = sorted(scores)
    if len(tickers) < 3:
        return dict(scores)
    grouped = {}
    for ticker in tickers:
        grouped.setdefault(buckets.get(ticker, "Other"), []).append(ticker)
    # A bucket of ONE demeans to exactly zero, which reads as "average" and
    # means "alone in its group" -- it does not weaken that name's signal, it
    # deletes it and parks it mid-ranking. Pooling small industries into "Other"
    # handles the common case, but "Other" itself can hold a single name when
    # only one tiny industry is present on a date. Any bucket that cannot
    # support a mean is demeaned against the WHOLE cross-section instead, which
    # keeps the name on the same scale as everyone else and is honest that it
    # was never neutralised.
    global_mean = sum(scores[t] for t in tickers) / len(tickers)
    global_sizes = [sizes[t] for t in tickers if sizes.get(t) is not None]
    global_size_mean = (sum(global_sizes) / len(global_sizes)) if global_sizes else None
    demeaned, demeaned_size = {}, {}
    for members in grouped.values():
        if len(members) < 2:
            for ticker in members:
                demeaned[ticker] = scores[ticker] - global_mean
                demeaned_size[ticker] = (sizes[ticker] - global_size_mean
                                         if global_size_mean is not None
                                         and sizes.get(ticker) is not None else None)
            continue
        mean_score = sum(scores[t] for t in members) / len(members)
        present = [t for t in members if sizes.get(t) is not None]
        mean_size = (sum(sizes[t] for t in present) / len(present)) if present else None
        for ticker in members:
            demeaned[ticker] = scores[ticker] - mean_score
            demeaned_size[ticker] = (sizes[ticker] - mean_size
                                     if mean_size is not None and sizes.get(ticker) is not None
                                     else None)
    paired = [(demeaned_size[t], demeaned[t]) for t in tickers
              if demeaned_size.get(t) is not None]
    if len(paired) < 3:
        return demeaned
    sxx = sum(x * x for x, _y in paired)
    if sxx <= 0:
        return demeaned
    beta = sum(x * y for x, y in paired) / sxx
    return {t: (demeaned[t] - beta * demeaned_size[t]
                if demeaned_size.get(t) is not None else demeaned[t])
            for t in tickers}


def rank_on(book, date, bench_by_date, block=None, rsi_flip=False, continuous=False,
            neutral=False, no_skip_month=False, sectors=None):
    """[(ticker, score)] for every ticker scoreable as at `date`, best first.

    Ties break on ticker ascending, the same rule the screener ranks by, so the
    selection is deterministic rather than dependent on dictionary order.

    block=None ranks on the composite technical total, which is what the
    portfolio trades. Naming one of TECHNICAL_BLOCK_NAMES ranks on that
    subtotal alone, which is how the blocks get measured separately: the
    composite is a weighted sum, and a near-zero result for the sum is
    consistent with one block carrying and another dragging by the same amount.

    continuous=True scores magnitudes instead of thresholds (see
    continuous_scores). Eligibility is decided by the ENGINE in both modes, so
    the two rank the same companies and any difference between them is scoring
    and not universe. ab_compare.py's docstring records what happens when that
    does not hold: a minimum-session rule changed which companies were rankable,
    and the comparison became part scoring and part universe with no way to
    separate them afterwards.
    """
    if continuous:
        entries = []
        points_blocks = {}
        for ticker in book.tickers():
            tech = technicals_on(book, ticker, date, bench_by_date,
                                 no_skip_month=no_skip_month)
            if tech is None:
                continue
            # The gate is the engine's own refusal, not a reimplementation of
            # it. Reimplementing "is this scoreable" is how the two modes drift
            # apart on the universe while both look correct in isolation.
            gate = E.calculate_technical_score(tech, True)
            total = gate[0] if isinstance(gate, tuple) else gate
            if total is None:
                continue
            entries.append((ticker, tech))
            # Kept so the continuous blocks can be rescaled to the spread the
            # points model actually realises, which is what makes the two
            # comparable. See continuous_scores.
            points_blocks[ticker] = gate[3] if isinstance(gate, tuple) and len(gate) > 3 else None
        scored = list(continuous_scores(entries, block=block,
                                        points_blocks=points_blocks).items())
    else:
        scored = []
        for ticker in book.tickers():
            score, blocks = score_on(book, ticker, date, bench_by_date,
                                     rsi_flip=rsi_flip, no_skip_month=no_skip_month)
            if block is not None:
                # A company with no block breakdown cannot be ranked on a block.
                # Dropping it is right: substituting zero would rank "not
                # measured" below every measured company, a claim nobody made.
                score = None if not blocks else blocks.get(block)
            if score is not None:
                scored.append((ticker, score))
    if neutral and scored:
        # Neutralisation is applied to the score being ranked, AFTER the block
        # matching, and the matching is deliberately NOT re-derived here. The
        # matching is what makes rung B comparable to the points model; leaving
        # it fixed is what makes rung C differ from rung B by neutralisation and
        # nothing else. Re-deriving it would partly undo the dispersion change
        # that neutralisation causes, which is the thing being measured.
        # Ranking is invariant to positive rescaling, so no rescale is needed.
        if sectors is None:
            sectors = load_sector_map()
        names = [ticker for ticker, _s in scored]
        scored = list(neutralise(
            dict(scored),
            sector_buckets(names, sectors),
            {ticker: trailing_log_turnover(book, ticker, date) for ticker in names},
        ).items())
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


# --- After tax -------------------------------------------------------------
# Indian capital-gains tax on listed equity, as it stands for this measurement.
# NOT sourced from a feed: the repository holds no tax data, and these are stated
# from knowledge with their statutory references so a reader can check them.
#
#   s.111A  short-term gains on listed equity: 20%, since 23 July 2024
#   s.112A  long-term gains on listed equity: 12.5%, above a Rs 1.25 lakh
#           annual exemption
#   holding period to qualify as long-term: 12 months
#
# THE EXEMPTION IS MODELLED, and an earlier version of this comment got its
# direction exactly backwards. It said ignoring the exemption was "the
# conservative direction" because it overstates long-term tax. That is true and
# it is not conservative, because the conclusion this function feeds is a
# COMPARISON.
#
# Ignoring the exemption taxes long-term gains from the first rupee. The side
# that bears almost all of that is EQUAL WEIGHT, which realises 97.1% of its
# gains long-term; the strategy, at 90-100% short-term, barely feels it. So the
# omission understates equal weight's after-tax return and INFLATES the gap in
# the strategy's favour. It is anti-conservative with respect to the headline.
#
# The old justification carried the same error: "nearly irrelevant here, the
# realised gains are 73-100% short-term" is the STRATEGY's split, cited to excuse
# an omission borne by the other side.
#
# It needs a portfolio size, because Rs 1.25 lakh is an absolute figure against a
# backtest normalised to 1.0. `capital` supplies one. With capital=None the
# exemption is off and the bias above is live -- kept only so the old figures can
# be reproduced, never as a default for a published comparison.
STCG_RATE = 0.20
LTCG_RATE = 0.125
LONG_TERM_MONTHS = 12
LTCG_EXEMPTION_RUPEES = 125000.0


def _financial_year(date):
    """The Indian financial year a date falls in, labelled by its April."""
    parsed = datetime.date.fromisoformat(date)
    return parsed.year if parsed.month >= 4 else parsed.year - 1


def _months_held(since, until):
    """Whole months between two ISO dates, the s.2(42A) holding-period test."""
    start = datetime.date.fromisoformat(since)
    end = datetime.date.fromisoformat(until)
    months = (end.year - start.year) * 12 + (end.month - start.month)
    return months - (1 if end.day < start.day else 0)


def after_tax_performance(book, periods, stcg_rate=STCG_RATE, ltcg_rate=LTCG_RATE,
                          cost_bps_per_side=DEFAULT_COST_BPS_PER_SIDE,
                          long_term_months=LONG_TERM_MONTHS, capital=None):
    """Compound the portfolio with lots tracked, and tax every realised gain.

    Why a lot-tracking simulation rather than a turnover approximation: the
    question is whether a 1-month signal survives tax, and that turns entirely on
    WHEN each position is sold relative to the 12-month line. A turnover-based
    estimate cannot see the line at all.

    Two simplifications, both stated because both flatter the strategy slightly:

    1. Tax is charged at realisation, not at the financial-year end. That removes
       the within-year deferral benefit and so OVERSTATES the drag a little --
       the conservative direction.
    2. Adding to an existing position keeps the original acquisition date rather
       than opening a FIFO lot. That makes long-term treatment slightly MORE
       likely than the statute allows, which flatters the strategy. The realised
       short/long split is reported so the size of the error is visible; when the
       split is overwhelmingly short, both simplifications are immaterial.

    Costs are charged on traded value at the same rate the pre-tax backtest uses,
    so the two are comparable.
    """
    if not periods:
        return {}
    rate = cost_bps_per_side / 10000.0
    positions = {}          # ticker -> [units, cost basis, acquisition date]
    cash = 1.0
    # The exemption in NORMALISED units: a fixed rupee amount against a book that
    # starts at `capital`, so its relative weight shrinks as the portfolio grows,
    # which is the real behaviour.
    exemption_unit = (LTCG_EXEMPTION_RUPEES / capital) if capital else 0.0
    exempt_left = {}
    exempt_used = 0.0
    taxed = {"short": 0.0, "long": 0.0}
    tax_paid = 0.0
    costs_paid = 0.0

    def prices_at(date, names):
        out = {}
        for ticker in names:
            price, _fallback = book.execution_price(ticker, date)
            if price and price > 0:
                out[ticker] = price
        return out

    for period in periods:
        entry = period["entry_date"]
        names = [t for t in period["holdings"]]
        price = prices_at(entry, set(list(positions) + names))
        held_value = sum(units * price[t] for t, (units, _c, _s) in positions.items()
                         if t in price)
        total = cash + held_value
        target = total / len(names) if names else 0.0

        # Sell down or out first, so the tax is known before anything is bought.
        for ticker in list(positions):
            if ticker not in price:
                continue
            units, basis, since = positions[ticker]
            wanted = (target / price[ticker]) if ticker in names else 0.0
            if wanted >= units:
                continue
            sold = units - wanted
            share = sold / units
            proceeds = sold * price[ticker]
            gain = proceeds - basis * share
            bucket = "long" if _months_held(since, entry) >= long_term_months else "short"
            taxed[bucket] += gain
            taxable = gain
            if bucket == "long" and exemption_unit > 0 and gain > 0:
                # s.112A exempts the first Rs 1.25 lakh of long-term gain in a
                # financial year, in aggregate. Consuming it first-come-first-
                # served within the year is equivalent to applying it to the
                # total, and a loss must not consume it.
                year = _financial_year(entry)
                left = exempt_left.setdefault(year, exemption_unit)
                used = min(gain, left)
                exempt_left[year] = left - used
                exempt_used += used
                taxable = gain - used
            tax = taxable * (ltcg_rate if bucket == "long" else stcg_rate)
            # A loss offsets at the same rate: real relief needs other gains to
            # set against, and at this turnover there are always plenty.
            tax_paid += tax
            cost = proceeds * rate
            costs_paid += cost
            cash += proceeds - cost - tax
            basis -= basis * share
            if wanted <= 0:
                del positions[ticker]
            else:
                positions[ticker] = [wanted, basis, since]

        # Then buy toward the target with whatever is left.
        for ticker in names:
            if ticker not in price:
                continue
            units, basis, since = positions.get(ticker, [0.0, 0.0, entry])
            wanted = target / price[ticker]
            if wanted <= units:
                continue
            spend = (wanted - units) * price[ticker]
            cost = spend * rate
            costs_paid += cost
            cash -= spend + cost
            positions[ticker] = [wanted, basis + spend, since]

    # Mark to market at the last exit, WITHOUT taxing the unrealised gain: the
    # comparison is between strategies that both end holding something, and
    # taxing one terminal book and not the other would be the same one-sided
    # error as comparing after-tax to pre-tax.
    final = periods[-1]["exit_date"]
    price = prices_at(final, list(positions))
    value = cash + sum(units * price[t] for t, (units, _c, _s) in positions.items()
                       if t in price)
    # Years from the ACTUAL dates, not from len(periods)/12. The period count is
    # only a month count when the rebalance interval is monthly; on a quarterly
    # schedule len(periods)/12 understates the span threefold and reported a
    # 95% CAGR where the truth is nearer 24%. The absurd figure was the tell.
    span_days = ((datetime.date.fromisoformat(periods[-1]["exit_date"])
                  - datetime.date.fromisoformat(periods[0]["entry_date"])).days)
    years = span_days / 365.25
    cagr = value ** (1.0 / years) - 1.0 if years > 0 and value > 0 else float("nan")
    realised = taxed["short"] + taxed["long"]
    return {
        "final_value": value,
        "cagr": cagr,
        "months": len(periods),
        "years": years,
        "tax_paid": tax_paid,
        "costs_paid": costs_paid,
        "realised_short": taxed["short"],
        "realised_long": taxed["long"],
        "short_share": (taxed["short"] / realised) if realised else float("nan"),
        "capital": capital,
        "exempt_used": exempt_used,
        "stcg_rate": stcg_rate,
        "ltcg_rate": ltcg_rate,
    }


def buffered_selection(ranked, held, top_n, buffer_multiple):
    """Top-N, but a held name is only sold once it leaves the top N*multiple.

    Rank buffering is the standard turnover brake: a name sitting at rank 21 of 20
    is not meaningfully worse than one at rank 20, and swapping them every month
    pays two spreads and a tax bill for noise. With multiple=2 a holding survives
    until it falls out of the top 40.

    Survivors keep their rank order and fill the book first; the remaining slots
    go to the best-ranked names not already held. Both halves are ordered by the
    ranking, so the result is deterministic.
    """
    if buffer_multiple <= 1:
        return [ticker for ticker, _score in ranked[:top_n]]
    order = {ticker: index for index, (ticker, _score) in enumerate(ranked)}
    window = {ticker for ticker, _score in ranked[:top_n * buffer_multiple]}
    selected = sorted((t for t in held if t in window), key=lambda t: order[t])[:top_n]
    for ticker, _score in ranked:
        if len(selected) >= top_n:
            break
        if ticker not in selected:
            selected.append(ticker)
    return selected


def run_portfolio(book, calendar, rebalances, bench_by_date, top_n, cost_bps_per_side,
                  rsi_flip=False, continuous=False, neutral=False, no_skip_month=False,
                  sectors=None, buffer_multiple=1, portfolio_block=None, invert=False):
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
        ranked = rank_on(book, signal_date, bench_by_date, block=portfolio_block,
                         rsi_flip=rsi_flip, continuous=continuous, neutral=neutral,
                         no_skip_month=no_skip_month, sectors=sectors)
        # invert holds the WORST-ranked names. It exists so the pre-registered
        # momentum reversal can be traded and measured rather than described:
        # the hypothesis is that low momentum outperforms, and a top-N portfolio
        # cannot express that.
        if invert:
            ranked = list(reversed(ranked))
        selected = buffered_selection(ranked, held, top_n, buffer_multiple)
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
            "entered": [t for t in selected if t not in held],
            "exited": [t for t in held if t not in selected],
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


def align_to(records, reference):
    """Keep only the periods the reference series also traded.

    The strategy cannot trade until enough companies clear the minimum-session
    rule; equal-weighting can trade from the first month in the file. So the two
    series are not the same length -- 86 months against 95 on the pre-holdout
    span -- and a table printing one beside the other is not a comparison, it is
    two measurements of different windows sharing a header.

    That is not hypothetical. The whole-period table showed 19.41% against
    20.17%, inviting the subtraction -0.77pp, while the paired figure underneath
    it read -3.89pp: two answers to one question, five-fold apart, with the wrong
    one in the larger type. Cutting the benchmarks to the strategy's months makes
    the table's own subtraction equal the paired figure instead of contradicting
    it.
    """
    dates = {r["signal_date"] for r in reference}
    return [r for r in records if r["signal_date"] in dates]


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


def _percentile_index(quantile, count):
    """Index of the nearest-rank percentile in a sorted list of `count` values."""
    return max(0, min(count - 1, math.ceil(quantile * count) - 1))


def _stationary_bootstrap_se(series, mean_block, draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED):
    """(standard error, 2.5th pct, 97.5th pct) by the Politis-Romano bootstrap.

    A third, independent estimate. It was introduced as a CONSERVATIVE check on
    HAC, on the reasoning that HAC is undersized in small samples. **That claim
    was false as configured and has been withdrawn.** Across the 15 overlapping
    cells of the pre-holdout run the bootstrap SE is SMALLER than the HAC SE in
    10 of them, including every high-dependence cell, so it was systematically
    the LESS conservative of the two -- the opposite of what it was here to do.

    Both are biased the same way, and badly. Scored against a series whose true
    standard error is known -- a moving average of h shocks, which is exactly
    the structure an overlapping h-window IC series has -- every estimator
    understates it (4,000 replications, n matching the real study):

        h=6,  n=81:  i.i.d. -61%,  HAC(lag 5) -22%,  bootstrap(block 6) -25%
        h=12, n=75:  i.i.d. -74%,  HAC(lag 11) -29%, bootstrap(block 12) -38%
        h=3,  n=84:  i.i.d. -44%,  HAC(lag 2) -17%,  bootstrap(block 3) -20%

    Lengthening the block makes the bootstrap WORSE, not better: at h=6 blocks
    of 12 and 18 give -29% and -32%. With n around 80 a long block makes the
    resampled paths too alike, so the draws under-disperse. There is no block
    length that fixes it.

    Nor is there a Bartlett bandwidth that fixes HAC. Sweeping lag from h-1 to
    4h, the best attainable is -17.5% at h=6 (lag 11), -28% at h=12 (lag 18) and
    -10.6% at h=3 (lag 6); beyond that the bias grows again. The bandwidth is
    left at h-1 because a few points of a twenty-point bias is not worth
    re-opening every published figure for, and because the honest statement is
    not "we found the right bandwidth" but "these standard errors understate".

    SO READ EVERY t IN THIS FILE AS INFLATED, by roughly a quarter to a third at
    the longer horizons. That direction is unhelpful for any positive finding
    and harmless for a null, which is the whole of what this study reports.

    The stationary bootstrap resamples blocks whose lengths are geometric with
    mean `mean_block`, wrapping circularly, which preserves serial dependence up
    to roughly that length while keeping the resampled series stationary. Fixed
    blocks would not be stationary; a plain i.i.d. bootstrap would destroy the
    dependence this is trying to respect.

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
    # Nearest-rank percentile: the qth percentile of n sorted values is at index
    # ceil(q*n) - 1, not int(q*n). At draws=2000 the old form took index 50 and
    # 1950 where the 2.5th and 97.5th are 49 and 1949 -- both off by one rank,
    # a sub-percentile error but a wrong one in both tails.
    lo = means[_percentile_index(0.025, draws)]
    hi = means[_percentile_index(0.975, draws)]
    return math.sqrt(variance), lo, hi


def cagr_difference_ci(strategy_periods, benchmark_periods, mean_block=6,
                       draws=BOOTSTRAP_DRAWS, seed=BOOTSTRAP_SEED):
    """Bootstrap interval for strategy CAGR minus benchmark CAGR.

    The headline comparison in this file -- 20.40% against 21.15% -- has carried
    no error bar at all. Three quarters of a percentage point over eleven years
    is very plausibly noise, and stating it without an interval invites reading
    a coin-flip as a finding in either direction.

    Two things this gets right that a naive bootstrap would not:

    Months are resampled JOINTLY as (strategy, benchmark) pairs. The two series
    hold overlapping names in the same market and move together; resampling them
    independently would destroy that contemporaneous correlation and inflate the
    interval to uselessness. What is being estimated is the difference, so the
    pairing is the whole point.

    CAGR is recomputed by compounding each resampled path, not differenced as a
    mean. It is a nonlinear function of the path, so the difference of means is
    not the mean of differences, and a bootstrap of monthly means would answer a
    different question from the one the table asks.

    Periods are aligned on signal_date rather than by index: the strategy series
    is shorter than the equal-weight one (it needs a scoreable universe), and
    zipping them positionally would silently compare different months.
    """
    by_date = {p["signal_date"]: p["net_return"] for p in benchmark_periods}
    pairs = [(p["net_return"], by_date[p["signal_date"]])
             for p in strategy_periods if p["signal_date"] in by_date]
    n = len(pairs)
    if n < 12:
        return {"months": n, "difference": float("nan"), "ci_lo": float("nan"),
                "ci_hi": float("nan"), "p_value": float("nan"),
                "excludes_zero": False, "draws": 0}

    def cagr(returns):
        value = 1.0
        for r in returns:
            value *= 1.0 + r
        years = len(returns) / float(MONTHS_PER_YEAR)
        return value ** (1.0 / years) - 1.0 if years > 0 and value > 0 else float("nan")

    observed = cagr([a for a, _ in pairs]) - cagr([b for _, b in pairs])
    rng = random.Random(seed)
    p_restart = 1.0 / mean_block
    diffs = []
    for _ in range(draws):
        strat, bench = [], []
        index = rng.randrange(n)
        for _step in range(n):
            a, b = pairs[index]
            strat.append(a)
            bench.append(b)
            index = rng.randrange(n) if rng.random() < p_restart else (index + 1) % n
        d = cagr(strat) - cagr(bench)
        if d == d:
            diffs.append(d)
    if len(diffs) < 100:
        return {"months": n, "difference": observed, "ci_lo": float("nan"),
                "ci_hi": float("nan"), "p_value": float("nan"),
                "excludes_zero": False, "draws": len(diffs)}
    diffs.sort()
    lo = diffs[int(0.025 * len(diffs))]
    hi = diffs[min(len(diffs) - 1, int(0.975 * len(diffs)))]
    # Two-sided bootstrap p as 2 * min(P(d <= 0), P(d >= 0)), capped at 1.
    #
    # The earlier form counted resamples "on the other side of zero from the
    # observed difference" using strict > 0, which sorted exactly-zero into the
    # negative bucket. Two identical return series then reported p 0.000 and an
    # interval excluding zero -- the strongest possible claim of a difference,
    # for series with no difference at all. Ties have to count on both sides.
    at_or_below = sum(1 for d in diffs if d <= 0)
    at_or_above = sum(1 for d in diffs if d >= 0)
    p_value = min(1.0, 2.0 * min(at_or_below, at_or_above) / len(diffs))
    return {
        "months": n,
        "difference": observed,
        "ci_lo": lo,
        "ci_hi": hi,
        "p_value": p_value,
        # An interval containing zero does not exclude it, including the
        # degenerate case where both bounds ARE zero.
        "excludes_zero": (lo > 0 and hi > 0) or (lo < 0 and hi < 0),
        "draws": len(diffs),
        "mean_block": mean_block,
    }


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
    # Degrees of freedom for a HAC t are NOT n-1. n-1 is the df of an i.i.d.
    # mean; on overlapping windows consecutive observations share (h-1)/h of
    # their span, so the independent information is about n/h. Referring a HAC t
    # to df = n-1 over-rejects, and this file already argues the point against
    # itself: two_sided_p's docstring defends Student's t over the normal
    # because "at df=9 the critical t is 2.262 rather than 1.96 -- that
    # difference decides significance", and the same file then handed the HAC
    # statistic df=80 where the independent count is 12.
    #
    # n // h reproduces the non-overlapping series length EXACTLY at every
    # horizon this study measures -- 84//3=28, 81//6=13, 75//12=6 -- so it is a
    # count the run already computes rather than a new estimate to defend.
    #
    # This is a CONSERVATIVE PROXY, not the textbook fix. The rigorous treatment
    # is fixed-b asymptotics (Kiefer & Vogelsang 2005), under which a HAC t has
    # a nonstandard limiting distribution with fatter tails than Student's t at
    # any df. The honest p therefore sits ABOVE the one computed here, and
    # df = n_eff - 1 is still anti-conservative relative to the correct answer.
    # It is adopted because it uses a number already in the study and so cannot
    # be argued downward once a cell turns out to depend on it.
    horizon = hac_lag + 1
    effective_n = n if horizon <= 1 else max(2, n // horizon)
    hac_df = max(1, effective_n - 1)
    hac_p = two_sided_p(hac_t, hac_df)
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
    #
    # The floor must use the SAME standard error as the t-statistic it is read
    # beside, and for an overlapping series that is the HAC one. Tier 0 moved
    # the t to Newey-West and left this figure on the i.i.d. SE, which is the
    # estimator Tier 0 exists to say is invalid here. The cost was not small:
    # at 6 months the published floor read 0.0478 where the honest figure is
    # 0.0607, understating it by 27%.
    #
    # The direction matters more than the size. An understated floor makes the
    # test look better powered than it is, which makes a null look more
    # conclusive than it is -- the same error as the "powered null" overclaim
    # this very figure was added to prevent. A number that guards against an
    # overclaim is worth checking for the overclaim it guards against.
    # The floor takes the same standard error AND the same degrees of freedom as
    # the t-statistic it is read beside. Pairing a HAC standard error with an
    # i.i.d. df would understate the critical value and so understate the floor,
    # which is the same anti-conservative direction as the df defect above.
    inference_se = hac_se if hac_lag > 0 else (spread / math.sqrt(n) if n > 0 else float("nan"))
    inference_df = hac_df if hac_lag > 0 else max(1, n - 1)
    detectable = ((_t_critical(inference_df) + Z_FOR_80_PERCENT_POWER) * inference_se) \
        if n > 1 and inference_se == inference_se and inference_se > 0 else float("nan")
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
        # Reported so a reader can see which df the p was referred to. It is the
        # single figure most able to move a cell across a significance line, and
        # it was wrong here for the life of the project.
        "hac_effective_n": effective_n,
        "hac_df": hac_df,
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


def _phase_averaged_statistics(phases, family_size):
    """Non-overlapping IC statistics using EVERY phase, not an arbitrary one.

    At horizon h there are h valid non-overlapping series -- windows starting at
    month 0, h, 2h..., or at 1, h+1..., and so on. The study used to keep phase 0
    alone, which threw away (h-1)/h of the observations and made the column
    depend on which month the price file happened to begin in. At h=12 that meant
    6 windows out of 75.

    THE POINT ESTIMATE IS AVERAGED; THE STANDARD ERROR IS NOT REDUCED. Averaging
    the h phase means uses every observation and removes the arbitrary choice. It
    does NOT buy a sqrt(h) improvement in precision, because the phases are not
    independent OF EACH OTHER: phase 0's first window spans months 0..h and phase
    1's spans 1..h+1, sharing h-1 of them. Dividing the standard error by sqrt(h)
    would assume an independence that does not hold and would understate it --
    the direction this project keeps having to correct.

    So the reported standard error is the average of the per-phase standard
    errors, each honestly derived from its own phase's independent observations.
    That is conservative: the true SE of the averaged mean lies below it and
    above SE/sqrt(h), and the overlapping column with a HAC standard error is the
    estimate to read when precision matters.
    """
    if not phases:
        return _ic_statistics([], family_size, hac_lag=0)
    per_phase = [_ic_statistics(series, family_size, hac_lag=0)
                 for _key, series in sorted(phases.items()) if len(series) > 1]
    if not per_phase:
        return _ic_statistics(max(phases.values(), key=len), family_size, hac_lag=0)
    count = len(per_phase)
    mean_ic = sum(p["mean_ic"] for p in per_phase) / count
    observations = sum(p["ic_periods"] for p in per_phase)
    spreads = [p["ic_sd"] / math.sqrt(p["ic_periods"]) for p in per_phase
               if p["ic_sd"] == p["ic_sd"] and p["ic_periods"] > 0]
    standard_error = (sum(spreads) / len(spreads)) if spreads else float("nan")
    # df from ONE phase's length, not the pooled count, for the same reason the
    # standard error is not divided by sqrt(h).
    typical = sum(p["ic_periods"] for p in per_phase) / count
    df = max(1, int(typical) - 1)
    t_stat = (mean_ic / standard_error) \
        if standard_error == standard_error and standard_error > 0 else float("nan")
    p_value = two_sided_p(t_stat, df)
    detectable = ((_t_critical(df) + Z_FOR_80_PERCENT_POWER) * standard_error) \
        if standard_error == standard_error and standard_error > 0 else float("nan")
    merged = dict(per_phase[0])
    merged.update({
        "mean_ic": mean_ic,
        "ic_periods": observations,
        "ic_t_stat": t_stat,
        "ic_p_value": p_value,
        "ic_p_bonferroni": bonferroni(p_value, family_size),
        "detectable_ic_80pct": detectable,
        "phases_averaged": count,
        "phase_periods": typical,
    })
    return merged


def decile_study(book, calendar, rebalances, bench_by_date, horizons=DECILE_HORIZONS,
                 block=None, family_size=None, rsi_flip=False, continuous=False,
                 neutral=False, no_skip_month=False, sectors=None):
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
    ics = {h: {"overlapping": [], "phases": {}} for h in horizons}
    for index, signal_date in enumerate(rebalances):
        entry_date = next_session(calendar, signal_date)
        if entry_date is None:
            continue
        ranked = rank_on(book, signal_date, bench_by_date, block=block, rsi_flip=rsi_flip,
                         continuous=continuous, neutral=neutral,
                         no_skip_month=no_skip_month, sectors=sectors)
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
            # EVERY phase, not just phase 0. There are h valid non-overlapping
            # series at horizon h; keeping only `index % horizon == 0` threw away
            # h-1 of them and made the column depend on which month the price
            # file happened to begin in.
            ics[horizon]["phases"].setdefault(index % horizon, []).append(ic)
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
        non_overlapping = _phase_averaged_statistics(ics[horizon]["phases"], family_size)
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
        # Named from the data, not from a constant. The previous heading read
        # "Out of sample (2022 on)" and was true until HOLDOUT_START landed
        # between OUT_OF_SAMPLE_START and the end of the file, after which that
        # block held a single calendar year and the heading promised years.
        span = block.get("span")
        title = {"full": "Whole period", "in_sample": "In sample",
                 "out_of_sample": "Out of sample"}[label]
        if span:
            out.append("## %s: %s to %s (%d rebalances)" % (title, span[0], span[1], span[2]))
        else:
            out.append("## %s (no rebalances)" % title)
        out.append("")
        if span and span[2] < MONTHS_PER_YEAR * 2:
            # A block this short produces a CAGR by annualising a handful of
            # months, which is arithmetic rather than evidence. Under the
            # holdout, out_of_sample collapsed to eleven months and reported a
            # 14.88 point advantage -- the most quotable figure in the report
            # and among the least meaningful.
            out.append("> **Too short to interpret: %d rebalances.** The CAGR below "
                       "annualises under two years, and the gap against equal weight "
                       "is dominated by which months happened to fall inside it. "
                       "Quote the whole-period figures instead." % span[2])
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
        gap = block.get("cagr_vs_equal_weight") or {}
        if gap.get("draws"):
            verdict = ("**excludes zero**" if gap["excludes_zero"]
                       else "**straddles zero — consistent with no difference**")
            out.append("CAGR against equal weight: **%s** "
                       "(95%% bootstrap CI %s to %s, p %.3f, %d paired months, "
                       "%d draws). %s"
                       % (pct(gap["difference"]), pct(gap["ci_lo"]), pct(gap["ci_hi"]),
                          gap["p_value"], gap["months"], gap["draws"], verdict))
            out.append("")
            out.append("Months are resampled jointly as (strategy, equal-weight) pairs so "
                       "the contemporaneous correlation between them survives, and each "
                       "resampled path is compounded rather than averaged, because CAGR is "
                       "a function of the path and not a mean.")
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


def _after_tax_block(book, periods, cost_bps_per_side, stcg_rate, capital):
    """After-tax figures for the strategy and for equal weight, side by side.

    EQUAL WEIGHT IS BUILT ON THE STRATEGY'S OWN PERIODS, which is the whole of
    what makes this a comparison. The first version of this function walked the
    full rebalance calendar and so taxed a 95-month equal-weight book against an
    86-month strategy, differencing a 7.17-year CAGR against a 7.92-year one.
    That is the benchmark-alignment defect c96780d fixed for the performance
    table, reintroduced here because this code path never went through
    align_to().

    Truncating the OUTPUT would not have fixed it. Equal weight would still have
    acquired lots in the nine dropped months, so its realised short/long split
    and its exemption consumption would have been wrong in a new way. It has to
    START where the strategy starts, which is what using the strategy's periods
    guarantees: same months, same entry and exit dates, same lot history window.
    """
    if not periods:
        return {}
    everything = book.tickers()
    equal_with_holdings = [{
        "signal_date": period["signal_date"],
        "entry_date": period["entry_date"],
        "exit_date": period["exit_date"],
        "holdings": list(everything),
    } for period in periods]
    strategy = after_tax_performance(book, periods, stcg_rate=stcg_rate,
                                     cost_bps_per_side=cost_bps_per_side, capital=capital)
    benchmark = after_tax_performance(book, equal_with_holdings, stcg_rate=stcg_rate,
                                      cost_bps_per_side=cost_bps_per_side, capital=capital)
    gap = (strategy.get("cagr", float("nan")) - benchmark.get("cagr", float("nan")))
    return {
        "strategy": strategy,
        "equal_weight": benchmark,
        "gap": gap,
        "stcg_rate": stcg_rate,
        "ltcg_rate": LTCG_RATE,
        "capital": capital,
        "exemption_modelled": bool(capital),
    }


# --- Orchestration ---------------------------------------------------------
def backtest(history, top_n=DEFAULT_TOP_N, cost_bps_per_side=DEFAULT_COST_BPS_PER_SIDE,
             variants_tried=1, variants_note="", rsi_flip=False, respect_holdout=True,
             continuous=False, neutral=False, no_skip_month=False, buffer_multiple=1,
             stcg_rate=STCG_RATE, capital=None, portfolio_block=None, invert=False):
    book = PriceBook(history)
    calendar = market_calendar(history)
    rebalances = month_end_sessions(calendar, respect_holdout=respect_holdout)
    bench = history[E.BENCHMARK_SYMBOL]
    bench_by_date = dict(zip(bench["dates"], bench["closes"]))

    # Read once per run, not once per rebalance: rank_on would otherwise reopen
    # the constituents file 87 times.
    sectors = load_sector_map() if neutral else None
    if neutral and not sectors:
        raise SystemExit(
            "--neutral needs %s, which is missing. Neutralising on an empty sector "
            "map would silently demean every name against one bucket, which is a "
            "no-op wearing the name of a treatment." % SECTOR_SOURCE)
    periods = run_portfolio(book, calendar, rebalances, bench_by_date, top_n, cost_bps_per_side,
                            rsi_flip=rsi_flip, continuous=continuous, neutral=neutral,
                            no_skip_month=no_skip_month, sectors=sectors,
                            buffer_multiple=buffer_multiple,
                            portfolio_block=portfolio_block, invert=invert)
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
                           rsi_flip=rsi_flip, continuous=continuous, neutral=neutral,
                           no_skip_month=no_skip_month, sectors=sectors)
    block_deciles = {
        name: decile_study(book, calendar, rebalances, bench_by_date,
                           block=name, family_size=family, rsi_flip=rsi_flip,
                           continuous=continuous, neutral=neutral,
                           no_skip_month=no_skip_month, sectors=sectors)
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
        chosen = chooser(periods)
        blocks[label] = {
            "strategy": performance(chosen),
            # Both benchmarks are cut to the months the strategy actually traded,
            # so every column in the table covers the span its heading names and
            # subtracting two of them answers the question it appears to answer.
            # See align_to().
            "equal_weight": performance(align_to(chooser(equal), chosen)),
            "index": performance(align_to(chooser(index), chosen)),
            # The span this block actually covers, so the report can name it
            # rather than assert a hardcoded one. "Out of sample (2022 on)" was
            # true when the file ended in 2026 and became false the moment the
            # holdout cut landed, leaving a heading that promised years over a
            # block containing one. A label derived from the data cannot go
            # stale when a boundary moves.
            "span": ((chosen[0]["signal_date"], chosen[-1]["signal_date"], len(chosen))
                     if chosen else None),
            # The CAGR gap with an interval around it. Without one, a 0.75-point
            # difference over eleven years reads as a result rather than as the
            # coin-flip it probably is.
            "cagr_vs_equal_weight": cagr_difference_ci(chosen, chooser(equal)),
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
            # Aligned for the same reason as the performance table: an unaligned
            # first year gives the benchmarks months the strategy never had, and
            # the yearly rows are read as a win/loss tally.
            "equal_weight": yearly_returns(align_to(equal, periods)),
            "index": yearly_returns(align_to(index, periods)),
        },
        "turnover": (sum(turnovers) / len(turnovers) * MONTHS_PER_YEAR) if turnovers else 0.0,
        "buffer_multiple": buffer_multiple,
        "portfolio_block": portfolio_block,
        "inverted": invert,
        # After tax, BOTH SIDES, written to the artefact so the headline
        # re-derives rather than living in a commit message. The equal-weight
        # book is run through the same simulator: taxing one side is not a
        # comparison.
        "after_tax": _after_tax_block(book, periods, cost_bps_per_side,
                                      stcg_rate, capital),
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
        # respect_holdout=False because this test is about month-end detection,
        # not holdout policy. The fixture sits entirely inside the reserved
        # window, so the default cut would empty it and the assertion below
        # would be comparing two empty lists -- passing while testing nothing.
        # The cut itself is covered by its own test.
        ends = month_end_sessions(dates, respect_holdout=False)
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

    def test_continuous_mode_ranks_the_same_names_in_a_different_order(self):
        # Two things must hold and only one is obvious.
        #
        # The flag must REACH the ranking: a parameter that is accepted and
        # never used passes every grep ever written, which is why this asserts
        # on behaviour rather than on the signature.
        #
        # And both modes must rank the SAME COMPANIES. ab_compare.py's docstring
        # records the alternative: a minimum-session rule changed which names
        # were rankable, so a comparison became part scoring and part universe
        # with no way to separate them after the fact. A continuous score that
        # quietly admits or drops names would reproduce that exactly, and the
        # IC difference would be uninterpretable while looking fine.
        dates = self._business_days(420, start="2018-01-01")
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
        bench = dict(zip(dates, history[E.BENCHMARK_SYMBOL]["closes"]))
        date = month_end_sessions(calendar)[-1]

        points = rank_on(book, date, bench)
        continuous = rank_on(book, date, bench, continuous=True)
        # Guard before asserting: on an empty or single-name ranking every
        # comparison below passes while proving nothing.
        self.assertGreater(len(points), 9)
        self.assertEqual(sorted(t for t, _s in points),
                         sorted(t for t, _s in continuous),
                         "the two modes must score the same universe")
        self.assertNotEqual([t for t, _s in points], [t for t, _s in continuous],
                            "continuous scoring did not change the order")
        # The points model ties heavily -- that is the defect being measured --
        # so the continuous score must be strictly more discriminating, not just
        # different. Equal-valued scores cannot order anything.
        self.assertGreater(len({s for _t, s in continuous}),
                           len({s for _t, s in points}))

    def test_continuous_blocks_are_scored_separately(self):
        # Each block must be reachable on its own, as it is for the points
        # model, or the per-block table cannot be produced for this variant.
        dates = self._business_days(420, start="2018-01-01")
        history = {}
        for k in range(12):
            history["T%02d" % k] = self._series(
                dates, [100.0 + math.cos(i / (5.0 + k)) * 7.0 + i * (0.05 if k % 3 else -0.03)
                        for i in range(len(dates))])
        history[E.BENCHMARK_SYMBOL] = self._series(
            dates, [1000.0 + i * 0.06 for i in range(len(dates))])
        book = PriceBook(history)
        calendar = market_calendar(history)
        bench = dict(zip(dates, history[E.BENCHMARK_SYMBOL]["closes"]))
        date = month_end_sessions(calendar)[-1]
        composite = rank_on(book, date, bench, continuous=True)
        self.assertGreater(len(composite), 9)
        orders = {}
        for name in E.TECHNICAL_BLOCK_MAX:
            ranked = rank_on(book, date, bench, block=name, continuous=True)
            self.assertEqual(sorted(t for t, _s in ranked),
                             sorted(t for t, _s in composite),
                             "block %s ranked a different universe" % name)
            orders[name] = tuple(t for t, _s in ranked)
        # The universe check alone is VACUOUS and was: it passed for a whole
        # revision in which `block` was shadowed by the feature loop variable,
        # so every block returned the volume subtotal. Same universe, same
        # order, same numbers, four different names. Asserting the blocks
        # actually differ from each other is what catches that.
        self.assertEqual(len(orders), len(E.TECHNICAL_BLOCK_MAX))
        self.assertGreater(len(set(orders.values())), 1,
                           "every block produced an identical ranking")

    def test_continuous_blocks_carry_the_points_model_spread(self):
        # What a block contributes to a ranking is its cross-sectional SPREAD,
        # not its nominal cap. Neither mode realises 40:30:20:10 -- over 87 real
        # dates the points model realises 36.1/32.0/22.7/9.2 and the unmatched
        # continuous form 38.2/32.1/21.3/8.4, because a block's SD depends on the
        # correlation among its own features and trend's five are near-collinear
        # while volume's two are not. Left unmatched, an IC difference between
        # the modes is part thresholding and part reweighting.
        dates = self._business_days(420, start="2018-01-01")
        history = {}
        for k in range(14):
            history["T%02d" % k] = self._series(
                dates, [100.0 + math.sin(i / (6.0 + k)) * 9.0 + i * (0.06 if k % 2 else -0.04)
                        for i in range(len(dates))])
        history[E.BENCHMARK_SYMBOL] = self._series(
            dates, [1000.0 + i * 0.08 for i in range(len(dates))])
        book = PriceBook(history)
        calendar = market_calendar(history)
        bench = dict(zip(dates, history[E.BENCHMARK_SYMBOL]["closes"]))
        date = month_end_sessions(calendar)[-1]

        entries, points_blocks = [], {}
        for ticker in book.tickers():
            tech = technicals_on(book, ticker, date, bench)
            if tech is None:
                continue
            gate = E.calculate_technical_score(tech, True)
            if (gate[0] if isinstance(gate, tuple) else gate) is None:
                continue
            entries.append((ticker, tech))
            points_blocks[ticker] = gate[3] if len(gate) > 3 else None
        self.assertGreater(len(entries), 9)

        for name in E.TECHNICAL_BLOCK_MAX:
            target = _population_sd([points_blocks[t][name] for t, _tech in entries])
            # Guard: a block with no spread in the points model cannot be matched
            # and would make the assertion below vacuous.
            self.assertGreater(target, 0.0, "points block %s has no spread" % name)
            got = continuous_scores(entries, block=name, points_blocks=points_blocks)
            self.assertAlmostEqual(_population_sd([got[t] for t, _tech in entries]),
                                   target, places=9,
                                   msg="block %s does not carry the points spread" % name)
            # Matching the spread must not flatten the ordering -- if it did, the
            # blocks would agree on spread and carry no information.
            self.assertGreater(len({round(v, 9) for v in got.values()}), 1)

    def test_the_engine_skips_the_month_and_the_flag_restores_it(self):
        # The ENGINE now measures t-h to t-2 by default (CFA rf-v2016-n4-1#71).
        # --no-skip-month restores t-h to t-1 so the change stays measurable.
        # The START stays anchored and only the END moves; shifting the whole
        # window would give t-13 to t-1, a different quantity. Both windows are
        # checked against values computed by hand from the series.
        dates = self._business_days(400, start="2018-01-01")
        prices = [100.0 + i * 0.3 + math.sin(i / 11.0) * 6.0 for i in range(len(dates))]
        bench = [1000.0 + i * 0.2 for i in range(len(dates))]
        history = {"AAA": self._series(dates, prices),
                   E.BENCHMARK_SYMBOL: self._series(dates, bench)}
        book = PriceBook(history)
        bench_by_date = dict(zip(dates, bench))
        date = dates[-1]

        shipped = technicals_on(book, "AAA", date, bench_by_date)
        restored = technicals_on(book, "AAA", date, bench_by_date, no_skip_month=True)
        skip = E.RELATIVE_STRENGTH_SKIP_SESSIONS
        self.assertEqual(skip, E.SESSIONS_1_MONTH)

        for key, sessions in (("relativeStrength3M", E.SESSIONS_3_MONTH),
                              ("relativeStrength6M", E.SESSIONS_6_MONTH),
                              ("relativeStrength12M", E.SESSIONS_12_MONTH)):
            # The window the engine uses: start at -sessions, end at -1.
            start_price, start_bench = prices[-sessions], bench[-sessions]
            expected_plain = ((prices[-1] - start_price) / start_price
                              - (bench[-1] - start_bench) / start_bench) * 100.0
            # The skip-month window: same start, end one month earlier.
            expected_skip = ((prices[-1 - skip] - start_price) / start_price
                             - (bench[-1 - skip] - start_bench) / start_bench) * 100.0
            # Shipped behaviour is now the SKIPPED window.
            self.assertAlmostEqual(shipped[key], expected_skip, places=9, msg=key)
            # The flag restores the old one.
            self.assertAlmostEqual(restored[key], expected_plain, places=9, msg=key)
            # Guard: the two windows must actually differ on this fixture.
            self.assertGreater(abs(expected_plain - expected_skip), 1e-6, key)
        # Nothing outside relative strength may move.
        for key in ("rsi14", "adx14", "macdHistogram", "volumeRatio20D", "sma200"):
            self.assertEqual(shipped[key], restored[key], key)

    def test_relative_strength_cannot_disturb_the_preregistered_cell(self):
        # knowledge/preregistration.md names one cell: the MOMENTUM block at
        # 1 month, rung C. Changing relative strength in the engine must leave it
        # bit-identical, or the pre-registration is invalidated before it is ever
        # run. Momentum is MACD + RSI and neutralisation residualises on sector
        # and liquidity, so nothing in that path reads relative strength -- but
        # that is an argument, and this is the assertion.
        dates = self._business_days(420, start="2018-01-01")
        history = {}
        for k in range(14):
            history["T%02d" % k] = self._series(
                dates, [100.0 + math.sin(i / (6.0 + k)) * 9.0 + i * (0.06 if k % 2 else -0.04)
                        for i in range(len(dates))])
        history[E.BENCHMARK_SYMBOL] = self._series(
            dates, [1000.0 + i * 0.08 for i in range(len(dates))])
        book = PriceBook(history)
        calendar = market_calendar(history)
        bench = dict(zip(dates, history[E.BENCHMARK_SYMBOL]["closes"]))
        date = month_end_sessions(calendar)[-1]
        sectors = {t: ("Alpha" if i % 3 == 0 else "Beta" if i % 3 == 1 else "Gamma")
                   for i, t in enumerate(sorted(book.tickers()))}

        shipped = rank_on(book, date, bench, block="momentum", continuous=True,
                          neutral=True, sectors=sectors)
        restored = rank_on(book, date, bench, block="momentum", continuous=True,
                           neutral=True, sectors=sectors, no_skip_month=True)
        self.assertGreater(len(shipped), 9)
        self.assertEqual(shipped, restored,
                         "the relative-strength window moved the momentum block")

        # Guard: the fixture must be one where relative strength ACTUALLY moves,
        # or the equality above holds for a reason unrelated to the claim.
        rs_shipped = rank_on(book, date, bench, block="relStrength", continuous=True,
                             neutral=True, sectors=sectors)
        rs_restored = rank_on(book, date, bench, block="relStrength", continuous=True,
                              neutral=True, sectors=sectors, no_skip_month=True)
        self.assertNotEqual(rs_shipped, rs_restored,
                            "fixture does not exercise the relative-strength change")

    def test_neutralising_removes_sector_and_size(self):
        # Build a score that is ENTIRELY sector effect plus size effect, so a
        # working neutralisation must return approximately zero for everyone.
        sectors, scores, sizes = {}, {}, {}
        for group, (name, offset) in enumerate((("Banks", 10.0), ("Tech", -4.0), ("Pharma", 2.0))):
            for k in range(6):
                ticker = "%s%d" % (name, k)
                sectors[ticker] = name
                sizes[ticker] = 12.0 + k * 0.5
                scores[ticker] = offset + 3.0 * sizes[ticker]
        buckets = sector_buckets(sorted(scores), sectors)
        self.assertEqual(len(set(buckets.values())), 3)
        out = neutralise(scores, buckets, sizes)
        for ticker, value in out.items():
            self.assertAlmostEqual(value, 0.0, places=9, msg=ticker)
        # Guard: the raw scores were nowhere near zero, so the assertion above
        # is not satisfied trivially.
        self.assertGreater(max(abs(v) for v in scores.values()), 20.0)
        # A signal orthogonal to both must SURVIVE, or neutralisation is just
        # erasure. Add an alternating component that is uncorrelated with size
        # within each sector.
        with_signal = {t: scores[t] + (5.0 if int(t[-1]) % 2 else -5.0) for t in scores}
        kept = neutralise(with_signal, buckets, sizes)
        self.assertGreater(max(kept.values()) - min(kept.values()), 5.0)

    def test_a_lone_name_is_not_demeaned_to_a_fake_average(self):
        # Demeaning a bucket of one sets that name to exactly zero, which reads
        # as "average" and means "alone in its group". Pooling small industries
        # into Other handles the usual case, but Other itself can hold a single
        # name. Such a name must be demeaned against the whole cross-section, so
        # its standing is preserved rather than replaced by a fake zero.
        sectors = {"A%d" % k: "Banks" for k in range(6)}
        sectors["LONE"] = "Shipping"
        scores = {t: 1.0 for t in sectors}
        scores["LONE"] = 99.0          # clearly the best name present
        sizes = {t: 10.0 for t in sectors}
        buckets = sector_buckets(sorted(scores), sectors)
        self.assertEqual(buckets["LONE"], "Other")
        counts = {}
        for bucket in buckets.values():
            counts[bucket] = counts.get(bucket, 0) + 1
        self.assertEqual(counts["Other"], 1, "fixture must produce a bucket of one")
        out = neutralise(scores, buckets, sizes)
        self.assertNotAlmostEqual(out["LONE"], 0.0, places=6,
                                  msg="a lone name was demeaned to a fake average")
        # And it must still rank first, because it still is first.
        self.assertEqual(max(out, key=lambda t: out[t]), "LONE")

    def test_winsorised_z_is_standardised_and_clips_both_tails(self):
        # A z-score that is not actually standardised would silently reweight
        # every feature by its raw units -- RSI spans 0-100, relative strength
        # spans percentages, and a composite of unstandardised values is a
        # composite of whichever feature happens to have the largest scale.
        values = [float(i) for i in range(100)]
        z = _winsorised_z(values)
        self.assertEqual(len(z), len(values))
        self.assertAlmostEqual(sum(z) / len(z), 0.0, places=12)
        variance = sum(v * v for v in z) / (len(z) - 1)
        self.assertAlmostEqual(variance, 1.0, places=12)
        # An extreme outlier must not be able to dominate the cross-section.
        # Without clipping this z would be ~9.9 (one point carrying the whole
        # variance); clipped to the 97.5th percentile it lands near the top of
        # the real distribution instead.
        spiked = [float(i) for i in range(99)] + [1.0e9]
        zs = _winsorised_z(spiked)
        self.assertLess(max(zs), 3.0)
        # No spread means the feature orders nothing; None, not a divide by zero.
        self.assertIsNone(_winsorised_z([3.0] * 40))

    def test_winsorising_still_clips_below_forty_names(self):
        # int(n * 0.025) is 0 for every n < 40, so the tails were never touched
        # there. Nothing raised; the transform just quietly stopped being a
        # winsorisation. This asserts the tails actually MOVED, which is the
        # only observable difference between clipping and not clipping.
        for n in (10, 20, 30, 39):
            values = [float(i) for i in range(n - 1)] + [1.0e6]
            z = _winsorised_z(values)
            self.assertIsNotNone(z, "n=%d returned nothing" % n)
            # With one outlier and no clipping the maximum z is EXACTLY
            # (n-1)/sqrt(n). A flat bound of 3.0 does not discriminate at n=10,
            # where that value is 2.846 -- a quarter of this loop asserted
            # nothing. Scaling to the unclipped value discriminates at every n
            # by construction.
            unclipped = (n - 1) / math.sqrt(n)
            self.assertLess(max(z), unclipped * 0.9,
                            "n=%d: the outlier was not clipped (max z %.4f, "
                            "unclipped would be %.4f)" % (n, max(z), unclipped))
        # And the middle must survive: clipping must not flatten the spread.
        z30 = _winsorised_z([float(i) for i in range(29)] + [1.0e6])
        self.assertGreater(len({round(v, 9) for v in z30}), 20)
        # Below five names there is no tail to identify, and destroying the
        # spread would be worse than leaving it: these must still order.
        for n in (3, 4):
            z = _winsorised_z([float(i) for i in range(n)])
            self.assertIsNotNone(z)
            self.assertEqual(len({round(v, 9) for v in z}), n)

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
        # respect_holdout=False: this fixture is dated after HOLDOUT_START and
        # the test is about cost arithmetic, not about which months are
        # measurable.
        periods = run_portfolio(book, dates, month_end_sessions(dates, respect_holdout=False),
                                bench, 1, 15.0)
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

    def test_the_hac_t_is_referred_to_the_independent_count_not_to_n(self):
        # n-1 is the df of an i.i.d. mean. On overlapping windows consecutive
        # observations share (h-1)/h of their span, so the independent count is
        # about n/h and referring the HAC t to n-1 over-rejects. It did: relative
        # strength at 6 months read p 0.0030 at df 80, where the independent
        # count is 13 and the p is 0.0099.
        rng = random.Random(77)
        series, prev = [], 0.0
        for _ in range(84):
            prev = 0.8 * prev + rng.gauss(0.0, 1.0)
            series.append(prev + 0.35)
        stats = _ic_statistics(series, family_size=1, hac_lag=5)
        # n // h, which reproduces the non-overlapping series length the study
        # already computes rather than introducing a second estimate.
        self.assertEqual(stats["hac_effective_n"], 84 // 6)
        self.assertEqual(stats["hac_df"], 84 // 6 - 1)
        self.assertAlmostEqual(stats["hac_p_value"],
                               two_sided_p(stats["hac_t_stat"], stats["hac_df"]),
                               places=12)
        # Guard: the two df must actually give different answers on this fixture,
        # or every assertion above would hold for the defect too.
        naive = two_sided_p(stats["hac_t_stat"], len(series) - 1)
        self.assertGreater(stats["hac_p_value"], naive,
                           "the correct df must not be more permissive")
        self.assertGreater(stats["hac_p_value"] / naive, 1.2,
                           "fixture does not separate the two df")
        # At lag 0 there is no overlap to discount and the count is n itself, so
        # every non-overlapping figure already published is unaffected.
        flat = _ic_statistics(series, family_size=1, hac_lag=0)
        self.assertEqual(flat["hac_effective_n"], len(series))
        self.assertEqual(flat["hac_df"], len(series) - 1)

    def test_the_detection_floor_uses_the_same_standard_error_as_the_t(self):
        # A floor computed from an i.i.d. SE beside a t computed from a HAC one
        # is not a pair of numbers about the same test. On the real pre-holdout
        # file the 6-month floor read 0.0478 where the honest figure is 0.0607:
        # understated by 27%, in the direction that makes a null look more
        # conclusive than the data supports.
        # An AR(1) with phi=0.8, the same construction the HAC test above uses.
        # A first attempt built the series from sin(i * 1.7), which oscillates
        # fast enough to be NEGATIVELY autocorrelated -- the guard below caught
        # it, which is the only reason this test is not quietly backwards.
        rng = random.Random(4242)
        series, prev = [], 0.0
        for _ in range(200):
            prev = 0.8 * prev + rng.gauss(0.0, 1.0)
            series.append(prev)
        n = len(series)
        mean = sum(series) / n
        spread = math.sqrt(sum((v - mean) ** 2 for v in series) / (n - 1))
        iid_floor = (_t_critical(n - 1) + Z_FOR_80_PERCENT_POWER) * spread / math.sqrt(n)

        overlapping = _ic_statistics(series, family_size=1, hac_lag=11)
        # Guard: if the fixture were not actually autocorrelated the two SEs
        # would coincide and every assertion below would pass without
        # distinguishing the fix from the defect.
        self.assertGreater(overlapping["hac_se"], spread / math.sqrt(n))
        # The floor is referred to the HAC degrees of freedom, not n-1: at
        # hac_lag=11 the independent count is n//12, not n.
        self.assertEqual(overlapping["hac_effective_n"], n // 12)
        hac_floor = ((_t_critical(overlapping["hac_df"]) + Z_FOR_80_PERCENT_POWER)
                     * overlapping["hac_se"])
        self.assertAlmostEqual(overlapping["detectable_ic_80pct"], hac_floor, places=12)
        self.assertGreater(overlapping["detectable_ic_80pct"] - iid_floor, 1e-4)

        # At lag 0 there is no overlap to correct for, so the floor stays on the
        # sample standard deviation and the published non-overlapping figures
        # are unaffected.
        independent = _ic_statistics(series, family_size=1, hac_lag=0)
        self.assertAlmostEqual(independent["detectable_ic_80pct"], iid_floor, places=12)

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

    def test_months_held_matches_the_holding_period_test(self):
        # s.2(42A): twelve months. The day-of-month comparison decides the
        # boundary, and the boundary is the whole question for a monthly system.
        self.assertEqual(_months_held("2020-01-15", "2021-01-15"), 12)
        self.assertEqual(_months_held("2020-01-15", "2021-01-14"), 11)  # one day short
        self.assertEqual(_months_held("2020-01-15", "2021-01-16"), 12)
        self.assertEqual(_months_held("2020-01-31", "2020-12-31"), 11)
        self.assertEqual(_months_held("2020-01-01", "2020-01-31"), 0)

    def test_buffering_cuts_turnover_and_keeps_names(self):
        # A held name must survive until it leaves the top N*multiple, and the
        # book must still be exactly N names.
        # SIXTY ranked names, because with only 40 the top-2N window is the whole
        # list and nothing can fall outside it -- the first version of this
        # fixture made that mistake and the test caught it.
        ranked = [("T%02d" % i, 100.0 - i) for i in range(60)]
        held = ["T25", "T45", "T05"]   # rank 25 inside the top 40, 45 outside, 5 inside
        selected = buffered_selection(ranked, held, top_n=20, buffer_multiple=2)
        self.assertEqual(len(selected), 20)
        self.assertIn("T25", selected, "a name inside the top 2N was sold")
        self.assertIn("T05", selected)
        self.assertNotIn("T45", selected, "a name outside the top 2N was kept")
        # Without buffering it is simply the top 20, and T25 is gone.
        plain = buffered_selection(ranked, held, top_n=20, buffer_multiple=1)
        self.assertEqual(plain, ["T%02d" % i for i in range(20)])
        self.assertNotIn("T25", plain)
        # Guard: the two rules must actually differ on this fixture.
        self.assertNotEqual(selected, plain)

    def test_after_tax_on_cases_with_known_answers(self):
        # A portfolio that never sells pays NO tax, however much it gains. If this
        # ever fails, the simulator is taxing unrealised gains.
        dates = self._business_days(400, start="2018-01-01")
        rising = [100.0 * (1.01 ** i) for i in range(len(dates))]
        history = {"AAA": self._series(dates, rising),
                   "BBB": self._series(dates, rising),
                   E.BENCHMARK_SYMBOL: self._series(dates, [1000.0] * len(dates))}
        book = PriceBook(history)
        never_sells = [{"entry_date": dates[i], "exit_date": dates[i + 20],
                        "holdings": ["AAA", "BBB"]} for i in range(0, 300, 20)]
        out = after_tax_performance(book, never_sells, cost_bps_per_side=0.0)
        self.assertAlmostEqual(out["tax_paid"], 0.0, places=12)
        self.assertGreater(out["final_value"], 1.0)

        # Now a portfolio that swaps its whole book every period, inside twelve
        # months, so every realised gain is SHORT term and taxed at 20%.
        churn = []
        for index, i in enumerate(range(0, 300, 20)):
            churn.append({"entry_date": dates[i], "exit_date": dates[i + 20],
                          "holdings": ["AAA"] if index % 2 == 0 else ["BBB"]})
        taxed = after_tax_performance(book, churn, cost_bps_per_side=0.0)
        self.assertGreater(taxed["tax_paid"], 0.0)
        self.assertAlmostEqual(taxed["short_share"], 1.0, places=9,
                               msg="a sub-12-month churn produced long-term gains")
        # And it must end up behind the buy-and-hold version on the same prices.
        self.assertLess(taxed["final_value"], out["final_value"])

        # A LONG-term sale is taxed at the lower rate. One holding, sold after
        # more than twelve months.
        long_hold = [{"entry_date": dates[0], "exit_date": dates[330],
                      "holdings": ["AAA"]},
                     {"entry_date": dates[330], "exit_date": dates[360],
                      "holdings": ["BBB"]}]
        slow = after_tax_performance(book, long_hold, cost_bps_per_side=0.0)
        self.assertAlmostEqual(slow["short_share"], 0.0, places=9)
        self.assertGreater(slow["realised_long"], 0.0)

    def test_percentile_index_is_nearest_rank(self):
        # The qth percentile of n sorted values sits at ceil(q*n) - 1, not
        # int(q*n). At the study's 2000 draws the old form took index 50 and 1950
        # where the answers are 49 and 1949 -- both tails off by one rank.
        self.assertEqual(_percentile_index(0.025, 2000), 49)
        self.assertEqual(_percentile_index(0.975, 2000), 1949)
        self.assertNotEqual(_percentile_index(0.025, 2000), int(0.025 * 2000))
        self.assertNotEqual(_percentile_index(0.975, 2000), int(0.975 * 2000))
        values = list(range(100))
        self.assertEqual(values[_percentile_index(0.50, 100)], 49)
        self.assertEqual(values[_percentile_index(0.01, 100)], 0)
        self.assertEqual(values[_percentile_index(1.00, 100)], 99)
        self.assertEqual(_percentile_index(0.0, 10), 0)
        self.assertEqual(_percentile_index(1.5, 10), 9)

    def test_every_phase_is_used_not_just_the_first(self):
        # At horizon h there are h non-overlapping series. Keeping only phase 0
        # discarded (h-1)/h of the observations and made the column depend on
        # which month the price file began in.
        phases = {0: [0.10] * 9, 1: [0.20] * 9, 2: [0.30] * 9, 3: [0.40] * 9}
        stats = _phase_averaged_statistics(phases, family_size=1)
        self.assertEqual(stats["phases_averaged"], 4)
        self.assertAlmostEqual(stats["mean_ic"], 0.25, places=12)
        self.assertEqual(stats["ic_periods"], 36)
        # Guard: phase 0 alone gives 0.10. If this ever equals 0.10 the averaging
        # has silently stopped happening.
        self.assertNotAlmostEqual(stats["mean_ic"], 0.10, places=6)

    def test_phase_averaging_does_not_shrink_the_standard_error(self):
        # Averaging h phase means does NOT buy a sqrt(h) precision gain: phase 0's
        # first window spans months 0..h and phase 1's spans 1..h+1, sharing h-1
        # of them. Dividing by sqrt(h) would understate the SE -- the direction
        # this project keeps having to correct.
        rng = random.Random(5)
        phases = {k: [rng.gauss(0.05, 0.2) for _ in range(20)] for k in range(4)}
        stats = _phase_averaged_statistics(phases, family_size=1)
        singles = [_ic_statistics(series, 1, hac_lag=0) for series in phases.values()]
        typical_se = sum(p["ic_sd"] / math.sqrt(p["ic_periods"]) for p in singles) / 4
        self.assertAlmostEqual(abs(stats["mean_ic"] / stats["ic_t_stat"]), typical_se,
                               places=12)
        self.assertGreater(abs(stats["mean_ic"] / stats["ic_t_stat"]),
                           typical_se / math.sqrt(4) * 1.5)
        self.assertEqual(stats["phase_periods"], 20)

    def test_the_bootstrap_is_not_a_conservative_check_on_hac(self):
        # It was introduced as one and the docstring said so. It is not: across
        # the 15 overlapping cells of the pre-holdout run the bootstrap SE is
        # SMALLER than the HAC SE in 10, including every high-dependence cell.
        # This pins the direction so the claim cannot be quietly re-added.
        #
        # The fixture is a moving average of h shocks, which is exactly the
        # dependence an overlapping h-window IC series carries, and whose true
        # long-run variance is the shock variance -- so the true standard error
        # of the mean is 1/sqrt(n) and both estimators can be scored against it
        # rather than only against each other.
        rng = random.Random(31)
        h, n = 6, 81
        shocks = [rng.gauss(0.0, 1.0) for _ in range(n + h - 1)]
        series = [sum(shocks[t:t + h]) / h for t in range(n)]
        true_se = 1.0 / math.sqrt(n)
        hac = _newey_west_se(series, h - 1)
        boot, _lo, _hi = _stationary_bootstrap_se(series, h, draws=400, seed=31)
        self.assertGreater(hac, 0.0)
        self.assertGreater(boot, 0.0)
        # Not the conservative one.
        self.assertLessEqual(boot, hac * 1.05,
                             "the bootstrap is being treated as a conservative check")
        # And both understate the truth, which is why every t here reads inflated.
        self.assertLess(hac, true_se, "HAC did not understate on a known structure")
        self.assertLess(boot, true_se, "the bootstrap did not understate")

    def test_cagr_difference_ci_on_cases_with_known_answers(self):
        # Constructed rather than real, so the right answer is known in advance
        # and the test can fail. Two identical series must read as no
        # difference: the first version reported p 0.000 and an interval
        # excluding zero for them, because strict > 0 comparisons sorted
        # exactly-zero into the negative bucket, making ties count on one side
        # only. That bug would never surface on real data and would silently
        # promote any interval with a bound at zero.
        rng = random.Random(1)
        base = [rng.gauss(0.01, 0.05) for _ in range(130)]

        def periods(returns, start=0):
            return [{"signal_date": "20%02d-%02d-28" % (15 + (start + i) // 12,
                                                        1 + (start + i) % 12),
                     "net_return": r} for i, r in enumerate(returns)]

        same = cagr_difference_ci(periods(base), periods(base))
        self.assertAlmostEqual(same["difference"], 0.0, places=12)
        self.assertFalse(same["excludes_zero"])
        self.assertAlmostEqual(same["p_value"], 1.0, places=12)

        # A large consistent edge must be detected, or the test above would pass
        # for a function that always says "no difference".
        better = cagr_difference_ci(periods([r + 0.02 for r in base]), periods(base))
        self.assertGreater(better["difference"], 0.2)
        self.assertTrue(better["excludes_zero"])
        self.assertLess(better["p_value"], 0.01)

        # Months pair on signal_date, not by position: the strategy series is
        # shorter than the equal-weight one in every real run.
        offset = cagr_difference_ci(periods(base[:60]), periods(base, start=30))
        self.assertEqual(offset["months"], 30)

    def test_every_strategy_benchmark_pair_covers_the_same_months(self):
        # The GENERAL guard. test_every_column_of_the_performance_table... covers
        # the performance block only, which is exactly why it could not see the
        # after-tax block comparing 86 strategy months against 95 equal-weight
        # ones -- the same benchmark-alignment defect c96780d fixed, reintroduced
        # in a code path that never went through align_to().
        #
        # This walks the WHOLE result and checks every dict that prints a
        # strategy against an equal_weight. A third instance has to add such a
        # pair to be a defect, and adding one is what this catches.
        dates = self._business_days(700, start="2018-01-01")
        history = {}
        for k in range(6):
            history["T%d" % k] = self._series(
                dates, [100.0 + math.sin(i / (7.0 + k)) * 8.0 + i * (0.05 if k % 2 else -0.03)
                        for i in range(len(dates))])
        history[E.BENCHMARK_SYMBOL] = self._series(
            dates, [1000.0 + i * 0.05 for i in range(len(dates))])
        results = backtest(history, top_n=3, capital=1000000.0)

        pairs = []

        def walk(node, path):
            if isinstance(node, dict):
                if isinstance(node.get("strategy"), dict) and \
                        isinstance(node.get("equal_weight"), dict):
                    pairs.append((path, node["strategy"], node["equal_weight"]))
                for key, value in node.items():
                    walk(value, "%s.%s" % (path, key))

        walk(results, "results")
        # Guard: if the walker finds nothing, every assertion below is vacuous.
        self.assertGreaterEqual(len(pairs), 2,
                                "walker found no strategy/equal_weight pairs to check")
        for path, strategy, benchmark in pairs:
            if not strategy or not benchmark:
                continue
            self.assertEqual(strategy.get("months"), benchmark.get("months"),
                             "%s compares different month counts" % path)
            if "years" in strategy and "years" in benchmark:
                self.assertAlmostEqual(strategy["years"], benchmark["years"], places=12,
                                       msg="%s compares different spans" % path)

    def test_the_after_tax_gap_agrees_with_its_own_parts(self):
        # Equal month counts are necessary and not sufficient: two wrong-but-equal
        # counts would pass. This also recomputes each side's CAGR from its own
        # final value and span, so the reported gap has to agree with figures
        # derived a different way.
        dates = self._business_days(700, start="2018-01-01")
        history = {}
        for k in range(6):
            history["T%d" % k] = self._series(
                dates, [100.0 + math.cos(i / (6.0 + k)) * 7.0 + i * (0.04 if k % 2 else -0.02)
                        for i in range(len(dates))])
        history[E.BENCHMARK_SYMBOL] = self._series(
            dates, [1000.0 + i * 0.04 for i in range(len(dates))])
        results = backtest(history, top_n=3, capital=1000000.0)
        block = results["after_tax"]
        self.assertTrue(block, "no after-tax block was produced")
        strategy, benchmark = block["strategy"], block["equal_weight"]
        self.assertEqual(strategy["months"], benchmark["months"])
        self.assertAlmostEqual(strategy["years"], benchmark["years"], places=12)
        for side in (strategy, benchmark):
            recomputed = side["final_value"] ** (1.0 / side["years"]) - 1.0
            self.assertAlmostEqual(side["cagr"], recomputed, places=12)
        self.assertAlmostEqual(block["gap"], strategy["cagr"] - benchmark["cagr"],
                               places=12)
        # And the equal-weight book must start where the strategy starts, or its
        # lot history -- and so its short/long split -- describes a different
        # window from the one being compared.
        self.assertEqual(strategy["months"], len(results["periods"]))

    def test_every_column_of_the_performance_table_covers_the_same_months(self):
        # The strategy cannot trade until enough companies clear the minimum
        # session rule; equal-weighting trades from the first month in the file.
        # On the real pre-holdout span that is 86 months against 95, printed as
        # adjacent columns under a heading naming 86. Subtracting the CAGR row
        # gave -0.77pp; the paired figure below the same table gave -3.89pp.
        dates = self._business_days(700, start="2018-01-02")
        history = {}
        for k in range(6):
            drift = 0.05 if k % 2 else -0.03
            history["T%d" % k] = self._series(
                dates, [100.0 + math.sin(i / (7.0 + k)) * 8.0 + i * drift
                        for i in range(len(dates))])
        history[E.BENCHMARK_SYMBOL] = self._series(
            dates, [1000.0 + i * 0.05 for i in range(len(dates))])

        # Establish that the fixture reproduces the ragged start before asserting
        # anything about the cure. Without this the assertions below would also
        # pass on a fixture where aligning is a no-op, and would then be
        # measuring nothing.
        book = PriceBook(history)
        calendar = market_calendar(history)
        rebalances = month_end_sessions(calendar)
        bench = dict(zip(dates, history[E.BENCHMARK_SYMBOL]["closes"]))
        raw_strategy = run_portfolio(book, calendar, rebalances, bench, 3,
                                     DEFAULT_COST_BPS_PER_SIDE)
        raw_equal = run_equal_weight(book, calendar, rebalances)
        self.assertGreater(len(raw_equal), len(raw_strategy),
                           "fixture does not produce a ragged start, so it cannot "
                           "detect whether the columns are aligned")

        block = backtest(history, top_n=3)["performance"]["full"]
        self.assertEqual(block["equal_weight"]["months"], block["strategy"]["months"])
        self.assertEqual(block["index"]["months"], block["strategy"]["months"])
        # The reason alignment is worth doing: the subtraction a reader performs
        # on the table now equals the paired figure printed underneath it,
        # instead of contradicting it.
        gap = block["cagr_vs_equal_weight"]
        self.assertTrue(gap["draws"], "no paired figure to agree with")
        self.assertAlmostEqual(block["strategy"]["cagr"] - block["equal_weight"]["cagr"],
                               gap["difference"], places=12)

    def test_the_holdout_cut_removes_reserved_months_and_can_be_lifted(self):
        # A flag that is wired but does nothing passes every grep and every
        # type check. This asserts on the rebalance list itself, in both
        # directions, because a cut that never cuts and a cut that cannot be
        # lifted are different bugs and the second only shows at the final test.
        calendar = self._business_days(900, start="2021-01-01")
        self.assertGreater(calendar[-1], HOLDOUT_START)

        reserved = month_end_sessions(calendar, respect_holdout=True)
        everything = month_end_sessions(calendar, respect_holdout=False)

        self.assertTrue(reserved, "the cut must not empty the list")
        self.assertLess(len(reserved), len(everything))
        self.assertTrue(all(d < HOLDOUT_START for d in reserved))
        self.assertTrue(any(d >= HOLDOUT_START for d in everything))
        # Lifting the cut must restore exactly the reserved months and nothing
        # else -- not reorder, not duplicate.
        self.assertEqual(everything[:len(reserved)], reserved)
        # And the default is the protective one.
        self.assertEqual(month_end_sessions(calendar), reserved)

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
    parser.add_argument("--portfolio-block", default=None, metavar="NAME",
                        help="rank the PORTFOLIO on one block rather than the composite.")
    parser.add_argument("--invert", action="store_true",
                        help="hold the WORST-ranked names. With --portfolio-block momentum "
                             "this trades the pre-registered reversal hypothesis.")
    parser.add_argument("--buffer", type=int, default=1, metavar="N",
                        help="exit a holding only when it leaves the top N*top_n rather "
                             "than the top top_n. 2 is the usual rank buffer; 1 is off.")
    parser.add_argument("--tax-stcg", type=float, default=STCG_RATE, metavar="RATE",
                        help="short-term capital gains rate as a fraction (default %.2f, "
                             "the s.111A rate since 23 July 2024). Long-term is fixed at "
                             "%.3f per s.112A." % (STCG_RATE, LTCG_RATE))
    parser.add_argument("--capital", type=float, default=None, metavar="RUPEES",
                        help="portfolio size in rupees, used to apply the Rs 1.25 lakh "
                             "s.112A annual exemption. WITHOUT it the exemption is off, "
                             "which taxes long-term gains from the first rupee and so "
                             "penalises the long-term-heavy side -- equal weight. That "
                             "INFLATES the strategy's gap; supply a size for any published "
                             "comparison.")
    parser.add_argument("--neutral", action="store_true",
                        help="residualise the score on sector dummies and log trailing "
                             "median turnover before ranking. Sector comes from the NSE "
                             "constituents file and is a snapshot as of %s, so it is "
                             "stale; turnover is a point-in-time LIQUIDITY proxy that "
                             "correlates with size and is not market cap." % SECTOR_AS_OF)
    parser.add_argument("--no-skip-month", action="store_true",
                        help="measure relative strength t-h to t-1, the window the engine used before 2026-09-14. The engine now skips the most recent month by default (CFA rf-v2016-n4-1#71); this restores the old window so the change stays measurable. A measurement only: engine.py is untouched by this flag.")
    parser.add_argument("--continuous", action="store_true",
                        help="score the twelve technical features on their MAGNITUDES "
                             "(winsorised cross-sectional z-scores, combined with the "
                             "engine's own weights) instead of on the binary thresholds "
                             "the shipped model uses. A measurement only: engine.py is "
                             "untouched, so the shipped score is unchanged and the "
                             "comparison isolates thresholding rather than confounding "
                             "it with a reweighting.")
    parser.add_argument("--rsi-flip", action="store_true",
                        help="score rsi14 BELOW the momentum floor instead of above it "
                             "(rulebook open item 1). A measurement only: the shipped "
                             "engine is untouched and RSI_MOMENTUM_FLOOR is not edited, "
                             "because changing the live comparison to see whether it "
                             "backtests better is adoption rather than measurement.")
    parser.add_argument("--no-respect-holdout", action="store_true",
                        help="measure against the reserved window from %s onward. "
                             "Reserved data answers a question once; this flag spends "
                             "it. Exists for the single final test described in "
                             "knowledge/holdout.md, and for nothing else."
                             % HOLDOUT_START)
    parser.add_argument("--self-test", action="store_true", help="run the offline checks and exit")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    if args.self_test:
        suite = unittest.TestLoader().loadTestsFromTestCase(BacktestTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1

    if not args.prices:
        parser.error("--prices is required unless --self-test is given")
    history, skipped = E.parse_price_history_csv(Path(args.prices).read_text(encoding="utf-8"))
    print("Loaded %d tickers (%d rows skipped)." % (len(history), skipped))
    if args.buffer > 1:
        print("RANK BUFFER %dx: a holding is sold only once it leaves the top %d."
              % (args.buffer, args.buffer * args.top_n))
    if args.capital:
        print("TAX: STCG %.1f%%, LTCG %.1f%% with the Rs 1.25 lakh annual exemption "
              "applied against a capital of Rs %.0f." % (args.tax_stcg * 100,
                                                          LTCG_RATE * 100, args.capital))
    else:
        print("TAX: STCG %.1f%%, LTCG %.1f%%, exemption NOT applied -- which penalises "
              "the long-term-heavy side and inflates the strategy's gap. Pass --capital "
              "for a published comparison." % (args.tax_stcg * 100, LTCG_RATE * 100))
    if args.continuous:
        print("CONTINUOUS SCORING: the twelve features are scored on magnitude "
              "(winsorised z-scores at tail %.3f) rather than on threshold tests. "
              "The engine's weights are unchanged, so this measures the cost of "
              "binarizing and nothing else." % WINSOR_TAIL)
    if args.rsi_flip:
        print("RSI SIGN FLIPPED: scoring rsi14 below %s instead of above it. "
              "This measures the alternative; it does not change the engine."
              % E.RSI_MOMENTUM_FLOOR)
    respect_holdout = not args.no_respect_holdout
    if respect_holdout:
        print("Holdout respected: measuring only up to %s. See knowledge/holdout.md."
              % HOLDOUT_START)
    else:
        print("*** SPENDING THE RESERVED WINDOW (%s onward). ***" % HOLDOUT_START)
        print("*** Reserved data answers a question once. If this is not the single ***")
        print("*** final test described in knowledge/holdout.md, stop and record why. ***")
    results = backtest(history, args.top_n, args.cost_bps,
                       args.variants_tried, args.variants_note, rsi_flip=args.rsi_flip,
                       respect_holdout=respect_holdout, continuous=args.continuous,
                       neutral=args.neutral, no_skip_month=args.no_skip_month,
                       buffer_multiple=args.buffer, stcg_rate=args.tax_stcg,
                       capital=args.capital, portfolio_block=args.portfolio_block,
                       invert=args.invert)
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
