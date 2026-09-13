# Rulebook

Every scoring rule in the engine, with its source.

This file exists because the decisions behind the technical score lived only in
code comments and in one conversation. A threshold with no stated provenance
cannot be defended, revised, or retired, because nobody can tell an argued
choice from an arbitrary one six months later.

## How to read an entry

Each rule carries a **status**, and the status is the point of the exercise:

| Status | Meaning |
| --- | --- |
| **Sourced** | A book states the principle and we implement it as stated. |
| **Adapted** | A book states the principle; our parameters differ, and the difference is named. |
| **Convention** | Standard market practice. No book in this repo justifies it. Not wrong — unjustified. |
| **Contradicted** | A book in this repo argues against what we do. Kept for now, with the argument recorded. |

"Convention" is not a criticism and "Contradicted" is not an instruction to
change anything today. They are labels that stop a future reader from assuming
a number was measured when it was inherited.

## Sources

Both books are copyrighted and gitignored, so this file summarises and cites
rather than quotes at length.

- **TSaM** — Perry J. Kaufman, *Trading Systems and Methods*, the copy at
  `Books_TO_study/TSaM.pdf`. Citations use the **printed page number**. That
  copy's PDF page = printed page + 20 (PDF 329 is printed 309), so Chapter 9 at
  printed pp. 369–426 is PDF pp. 389–446.
- **MtM** — Tom Williams, *Master the Markets*, at
  `Books_TO_study/mtm_251058.pdf`. Printed page = PDF page, no offset.

## The limit that applies to every rule below

Both books teach **time-series timing of one instrument**: when to enter and
exit a single market as its own history unfolds. The engine does something
different — it **ranks about a hundred companies against each other at one
instant** and takes the top of the list.

No rule below was validated by its author for cross-sectional ranking. An
indicator can time one stock well and still carry no information about which of
a hundred stocks will outperform the other ninety-nine, because ranking asks a
question about relative dispersion that a timing study never poses.

TSaM p. 313 anticipates the difficulty directly: individual shares are driven by
earnings, regulation, competition and management, their daily volume varies
considerably, and these factors "do not often net out as a clear trend."
Kaufman adds that index-level trading drags individual constituents around by
arbitrage regardless of company news, which makes single-stock price patterns
erratic. His prescription is longer calculation periods, lower-frequency data,
and markets tied closely to their fundamentals.

This is consistent with what the backtest measured: **the technical score does
not rank forward returns** (non-overlapping rank IC −0.001 / +0.026 / +0.004 /
+0.069 at 1/3/6/12 months, nothing surviving multiple-testing correction). The
book predicted the difficulty; the backtest confirmed it. Keep that in view
when reading the per-rule detail — sourcing a rule says the indicator is real,
not that our use of it earns anything.

---

# The technical score

100 points in four blocks, capped per block. Scored only when a company has at
least `SESSIONS_FOR_TECHNICAL_SCORE = 200` sessions of history; below that the
score is `None` rather than a low number, so a short listing is never confused
with a weak company.

## Trend — 40 points

| Rule | Points | Constant |
| --- | --- | --- |
| Close > 200-day SMA | 12 | — |
| Close > 50-day SMA | 8 | — |
| 50-day SMA > 200-day SMA | 8 | — |
| ADX(14) > 25 | 4 | `ADX_TRENDING` |
| Within 15% of the 52-week high | 8 | — |

### Price above its moving average — **Sourced**

TSaM p. 314 gives the basic moving-average signal in one line: be long when
prices are above the average, short when below. Kaufman notes the choice
between acting on an intraday penetration and waiting for the close, and
prefers the close as the more reliable price. We use closing prices throughout,
which matches.

p. 315 compares taking the signal from the **trendline's direction** against
taking it from a **price crossing**. Over ten years of Amazon at five
calculation periods, trendline signals produced 26–37% fewer trades and mostly
better performance (Table 8.2). p. 317 reaches the same conclusion across
Eurodollars and the S&P: longer trend periods were generally more profitable.

We use price-versus-average, the method that tested *worse* in that comparison,
and we do not use trendline direction at all. Kaufman is careful that this is a
single example rather than a general proof, but the asymmetry is worth
recording: the cheaper signal is the one we implement.

### The 50/200 pair and the crossover — **Convention**

Nothing in either book justifies 50 and 200 specifically. TSaM's worked examples
use 5, 10, 20, 40 and 80 days, and settle on 40 as "the fastest one that also
identifies the major price trends" (p. 317). The 50/200 pair is inherited market
convention.

That is not an argument against it — p. 310 notes most trending methods return
about the same over time and differ mainly in risk profile, and p. 317 supports
longer periods being more robust. But if anyone asks why 200 and not 150, the
honest answer today is "because everyone uses 200."

### ADX(14) > 25 — **Convention**, and probably the wrong *shape* of rule

The threshold is unsourced. TSaM p. 387 says the ADX is a by-product of
Directional Movement and defers it to Chapter 23; the opening pages of that
chapter (pp. 1027–1034) cover risk aversion, the efficient frontier, common-sense
risk management and liquidity, with no Directional Movement section. It sits
somewhere later in that chapter, unread. **25 therefore has no citation in this
repo.** Wilder's own convention, like 50/200, is inherited.

The deeper issue is not the number but the role. TSaM p. 310 is blunt: trend
trading works when the market is trending and does not work when it isn't, and
there is no technique that rescues a trending strategy in a sideways market.
That argues for ADX as a **gate on the other trend rules** — if there is no
trend, the moving-average points measure nothing — rather than as 4 points added
alongside them. As written, a company with no trend still banks up to 36 trend
points and merely forgoes 4.

### Within 15% of the 52-week high — **Convention**, and see *Contradicted* below

Neither book states this rule. It is standard momentum practice. MtM pp. 19 and
22 give an argument against one configuration of it; that is set out in
**Where the books contradict us**, below.

## Momentum — 30 points

| Rule | Points | Constant |
| --- | --- | --- |
| MACD histogram > +0.05% of price | 15 | `MACD_FLAT_BAND` |
| RSI(14) > 50 | 15 | `RSI_MOMENTUM_FLOOR` |

### Paying for one measure per concept — **Sourced**

The engine computes four rate-of-change windows and Bollinger %B but scores
neither, on the grounds that RSI, MACD and ROC are all functions of the same
close series and paying for each would count one price move several times.

TSaM pp. 393–394 supports the concern from measurement: comparing momentum, RSI
and the stochastic over an identical 14-day period, Kaufman finds "surprising
similarities among the three" despite very different formulas, with momentum and
the stochastic peaking in the same places. His comparison does not include MACD,
so the support is adjacent rather than exact — but the principle that
same-period oscillators on the same series carry largely the same information is
his, not ours.

### RSI(14), Wilder smoothing — **Sourced**

TSaM p. 386 gives Wilder's formula, RSI = 100 × RS/(1 + RS) with RS = AU/AD over
14 days, and the average-off daily update that our `_wilder_average` implements.
Wilder chose 14 because it is half a natural 1-month cycle. Our period and
smoothing match the source exactly.

### RSI > 50 as a momentum floor — **Convention**

50 appears nowhere in the source. It is the RSI's own midpoint, the level where
14 days of up-closes exactly balance the down-closes, so "RSI > 50" reads as
"more up than down lately." Defensible as a *direction* reading, but it is our
construction, not Wilder's and not Kaufman's.

### RSI > 50 means *continuation* — **Contradicted**, and this is the important one

This was the least documented decision in the engine, so it gets the fullest
treatment.

Awarding points for a high RSI treats it as a **continuation** signal: strength
predicts more strength. The alternative reading is **mean reversion**: a high
RSI marks an extended move due to snap back, which would make the same 15 points
a penalty rather than a reward.

TSaM does not settle this in our favour. The one piece of evidence it offers
(pp. 389–390, from MarketSci Blog, applied to the S&P from 1970 to 2008) is that
**the sign flipped**. Before roughly 1998 the RSI worked as a trend indicator —
when it moved above 90 the S&P continued up. After 1998 it has been "a much
better mean-reverting indicator," and the 2-day RSI traded as a reversion system
(buy below 10, sell above 90) is the version Kaufman presents as working in the
modern era.

So: our continuation reading matches the pre-1998 behaviour of a US index. The
book's own evidence for the period since points the other way. We have never
tested which reading holds for Indian equities, and the engine's null backtest
result is exactly what you would expect if the two effects cancel.

**This rule is a live hypothesis, not a documented finding.** Testing the
mean-reversion sign is the single highest-value experiment available, because it
is one character of code and the backtest harness already exists.

Be precise about the failure mode, because "untested" undersells it. The sign
flipping inside a single market is evidence that the relationship is **not
stable**, which is a stronger and more uncomfortable claim than "we have not
checked this one locally." An indicator whose direction reverses within one
market is not awaiting a local test that would settle it for good — its sign is
regime-dependent, and a fixed +15 for RSI > 50 encodes a constant where the
source documents a variable. So the risk is not merely that the rule is
unproven; it is that the rule is **directionally wrong in some regimes**, and a
single backtest over one span can only report the average of whichever regimes
that span happened to contain.

### RSI > 80 as an exhaustion flag — **Adapted**

Wilder set 70/30 (TSaM p. 386). p. 387 reports Aan's study (*Futures*, January
1985) finding that average RSI tops and bottoms cluster near **72 and 32**, so
half of all 14-day RSI readings fall inside that band — about 0.675 standard
deviations. p. 388 draws the conclusion: 70 and 30 are **too close together** to
be selective overbought/oversold marks and should be moved farther apart, with
1.5 standard deviations a comfortable trade-off, and it is "generally safer to
err on the side of less risk."

Our `RSI_EXHAUSTION = 80` is a widening of 70 in exactly the direction Aan and
Kaufman prescribe. 80 is not itself derived — 1.5σ on Aan's distribution would
land elsewhere — but the *direction* of the adjustment is sourced, which is more
than can be said for most thresholds here.

### MACD flat band, ±0.05% of price — **Convention**

MACD's 12/26/9 parameters are standard and unremarked in either book. The flat
band is ours: it exists so that a steady trend with no acceleration reads as a
real "flat" observation rather than a missing one. Normalising the histogram by
price is necessary for cross-stock comparison, for the same reason ATR is
normalised — see the volatility section.

## Relative strength — 20 points

| Rule | Points |
| --- | --- |
| 3-month relative strength vs benchmark > 0 | 5 |
| 6-month relative strength vs benchmark > 0 | 10 |
| 12-month relative strength vs benchmark > 0 | 5 |

**Convention.** Neither book covers cross-sectional relative strength against an
index; TSaM's "relative strength" discussions concern Wilder's RSI, a different
thing sharing a name. The 6-month emphasis and the 5/10/5 split are ours.

This is the block with the strongest outside literature behind it (the
cross-sectional momentum effect) and the weakest support *in this repo*.

### The two-point form — the one citation this block has, and it is a criticism

`_relative_strength()` is a **two-point** calculation. It takes the stock and the
benchmark close at `pairs[-sessions]` and at `pairs[-1]`, turns each into a
simple return, and subtracts. Everything between the two endpoints is discarded.

TSaM p. 851 lists exactly this form as its first volatility measure — the change
in price over n days — and p. 852 states the objection: such a measure depends
entirely on its two points regardless of the price activity between them, so a
series that moved violently but ended near where it began registers as nothing.

Two honesty notes about that citation. Kaufman is criticising the form as a
*volatility* measure, not as a relative-strength measure; what transfers is the
structural argument about two-endpoint statistics, not a claim he made about
this rule. And a source that criticises the construction does **not** promote
the block out of Convention — the 5/10/5 split, the `> 0` threshold and the
choice of windows remain unsourced. What the block now has is one citation, and
it argues against how the number is built.

The practical consequence: two companies with identical 6-month relative
strength may have arrived there completely differently, one grinding steadily
ahead and one round-tripping a crash. The engine scores them the same and cannot
tell them apart, because the measurement discards the evidence that would.

### Sector-relative strength — a diagnostic, not points

Measured against a broad index, this block cannot distinguish a company that
outran its peers from one carried by a hot sector: a pharma name beating the
Nifty while every pharma name beats it has shown nothing about itself. Since
736899c the engine also reports the 6-month figure minus the median of the
company's own sector peers, bucketed by industry, then coarse group, then
universe, under the same `MIN_MEDIAN_SAMPLE` floor and the same rule that the
basis text must name whichever bucket actually answered.

It earns **no points**, deliberately. The block is already 20 points resting on
convention, and the backtest found the technical score does not rank forward
returns, so a second unsourced scoring rule would be moving the wrong way. It is
computed after scoring, so it structurally cannot reach a score. And nothing
validates it: the A/B cannot test it, for the feedback reason under **Testing
methodology** below. It is a better question asked, not a measured improvement.

It also **inherits** the flaw above rather than repairing it. Both sides of the
subtraction are two-point figures, and a median of two-point figures is still a
two-point statistic, so the peer comparison is exactly as path-blind as the
index comparison. It changes what the two endpoints are measured *against*; it
restores nothing about how the company got there. The company that round-tripped
a crash still scores identically to the one that ground steadily ahead,
whichever yardstick it is held to.

## Volume — 10 points

| Rule | Points | Constant |
| --- | --- | --- |
| Volume > its 20-day average | 5 | — |
| OBV pressure over 20 days > 0 | 5 | `OBV_LOOKBACK` |

### Volume judged relative to a trailing window — **Adapted**

MtM p. 18 is explicit that volume in isolation means very little and must be
read in relative terms, comparing today's volume against **the previous thirty
bars** to judge whether it is high, low or average. Our `volumeRatio20D` does
exactly this with a 20-day window instead of 30. The principle is sourced; the
window length is ours and shorter.

### OBV pressure — **Adapted**, with two warnings from the source

MtM p. 19 gives the two definitions our OBV logic encodes: bullish volume is
rising volume on up-moves and falling volume on down-moves; bearish volume is
the inverse. That is the honest source for signing volume by price direction.

Williams immediately qualifies it twice, and both qualifications apply to us:

1. **Direction alone is not enough.** Knowing the two definitions is "only a
   start"; you must read the **price spread** — the bar's high-to-low range —
   alongside the volume. Our OBV pressure uses close-to-close direction and
   volume, and ignores spread entirely. We implement the half of the idea the
   author says is insufficient on its own.

2. **Smoothing destroys the signal.** p. 19 argues that most technical tools
   average noisy data across an area of the chart, and that the net effect is to
   diminish the variation that matters and hide the volume/price relationship
   rather than highlight it. Our `obvPressure20D` is a 20-day aggregate — the
   exact treatment the source warns against.

Keeping the rule is reasonable; the aggregate is what makes it comparable across
companies. But it should not be described as implementing Williams's method,
because he argues the aggregate is where the information goes to die.

## Flags — never points

| Flag | Trigger |
| --- | --- |
| High Volatility | ATR% of price > 5.0 |
| Overbought | RSI(14) > 80 |
| Deep Drawdown | more than 25% below the peak |

### Volatility describes, it does not score — **Sourced**

This decision is well supported. TSaM opens Chapter 20's volatility treatment
(p. 845) by casting volatility as a **trading filter** — avoid high risk, stand
aside when volatility is too low — and as "the key measure of risk," the dominant
ingredient in structuring a portfolio, pointing forward to the risk-control and
allocation chapters. p. 852 describes ATR as the most popular volatility measure
and a reasonable guideline for future volatility, used to place stops, take
profits, or set the current level of risk.

Throughout, volatility governs **risk and position size**. Kaufman never scores
it as a directional edge. Our choice not to pay points for it — on the grounds
that rewarding low volatility tilts towards sleepy stocks and rewarding high
volatility towards lottery tickets — matches the source's treatment.

### ATR normalised by price — **Sourced**

TSaM pp. 845–846 establishes that the price-volatility relationship is
lognormal: higher-priced instruments show higher volatility, and two stocks at
the same price can still differ sharply. Kaufman flags this as mattering when
sizing positions to equalise risk. Raw ATR is therefore not comparable across a
hundred companies at different price levels, and `atrPct` (ATR ÷ price) is the
right normalisation.

### ATR% > 5.0 — **Convention**, with a sourced replacement available

The 5% level is arbitrary; no absolute threshold appears in the source. TSaM
p. 854 offers a principled alternative, **relative volatility**:

    RV = V(n) / V(m)   where m = f × n, f ≥ 5, and f ≥ 10 is better

— a short-window volatility divided by a long-window one, so each company is
judged against its *own* normal rather than a universal 5%. With our ATR(14),
f = 10 gives ATR(14) / ATR(140). This would replace a made-up constant with a
sourced construction and is a clean, contained improvement.

### Deep drawdown, 25% — **Convention**

Unsourced. Descriptive only, so the cost of it being arbitrary is low.

---

# Where the books contradict us

Three conflicts, stated plainly.

### 1. High volume near the highs may be the top, not strength

The engine pays **+5** for volume above its 20-day average and **+8** for
trading within 15% of the 52-week high. A company can therefore collect 13
points for the configuration MtM p. 22 calls a **buying climax**: exceptionally
high volume, narrow spreads, price pushing into new high ground. Williams reads
that as the moment syndicate traders and market-makers unload into public demand
— the transition from bull to bear, and a *bearish* signal.

He generalises the point on the same page: market strength tends to appear on
down-bars and weakness on up-bars, which he acknowledges runs against natural
thinking.

We take the naive reading. The distinguishing feature is the **price spread**,
which we do not compute — so today we cannot tell a breakout from a climax even
in principle. This is the strongest argument in either book for adding spread to
the indicator set.

### 2. A high RSI means continuation only in the pre-1998 evidence

Covered in full above. The book's evidence for the modern era favours mean
reversion; we score continuation; nobody has tested which holds for Indian
equities.

### 3. Our "improvement" doubled turnover, which the book treats as a cost

TSaM p. 1033 discusses execution cost as a function of order size, volatility and
market volume, and concludes that given two systems with equal gross profits the
investor should prefer **the method with the fewest trades in the most liquid
markets**.

The reworked engine raised annual turnover from **489% to 754%** while improving
out-of-sample return by 2.15 percentage points before tax. At Indian short-term
capital-gains rates that 754% turnover turns the gain negative (−1.57% / −2.81% /
−5.28% at 15% / 20% / 30%). The book's preference and our own tax arithmetic
agree, and they disagree with the change.

---

# Testing methodology

TSaM Chapter 21 sets the standard we should be held to. Recording it here
because two of its requirements are ones we have already broken.

### What the book requires

- **Split in-sample from out-of-sample**, roughly 50/50 (p. 916). Four
  acceptable splits: first half, second half, alternating equal periods, or
  alternating random periods. Random alternating is the most robust, but the
  periods must be **fixed before development starts and never changed** (p. 917).
- **Expect degradation.** Out-of-sample typically returns about half of
  in-sample; an information ratio falling from 2.0 to 1.0 is a reasonably good
  outcome, not a failure (p. 917).
- **Prefer robustness to maxima.** The best parameter set is the most robust,
  not the highest-scoring (p. 919). A wide plateau of profitable parameter values
  is a good result; an isolated spike surrounded by losses is not. An erratic
  result surface means the strategy is unreliable *or the test program has bugs*
  (pp. 924–925).
- **Walk forward** where possible: fit on a window, apply to the next unseen
  window, accumulate only the out-of-sample segments (p. 918).
- **Remember hypothetical results are always optimistic** (p. 1034).

### What we did, and where it fails the standard

**Execution timing — passes, and is sourced.** Our backtest enters at the
*next day's open* after a month-end signal. TSaM p. 317 tests exactly this
choice (entry on today's close vs. next open vs. next close) and finds that for
noisy equity-index markets, waiting for the next open or close is better than
acting on the signal close. Our rule matches the book's finding for the noisier
market type, and it is also the honest choice, since a close-price signal cannot
be executed at that same close.

**Overlapping windows — passes.** We report non-overlapping rank ICs as the
headline and show overlapping figures only to expose their inflation. This was
learned the hard way: a 6-month forward return sampled monthly reuses five
sixths of its window and turned a true t of 0.12 into 2.14.

**Multiple testing — passes.** Bonferroni correction across every horizon
tested, with p-values from Student's t rather than a normal approximation.

**Feedback — FAILS, and the failure is material.**

p. 917 states the rule without qualification: once you have used the
out-of-sample data you cannot fix anything, because that is *feedback*, and the
result is always overfitting.

That is precisely the sequence we followed. The backtest ran and reported a null
result; the engine was then reworked in response; the reworked engine was
re-scored **on the same out-of-sample window**. The headline A/B figure —
out-of-sample 24.78% versus 22.63% equal-weight, **+2.15%** — is therefore
contaminated by construction. It is an in-sample number wearing an
out-of-sample label.

This does not mean the rework was bad. It means **that number cannot be used as
evidence that it was good**, and no amount of re-running changes that. Only data
untouched by the revision can settle it: either a period held back and never
examined, or forward paper-trading from today.

**Robustness mapping — not done.** Every result is a single point. We have never
varied `RSI_MOMENTUM_FLOOR`, `ADX_TRENDING`, `MACD_FLAT_BAND` or the block
weights to see whether performance sits on a plateau or a spike. By pp. 919 and
924–925 that check is what separates a real effect from a fitted one, and it is
cheap — the harness already exists.

**Walk-forward — not done.** We test one fixed split, not a rolling fit-and-apply
sequence.

### A risk rule we do not implement at all

TSaM p. 1032 lists nine common-sense risk principles. The second is to **know
your exit conditions in advance**, with a clear exit criterion for every trade
even when the exact loss cannot be known.

The engine produces **entries only**. It ranks a hundred companies and names a
top slice, with no exit rule, no stop, and no sell discipline beyond the next
month's re-rank. The first principle on the same page — never risk more than 5%
of capital on one position — is likewise absent, as the screener has no concept
of position size.

A screener is not a trading system, and it is legitimate for it to stop at
selection. But the product goal is buy/sell guidance with percentage
allocations, and by this page that goal needs an exit rule and a sizing rule
that do not yet exist anywhere in the codebase.

---

# Open items

Ranked by value, cheapest first where value ties.

1. **Test the RSI sign.** Score `rsi14 < 50`, or drop the RSI points entirely,
   and re-run. One constant, harness already built, and it settles the single
   most consequential undocumented choice in the engine.
2. **Map robustness, not points.** Sweep the live thresholds and look for a
   plateau. Per TSaM p. 925 an erratic surface also catches *test-harness bugs*,
   so this validates the backtest as well as the engine.
3. **Hold data back, permanently.** Fix a window now, never look at it, and
   reserve it for a final test. Until then, no out-of-sample claim survives the
   feedback objection above.
4. **Add price spread.** It is the missing input behind both the buying-climax
   conflict and the incomplete OBV implementation, and MtM treats it as
   indispensable.
5. **Replace ATR% > 5 with relative volatility**, ATR(14)/ATR(140), per TSaM
   p. 854. Swaps an invented constant for a sourced one.
6. **Reconsider ADX as a gate** on the trend block rather than 4 points beside
   it, per TSaM p. 310 — and find the Directional Movement section in Chapter 23
   to source the threshold.
7. **Decide what the relative-strength points are for.** The block now has one
   citation (TSaM pp. 851–852) and it argues against the two-point form the
   engine uses, so the 20 points still rest on convention alone. The peer-
   relative diagnostic added in 736899c asks the better question without scoring
   it; whether it should replace the index comparison rather than sit beside it
   is the part still open. It does **not** fix the path-blindness: both sides of
   that subtraction are two-point figures, so it changes what the endpoints are
   measured against and nothing else. Repairing that needs a different statistic
   altogether — one that reads the series *between* the endpoints, as every
   measure at TSaM pp. 851–852 after the first one does.
