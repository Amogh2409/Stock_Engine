# Price and volume research tools

Implemented 2026-10-04 for daily bars, with `python/engine.py` as the source of
truth and `computeMarketStructure()` in TypeScript as its mirror. They are
diagnostics attached to screened companies and shown in the watchlist detail
panel and Selection review tab. They do not alter the original watchlist scoring,
admission, sorting or position sizing. No parameters were selected from performance results.

## What our data supports

The stored price-history CSV headers were inspected. Current and archived panels
contain Date, Ticker, Open, High, Low, Close and Volume; newer panels also contain
CloseUnadjusted. No trade-side, bid/ask or order-book columns were found in those
headers. Header presence does not guarantee non-missing values for every bar.
Only file headers were inspected for this work, not reserved-window returns.

| Requested tool | Implemented scope | Limitation |
| --- | --- | --- |
| Anchored VWAP | HLC3 weighted by volume from an explicit date through an as-of date | Daily approximation, not trade-by-trade VWAP |
| Liquidity sweep | Breach of the prior range followed by a close back across its boundary | Cannot establish resting stops, executed liquidity, or intraday event order |
| Wyckoff price cycle | Spring, upthrust, markup and markdown candidates; unresolved-range and ambiguous-sweep states | Not a complete Wyckoff phase classifier; no inferred institutional accumulation/distribution |
| Volume profile | Uniform distribution of each bar's volume across its high–low range; POC and contiguous 70% value area | Estimated volume at price, not observed executions or a TPO Market Profile |
| Order flow | Explicit unavailable result and required-data explanation | Needs aggressor-side trade data for delta/CVD; order-book events for depth, additions, cancellations and imbalance |

## Using the tools

Upload a daily price CSV through **Upload prices**, then select a company in the
watchlist and open **Price & volume research**. Dates must be YYYY-MM-DD.
Optional OHLCV columns in the general importer become required for the tools
that use them; an older close-only CSV yields unavailable diagnostics.

The anchor and as-of controls apply to the loaded company. With blank controls,
the as-of date is the latest loaded bar and the anchor is the first of the last
20 bars. This rolling default is not an event anchor or a retrospectively chosen
swing. Set an explicit anchor to fix it across subsequent sessions. A manual
anchor must match an observed session; a holiday, out-of-file date or date after
the as-of point is refused. As-of dates between sessions select the last earlier
loaded session. Changing company resets both controls. Downloaded JSON includes
the ticker, actual dates, approximation basis, values and unavailable reasons.

Use only completed daily bars. The importer does not establish exchange timezone,
session completeness or the price-adjustment provenance of a user-uploaded CSV.
Our existing Yahoo OHLC is adjusted; CloseUnadjusted is a separate field intended
for traded-value calculations. These diagnostics consistently use the existing
High/Low/Close basis and do not mix CloseUnadjusted with adjusted highs/lows.
Historical adjustment factors and volume units must be consistent. These levels
should not be represented as historical raw execution prices.

Python/notebook use (with a parsed per-ticker series):

```python
result = compute_market_structure(
    history["TCS"], anchor_date="2022-06-01", as_of="2022-12-30",
    lookback=20, bins=24,
)
```

Dates above are examples, not a run or a recommendation. The existing watchlist
CSV schema is unchanged. To use this from the repository, import
`compute_market_structure` and `parse_price_history_csv` from `python.engine`.

## Integrated selection review

Every screening run now attaches `marketStructure` and `selectionReview` to
evaluation records. Failed screens are marked **excluded** and cannot re-enter
through the review. Passing companies receive the automatic 20-bar-anchor
analysis when they have price history. This also covers passing companies below
the original top-N cutoff, so a chart pattern is not hidden just because its
fundamental rank missed the watchlist.

The separate **Selection review** tab defaults to **Review candidates**, with
filters for mixed patterns, unavailable data and failed screens. A candidate
must satisfy all of these conventions: pass the existing screen, close strictly
above the rolling anchored VWAP, have a spring or markup candidate context, and
have neither a buy-side nor two-sided sweep. Other complete patterns are marked
mixed; absent/invalid inputs and missing reference history are unavailable.
This is an **experimental human-review filter**, not a validated improvement in
returns, a buy instruction or an additional score. VWAP and price context are
correlated evidence, not independent confirmations.

Review requires the company's last price date to match the latest date among
screened companies in the loaded file. This blocks comparatively old series
but cannot certify the entire file is current. The UI shows the actual dates.
Manual chart anchors do not change this automatic rule. Candidates and exports
are ordered by the existing fundamental score, then ticker, to avoid comparing
mixed fundamental-only and fundamental-plus-technical composite scales.
Profile POC/value area and cash-flow yield are included as context, without
adding points or introducing a proximity cutoff.

The Python/Colab pipeline writes `selection_review_<stamp>.csv` beside its normal
watchlist and rejected CSVs, containing **all evaluated companies**, statuses,
reasons, dates, indicator values and approximation basis. The browser exports
the displayed review category, or all categories if selected. Text cells are
guarded against spreadsheet formula execution; unavailable numbers remain blank.
No review shortlist has automatic position weights: original watchlist sizing
continues to apply only to the original watchlist.

## Exact definitions and conventions

* VWAP = sum of `(High + Low + Close) / 3 × Volume` divided by total volume.
  Each anchored bar needs positive finite prices, Low ≤ Close ≤ High, and
  positive finite Volume. Missing or zero volume makes the anchored calculation
  unavailable; it is not replaced or skipped. The relative distance is
  `(latest Close / VWAP − 1) × 100`.
* Sweep reference levels are the highest high and lowest low of the **prior**
  20 bars, excluding the latest bar. Sell-side candidate: latest Low < reference
  low and Close > reference low. Buy-side candidate: latest High > reference
  high and Close < reference high. Equal touches/reclaims do not qualify.
  Both may occur on the same daily bar; this is ambiguous, not an entry signal.
* Wyckoff context first reports markup/markdown candidates for closes beyond
  the prior range. Inside the range, it reports two-sided ambiguity, a spring
  candidate, an upthrust candidate, or unresolved accumulation/distribution.
  These are price-pattern labels; they do not establish Wyckoff phases A–E,
  volume confirmation, cause/effect, or buying/selling by a particular actor.
* The profile uses 24 equal-width bins between the anchored minimum low and
  maximum high. A non-flat bar allocates volume in proportion to its overlap
  with each bin; a flat bar allocates all volume to one bin. A completely flat
  window has one bin. POC is the centre of the largest-volume bin, lower-price
  bin winning ties. Expand the value area one adjacent bin at a time, choosing
  the larger volume and choosing the lower side on ties, until at least 70% of
  total volume is included. No buy/sell split is fabricated from candle colour.
* The lookback, bin count, 70% target and tie-breaking choices are conventions.
  No source or test establishes them as optimal for stock selection. The Python
  and TypeScript APIs allow explicit lookback and bin parameters; the panel uses
  the documented defaults. Bounds 2–252 and 2–100 respectively limit inputs,
  not economic recommendations.

Dates must be unique and increasing; arrays must align. An invalid included bar
is never silently removed from a window. Future prices/volumes after the as-of
date do not influence the diagnostics. This guards the computation, not the
historical provenance of adjustment factors or the hindsight in an anchor a
researcher selects after seeing later prices.

## Evidence and data requirements

TradingView documents [anchored VWAP](https://www.tradingview.com/support/solutions/43000669764-anchored-vwap-drawing-tool/)
and the [HLC3 volume-weighted formula](https://www.tradingview.com/support/solutions/43000502018-volume-weighted-average-price-vwap/).
Its [volume-profile documentation](https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/)
uses lower-timeframe data. Our daily uniform allocation is a deliberately labelled
approximation, not a reproduction of TradingView's calculation.

The [Wyckoff tutorial](https://chartschool.stockcharts.com/table-of-contents/market-analysis/wyckoff-analysis-articles/the-wyckoff-method-a-tutorial)
describes multi-event price/volume analysis and phase development. One range
breach cannot establish the full cycle. The [NSE data offering](https://www.nseindia.com/static/market-data/real-time-data-subscription)
distinguishes market-depth levels and a full order-book tick feed. Those data
are not reconstructible from this repository's daily candles. Integration needs
a chosen provider, access rights, timestamp/sequence handling and trade-side
definitions before a genuine order-flow strategy can be implemented.

Corpus searches: `Wyckoff spring accumulation distribution`,
`volume weighted average price VWAP`, `volume profile price distribution`.
The Wyckoff results were a reading list/index, not evidence for a parameter.
Read `TSaM.pdf#590` and `TSaM.pdf#593`: TPO Market Profile tracks time, which is
distinct from volume at price. Also read
`02_open_textbooks/cfa_research_foundation/CFA_Institute_Research_Foundation_Monograph_rf-v2015-n4-1_.pdf#49`:
VWAP is described as a trade-execution benchmark over a specified interval, not
a proven directional stock-selection signal. No existing rulebook status was
upgraded from Convention.

Validation uses synthetic, hand-calculated examples, future-data exclusion,
missing-data/anchor checks, volume conservation, UI interactions and exact
Python/notebook–TypeScript parity. No strategy return, current stock signal or
holdout result was measured. See [the reserved window](holdout.md) and
[frozen engine policy](v1-engine-freeze.md).
