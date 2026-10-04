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

### Auction context and the stock evidence heatmap

`auctionContext` compares the latest close with an estimated volume profile made
from the **prior** `lookback` bars, excluding the latest bar. It uses the same
allocation, POC, contiguous 70% value area and tie conventions as the existing
profile. Its reference is independent of the manual VWAP anchor. A close strictly
above VAH is `above value`, strictly below VAL is `below value`, and equality at
either boundary is `inside value`. It requires a valid latest High/Low/Close and
a complete prior window with positive finite volume. Missing evidence yields
`unavailable`, never a neutral zero. The reference dates and levels accompany
every result and the selection-review CSV. An invalid manual anchor may suppress
the manually anchored profile while leaving this independent prior context valid.

This is an Auction Market Theory-inspired **location description**, not a full
AMT strategy: a daily close does not establish acceptance, rejection, initiative
activity, responsive activity or intraday auction sequence. It adds no score or
admission threshold. The Selection review value-area filter narrows the displayed
rows and their CSV export only; the default is all positions. Existing candidate
statuses and original watchlist ranking are unchanged.

The stock evidence heatmap displays the same filtered rows with labels as well
as colour. Blue/orange means above/below a reference, not buy/sell. Unavailable
or unaligned review records have neutral directional cells. This is **not an
order-book liquidity heatmap**. Profile, VWAP and price context are correlated
descriptions and must not be counted as independent confirmations.

### Data-dependent tools still unavailable

The UI lists these as unavailable, with their requirements. No collector,
provider connection or raw microstructure importer has been implemented, and
none of these tools contributes to stock selection yet:

| Tool | Required input and implementation boundary |
| --- | --- |
| Liquidity heatmap | Timestamped bid/ask depth snapshots or sequenced book events, price/quantity units and coverage. Resting orders are not executed trades; cancellations are not selling pressure. |
| Time & Sales | Executed trades with exchange timestamp, instrument, price, size, trade ID, corrections and cancellations. Deduplicate by source identity, not by equal price/time alone. |
| Footprint / delta / order flow | Classified aggressor-side trades at each price and time bucket. Delta = buyer-initiated volume minus seller-initiated volume. Unknown side must remain unknown; daily candle colour is not classification. Reset cumulative delta on an explicit session boundary. |
| Session VWAP | Intraday volume/prices and session calendar. Trade VWAP = sum(price × size) / sum(size); intraday bar calculations remain approximations. Daily rolling anchored VWAP is already supported. |
| Gamma exposure | Dated option chain with gamma and its units, OI, lot size, strike, expiry, underlying price and consistent snapshot times. Gross OI-scaled exposure per 1% move can be defined as sum(gamma × OI × lot size × spot² × 0.01); this is not signed dealer exposure. Signed exposure needs signed positions or a clearly labelled position assumption, never an automatic call-positive/put-negative claim. |
| Market Profile / TPO | Intraday observations, exchange session/calendar, time-block length and price tick size. Count each price bucket once per time block. This measures price visitation by time blocks, not volume. Daily volume profile cannot stand in for it. |

No claim of improved accuracy follows from adding these tools. A future provider
integration must keep instrument, session, units, timestamps, source, coverage,
trade corrections, corporate actions and decision-time availability explicit.
Until a feed is supplied, these tools remain unavailable. Existing tests validate
code and parity, not profitability; the requested 50,000-case study has not been executed.

Primary references for these data definitions (not evidence of an investment edge):
[Sierra Chart Numbers Bars](https://www.sierrachart.com/index.php?l=doc/NumbersBars.php),
[Time & Sales](https://www.sierrachart.com/index.php?page=doc/TimeandSalesWindow.html),
[TPO profiles](https://www.sierrachart.com/index.php?page=doc/StudiesReference/TimePriceOpportunityCharts.html),
[Bookmap heatmap](https://bookmap.com/knowledgebase/docs/KB-SettingUpAndOperating-HeatmapMainChart),
[CME gamma](https://www.cmegroup.com/education/courses/option-greeks/options-gamma-the-greeks),
[CME open interest](https://www.cmegroup.com/education/lessons/open-interest).
OI counts outstanding contracts; it does not identify which participant holds
each side. The signed-dealer-exposure limitation is an inference from that data
definition. Neither these sources nor our tests validate a trading rule.

### Existing daily formulas

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
