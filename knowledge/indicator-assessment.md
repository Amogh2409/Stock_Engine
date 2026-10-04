# Indicator assessment — 2026-10-04

Working horizon: medium to long term, approximately 6–12 months. This is a
research watchlist, not a claim to identify the best future stocks.

## What deserves priority

| Family | Useful measures | Current engine | Next useful work |
| --- | --- | --- | --- |
| Quality | ROE, ROCE, leverage, earnings stability | Profitability and leverage already scored; lenders have a separate model | Collect dated annual earnings history before implementing earnings stability |
| Value | Earnings yield, book-to-price, cash-flow valuation | Sector-relative P/E and P/B already scored | Report operating cash-flow yield as context; obtain capex and aligned periods before free-cash-flow metrics |
| Momentum | Medium-term returns and benchmark-relative strength | 3/6/12-month returns and relative strength already calculated | Retain the technical freeze; validate a prespecified hypothesis before changing rankings |
| Risk | ATR, realised volatility, liquidity, concentration | ATR and volatility already used for sizing; exposure caps exist | Improve data and execution-cost coverage; risk measures are not expected-return forecasts |

NSE's [Nifty200 Momentum 30](https://www.niftyindices.com/indices/equity/strategy-indices/nifty200-momentum-30)
uses six- and twelve-month returns adjusted for volatility. Our relative-strength
implementation is different and should not be described as replicating it.
NSE's [Nifty200 Quality 30](https://niftyindices.com/indices/equity/strategy-indices/nifty200-quality-30)
uses ROE, debt/equity, and five-year EPS variability. Our current export does not
provide that five-year series. These are documented methodologies, not proof
that copying them will outperform in this engine.

Asness, Moskowitz and Pedersen's [Value and Momentum Everywhere](https://www.aqr.com/insights/research/journal-article/value-and-momentum-everywhere)
reports evidence across multiple markets and asset classes. This supports
researching complementary factor families; it does not justify any particular
weight or threshold for Indian stocks.

The CFA Institute's [market-based valuation reading](https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/market-based-valuation-price-enterprise-value-multiples)
discusses cash-flow multiples and their drawbacks. The new diagnostic is
**reported operating cash flow / market cap × 100**, with no inferred annual
period. Capital expenditure is unavailable, so it cannot be called free cash
flow. Working-capital changes, reporting conventions and one-off items can
distort it. A high value alone is not a buy signal.

## Implementation and validation boundary

`python/engine.py` remains the source of truth; TypeScript mirrors the formula.
Evaluation records expose `operatingCashFlowYieldPct`; the stock-detail panel
shows the percentage and its limitations. Financial companies, invalid inputs,
and evaluations with hard data flags show unavailable. No score, gate, ranking,
position weight, CSV schema or technical constant changed.

The current engine already calculates RSI, MACD, ADX, Bollinger position and
volume measures. Adding more related technical indicators would not address the
repository's missing validation of its fundamentals. See
[the frozen baseline](v1-engine-freeze.md) and [the handbook](../docs/HANDBOOK.md#1-the-honest-state-of-the-evidence).
Pre-holdout results are exploratory, with 125+ searches documented in that
handbook; no new performance figure was computed here.

To adopt any new ranking rule, first acquire point-in-time fundamentals with
publication dates and adequate historical coverage, specify the hypothesis and
decision criteria before measuring returns, and compare with a simple benchmark
after costs. Do not backfill historical dates with today's fundamentals. Preserve
the [reserved window](holdout.md) and its [registered test](preregistration.md).
Current stock recommendations also require current, verified inputs; the bundled
sample has invented figures and cannot supply them.
