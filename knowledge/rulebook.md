# Rulebook

Every **technical** scoring rule in the engine, with its source — and the
position sizing built on top of it.

Scope, stated because the earlier wording ("every scoring rule in the engine")
claimed more than this file delivers. The **fundamental** half has no entry
here at all: ROCE, growth, governance, promoter holding, pledge, valuation and
the P/E and NPA rules each appear zero times below. That half carries 60% of the
composite and is what actually gates selection, so the uncovered fraction is the
larger one.

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

## The corpus sweep, 2026-09-14

Until this date the **Convention** tag conflated two different claims: *searched
the corpus and found nothing*, and *never searched*. Mostly it meant the second.
`Books_TO_study/` holds 319 documents, 42,745 indexed chunks and a knowledge
graph of 1,519 nodes, with a query tool at `Books_TO_study/_tools/ask.py`, and
nothing in this repository referenced it until `CLAUDE.md` was written. The
earlier sourcing work searched 7 files.

**The count, because the first number quoted was wrong.** A `grep -c Convention`
returns 23. Reading the matching lines gives **15 Convention-tagged sections**:
**10 engine parameters**, which are what this sweep queried, and **5 policies or
facts**, which are not corpus-answerable and were rightly out of scope — the HAC
Bartlett bandwidth (L133), the pre-holdout exploratory policy (L157), the
realised block weights (L253), the relative-strength cell record (L320) and the
measurement-standard correction (L890). The remaining 8 grep hits are the legend,
three cross-references, prose, and two lines stating something is *no longer*
Convention.

### The guardrail this sweep was run under

Searching for support for rules the engine already uses is confirmation-seeking
by construction. `ask.py` states the danger in its own output: *"lexical match
shows the corpus discusses this, it does not by itself make the claim true."*
It was right to: `verify` returned **SUPPORTED ON TOPIC** for the 15%-of-52-week-high
rule, for the MACD band and for the 1%-risk rule, and **all three were false
positives** on common-word overlap. None was counted.

So a passage mentioning a concept did not move a tag; only a span stating the
specific parameter, or an explicitly equivalent rule, did. A contradiction was
recorded with the same weight as support.

### The result

| Rule | Verdict | Moved | Chunk ids |
| --- | --- | --- | --- |
| 50/200 pair, `50 SMA > 200 SMA` | **Sourced** | Convention → Sourced | `The-Complete-Guide-to-Trading.pdf#65`, `#37`, `TA_wrkbk.pdf#56` |
| 50/200 pair, `price > 50 SMA` and `price > 200 SMA` | Convention | no | none — corpus never ties price-vs-MA to these periods |
| Within 15% of the 52-week high | Convention | no | none — no span names a 52-week lookback or any proximity threshold |
| RSI > 50 momentum floor | **Adapted** | Convention → Adapted | `TSaM.pdf#277` (30/70), `#278` (Aan 32/72), `#784`, `TA_wrkbk.pdf#48` |
| MACD flat band ±0.05% of price | **Adapted** | Convention → Adapted | `TA_wrkbk.pdf#50`, `TSaM.pdf#271`, `#230` ("2% of price" band) |
| Relative strength — cross-sectional coverage | **Adapted** | Convention → Adapted | `TSaM.pdf#199`, `#200`, CFA `rf-v2011-n4#19`, `rf-v2016-n4-1#71` |
| Relative strength — 6-month emphasis, 5/10/5 | **Contradicted** | Convention → Contradicted | `TSaM.pdf#605`, `#604`, CFA `rf-v2016-n4-1#71` |
| Relative strength — threshold of exactly zero | **Contradicted** | Convention → Contradicted | `TSaM.pdf#271`, `#268`, CFA `rf-v2012-n4-1#71` |
| ATR% > 5.0 | **Adapted** | Convention → Adapted | `TSaM.pdf#451`, `#456` (ratio 2.0 vs 60-day ATR) |
| Deep drawdown 25% | Convention | no | none — no span names any drawdown level as a rule |
| Volatility window, 252 sessions | **Adapted** | Convention → Adapted | `TSaM.pdf#254` (20 rolling), `#573` (≤25), `#832` (126 already slow) |
| Position cap 10%, sector cap 25% | Convention | no | none — `TSaM.pdf#817`'s 0.10 is an illustrative GA constraint, not an endorsement |
| Risk 1–2% of capital per trade | Convention | no | none — **the zero is re-confirmed**; see below |

**Six of ten moved; four stayed, and now say *searched and not found* rather than
*never searched*.** That distinction is the point of the exercise.

### Three findings worth more than the tag changes

**The relative-strength block is contradicted twice over, and this is new.** The
corpus's momentum horizon is 12 months *skipping the most recent one* — the
engine's plain trailing 12-month includes exactly the month the literature
excludes. And Pring's KST, the only scheme here for weighting several momentum
horizons into one score, is **monotone increasing in horizon length**; the
engine's 5/10/5 is a hump that gives 12 months half the weight of 6. Both are
different numbers for the same purpose, which is a contradiction and not a failed
search. This is the block that carries the project's strongest exploratory cell.

**The 1–2% risk-per-trade finding survives a 2.2× larger corpus.** The earlier
search ran over 165 documents and 19,081 chunks and returned zero; this one ran
over 319 and 42,745 — eleven phrasings, including the exact folklore wordings —
and returned zero again. What the corpus *does* offer for the same job is Ralph
Vince's **optimal f** (`TSaM.pdf#790`), a principled method rather than a round
number. The rulebook was right to refuse the 1%.

**The one promotion is weak and is labelled weak.** `The-Complete-Guide-to-Trading.pdf#65`
states the 50/200 crossover rule verbatim, so it clears the bar — but it is a
corporatefinanceinstitute.com primer whose stated justification is popularity,
*"a favorite of many stock market traders"*. The most rigorous source in the
corpus runs its own two-MA comparison at **40/80** (`TSaM.pdf#257`),
`TA_wrkbk.pdf#43` says outright *"There is no perfect time span"*, and
`TSaM.pdf#650` warns that hunting for "the single best moving average speed" is
the most misused technique in the field. The corpus names 50/200; nothing in it
shows 50/200 is better than its neighbours.


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

## The shipped score has now been measured, and it does not rank returns

Measured 2026-09-13 against real prices: 266,432 rows, 101 tickers, 2015-01-01
to 2026-09-11, monthly rebalance, next-day-open fills, 15 bps a side. This is
the score described below, not a predecessor. Artefacts:
`data-store/reports/backtest_blocks/` (gitignored; re-runs in ~90s from the
cached price file).

**The null, and an honest account of what it can and cannot rule out.** On the
**pre-holdout window** — the data we are permitted to measure — the composite at
1 month scores **IC −0.0033, HAC t −0.16, n = 86, p 1.000** after Bonferroni
across the 20 tests in the family.

**This section previously called that a "powered null, not an absence of
evidence". That was an overclaim, and it contradicted this same section 45
lines below.** The smallest IC this sample could detect at 80% power is
**0.059**. The text further down puts a plausible cross-sectional effect at
roughly **0.02 to 0.05** — so the detection floor sits *above the entire range*
of effects anyone would expect to find. The test cannot see a realistic effect,
and a null from a test that could not have seen one is not a powered null.

The full-span measurement, which includes reserved data and is therefore not
available as evidence, was better powered but not by enough to rescue the claim:
its floor was **0.046**, which reaches only the very top of that same range.

So the supportable statement is narrower than what was here before:

- **No evidence of ranking skill** at any horizon. Nothing clears correction.
- **A small real effect cannot be ruled out.** The measurement is not sensitive
  enough to exclude an IC in the 0.02–0.05 band, which is where a genuine effect
  would most likely live.
- **The portfolio evidence is separate and does not depend on power.** Ranking
  by this score returned 22.52% against 23.29% for equal-weighting the same
  names over the same months — a gap of −0.78pp, 95% CI −7.68 to +5.00. It has
  never beaten equal-weighting on any window measured, though the gap now sits
  well inside its own interval.

The engine is not shown to work, and it is not shown that nothing could. What is
shown is that this construction underperformed the naive alternative.

One month carries the whole argument, and the reason is structural. A 1-month
forward return sampled monthly **cannot overlap**, so every estimator agrees
there by construction (t −0.09 either way, n 130).

**Correction to what this section first said.** It described longer horizons as
a forced choice between reusing (h−1)/h of each window and inflating t, or
keeping one phase offset and collapsing n. That was a false dichotomy, and the
third option is the correct one: **keep every window and use a standard error
that accounts for their dependence.** Overlap is not the defect. Applying an
i.i.d. standard error to overlapping windows is. Newey-West at lag h−1 does
this, and at 12 months it restores the sample from n = 6 to n = 75.

The estimator was validated before it touched real data — checked against
series with *known* overlap structure and confirmed to equal the i.i.d. figure
at h = 1 to four decimals, as it must.

**The bootstrap was NOT the independent conservative check this section once
claimed, and that claim is withdrawn.** Across the 15 overlapping cells the
bootstrap SE is *smaller* than the HAC SE in 10, including every
high-dependence cell. Scored against a series whose true standard error is
known — a moving average of h shocks, which is exactly the structure an
overlapping h-window IC series has — **every estimator here understates it**:
at h=6 the i.i.d. SE by 61%, HAC by 22%, the bootstrap by 25%; at h=12 by 74%,
29% and 38%. No block length fixes the bootstrap (longer blocks make it worse)
and no Bartlett bandwidth fixes HAC (best attainable −17.5% at h=6).

**So every t in this study reads inflated, by roughly a quarter to a third at
the longer horizons.** That direction is unhelpful for any positive finding and
harmless for a null, which is the whole of what this study reports. **Status:
Convention** — the bandwidth stays at h−1 because a few points off a
twenty-point bias is not worth re-opening every figure, and the honest
statement is not that the right bandwidth was found but that these standard
errors understate.

**It corrects in both directions, and the null survives it.** HAC deflates the
cells that overlap had inflated (relative strength at 6 months falls from
i.i.d. t +4.67 to +3.06) and restores power where discarding overlap had
destroyed it. On the pre-holdout window the composite reads:

| Horizon (pre-holdout window) | IC | n | i.i.d. t | HAC t | bootstrap t | p (corrected) |
| --- | --- | --- | --- | --- | --- | --- |
| 1 month | −0.0033 | 86 | −0.16 | −0.16 | −0.16 | 1.000 |
| 3 months | +0.0183 | 84 | +1.07 | +0.95 | +1.02 | 1.000 |
| 6 months | +0.0504 | 81 | +3.06 | +2.15 | +2.24 | 1.000 |
| 12 months | +0.0434 | 75 | +2.31 | +1.81 | +1.91 | 1.000 |

More observations with a correct standard error bought *less* significance, not
more, because the all-windows point estimate is the smaller one. Nothing clears
correction. The conclusion did not move; the best estimate did, and it moved
against us.

### Everything measured on the pre-holdout window is exploratory

**Status: Convention, and a policy rather than a rule about the engine.**

The Bonferroni divisor in `backtest.py` is 20, which is correct for one
invocation. But this same window has now been measured with the shipped score,
with `--rsi-flip`, and with the Tier 1 variants — roughly **80 cells against one
dataset**, and the divisor knows about 20 of them.

A divisor that grows with an open-ended search is unwinnable, because the
denominator is unknowable in advance and because it makes the divisor itself
negotiable — which is exactly the move refused above for relative strength at 6
months. So the correction is not chased. Instead:

1. **Every pre-holdout figure is exploratory and labelled as such.** No
   exploratory cell is called significant, whatever its p. Multiplicity
   correction applies only within the single pre-registered final test.
2. **The search count is stated wherever an exploratory cell appears.** ~80
   cells, and that is a **lower bound**: design choices are degrees of freedom
   too — the sector-bucket floor of 3, the neutralisation scheme, the turnover
   window, the 200-session gate, the winsorisation tail. The garden of forking
   paths is wider than the cell count.

**The gap this policy does NOT close, stated plainly because it is the one that
matters.** Labelling the exploration stops us calling it significant. It does
not stop the exploration from choosing *what gets tested on the holdout*. If
four variants are measured and the best goes forward, the final test is not a
clean test of a hypothesis — it is a test of the winner of an 80-cell search.
The selection effect survives the relabelling, because it operates through
which variant reaches the holdout rather than through what is said about the
p-values.

That does not make the holdout worthless. It narrows what it answers:

- **Not:** is there a real effect here. The holdout cannot answer that; the
  subject was chosen because it looked good.
- **But:** the variant we selected — does it hold up on data nobody has seen?

The second is decision-relevant and the holdout answers it cleanly. It must be
*stated* as the second, because "our pre-registered test came back positive"
will be read as the first.

Three things must therefore be written down **before the holdout is touched**:

- **The form of the test, not just the variant.** One variant, one horizon, one
  statistic means the divisor is 1. A variant across four horizons and five
  blocks puts it back at 20 and resets this whole argument. Name the exact cell.
- **The selection rule, in advance.** "The variant with the highest paired IC
  difference at 1 month" is a rule. "The one that looked best" is not, and only
  the first lets a reader judge what the holdout result means.
- **The cumulative count, including variants run and not reported.**

Below is the earlier **full-span** measurement, kept because it is the
better-powered version and dropping it would mean hiding the stronger
measurement rather than the weaker one. It includes reserved data and is
therefore **not available as evidence**; it also discards overlapping windows
rather than correcting their standard error, which is the method superseded
above. Each row repeats both facts, because this table sits directly beneath a
pre-holdout one and the nearest window cue a reader has is otherwise the wrong
one:

| Horizon (historical) | IC (non-overlapping) | t | n | p (Bonferroni/20) | detectable at 80% |
| --- | --- | --- | --- | --- | --- |
| 1 month — full span, incl. reserved, not evidence | −0.0015 | −0.09 | 130 | 1.000 | 0.046 |
| 3 months — full span, incl. reserved, not evidence | +0.0481 | +2.46 | 43 | 0.358 | 0.056 |
| 6 months — full span, incl. reserved, not evidence | +0.0278 | +0.82 | 21 | 1.000 | 0.100 |
| 12 months — full span, incl. reserved, not evidence | +0.0843 | +2.05 | 10 | 1.000 | 0.128 |

**Read the long horizons as unmeasurable, not as weak evidence.** At 12 months
the independent sample is n = 10 and cannot detect an IC below 0.128 — several
times any plausible cross-sectional effect, which is roughly 0.02 to 0.05. A
null there says the test could not see, not that nothing is there. The 3-month
figure is the most quotable number in the run and it is an artefact: its sign
**flips** against the overlapping estimate (+2.46 versus −0.11), which is the
signature of a phase offset rather than a signal.

### No block carries it

A near-zero total is equally consistent with four dead blocks and with two that
cancel. Ranking on each subtotal alone settles it. At 1 month — the cleanest
horizon, though not a well-powered one — every block sits inside its own
detection floor. Pre-holdout window, HAC:

| Block (pre-holdout, 1 month) | IC | t | detectable at 80% |
| --- | --- | --- | --- |
| Trend (40) | +0.0032 | +0.14 | 0.062 |
| Momentum (30) | −0.0277 | −1.67 | 0.047 |
| Relative strength (20) | +0.0300 | +1.56 | 0.055 |
| Volume (10) | −0.0231 | −1.66 | 0.040 |

**The stated block weights have never been the realised ones.** `TECHNICAL_BLOCK_MAX`
reads 40 / 30 / 20 / 10, but what a block contributes to a *ranking* is the
cross-sectional spread of its subtotal, not its cap. Measured over 87 pre-holdout
dates and 7,621 ticker-observations, the shipped points model realises
**36.1 / 32.0 / 22.7 / 9.2**. Trend is the block that loses most, because its five
features are near-collinear and a weighted sum of correlated features spreads less
than its cap implies; volume's two are not, so it holds closer to its share.

**Status: Convention, and a fact about the shipped score rather than about any
variant.** Nothing is changed in response. It is recorded because "the trend block
carries 40% of the technical score" is the natural reading of the constant and it
is not what the constant does.

**Correction, two claims.** This paragraph previously read "Four flat blocks",
unqualified, and the sentence above the table claimed those floors "are
themselves at or above the range where a real effect would sit". Both were
stated more strongly than the data supports, in the direction that flatters the
work — the same species as the "powered null" overclaim retracted above.

*On the floors:* a plausible cross-sectional effect is 0.02–0.05. Two of these
four floors sit above that range entirely (trend 0.062, relative strength
0.057) and two sit **inside** it (momentum 0.047, volume 0.040). So for momentum
and volume the test could have seen an effect at the top of the plausible range,
though not a typical one. "At or above the range" was false for half the table.

*On the blocks:* four flat blocks **at one month**. Nothing is being cancelled
out at that horizon, so no reweighting of the 1-month signal recovers an edge
that is not there — which is what makes `technical_weight_pct = 40` unearned
rather than merely unvalidated. That is a 1-month conclusion and it does not
extend, because at six months one cell does clear its floor.

### The cell that used to clear its floor, and no longer does

**As of 2026-09-14 no cell in this project clears its own detection floor at any
horizon — zero of twenty.** Relative strength at 6 months was the last one, and
it cleared by 1.3%. Adopting the sourced skip-month window (CFA
`rf-v2016-n4-1#71`) changed what relative strength measures, and the cell now
reads IC **+0.0781** against a floor of **0.0880** — it misses by 0.0100.

**The removal came from a citation, not from a measurement chosen to remove it.**
That direction matters: the change was adopted because a book states the
construction, and the cell fell below its floor as a consequence. Had the
sequence run the other way — adopt because the cell improved — it would have
been fitting.

The section is kept because omitting a cell while publishing "four flat blocks"
is how an affirmative negative becomes an overclaim, and because the pre-change
figures are part of the record.

| Relative strength | IC | n | df | HAC t | boot t | floor | p (Bonferroni/20) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 month — pre-holdout, overlapping | +0.0300 | 86 | 85 | +1.56 | +1.56 | 0.0547 | 1.000 |
| 3 months — pre-holdout, overlapping | +0.0471 | 84 | 27 | +2.12 | +2.21 | 0.0641 | 0.861 |
| **6 months — pre-holdout, overlapping** | **+0.0781** | 81 | 12 | **+2.68** | **+2.97** | **0.0880** | **0.402** |
| 12 months — pre-holdout, overlapping | +0.0525 | 75 | 5 | +2.08 | +2.41 | 0.0859 | 1.000 |

**The df column is the correction that moved these numbers.** Until 2026-09-14
the HAC t was referred to df = n−1, which is the df of an i.i.d. mean. On
overlapping windows consecutive observations share (h−1)/h of their span, so
the independent count is n/h — and n//h reproduces the non-overlapping series
length exactly at every horizon here (84//3=28, 81//6=13, 75//12=6). At 6
months that took the raw p from 0.0030 to 0.0099 and the corrected p from
0.060 to 0.198. **Status: Adapted.** It is a conservative proxy, not the
textbook fix: fixed-b asymptotics (Kiefer & Vogelsang 2005) give a nonstandard
limiting distribution with fatter tails than Student's t at any df, so the
honest p sits above even this one.

The 6-month bootstrap interval is +0.024 to +0.126 and still excludes zero; HAC
SE is 0.0291 at lag 5; raw p is 0.0201. It no longer clears its floor at all.

**Why this is more likely noise.** It does not clear correction. Under the null
the chance that *some* cell out of twenty looks at least this strong is about
**33%**. Twenty understates the search: this same window has been measured with
the shipped score, with the RSI sign flipped, and with four ladder rungs —
roughly **100 cells against one dataset**, at which the figure is **80%**. No
sibling horizon clears its floor either; 12 months misses by 0.0334.
Nothing here has been tested on data that was not already used to find it.

**And the standard error itself understates.** Every estimator in this study is
biased low, scored against a series whose true standard error is known: at six
months the i.i.d. SE by 61%, HAC by 22%, the bootstrap by 25%. No block length
fixes the bootstrap and no Bartlett bandwidth fixes HAC. So this t is inflated
rather than deflated, and taking the measured bias at face value would put the
corrected p near **0.53**. See `_stationary_bootstrap_se`.

**Status: Convention — recorded, not adopted.** No parameter changes in response
to this cell, and it is not to be investigated further on pre-holdout data:
looking harder at the window that produced it cannot distinguish the two
explanations. The one clean test belongs to whichever variant survives Tier 1.

**These twenty tests are not twenty independent looks, and that fact cuts both
ways.** The blocks share constituents and the horizons overlap, so the tests are
positively dependent. One consequence is that Bonferroni is conservative as a
divisor, and a dependence-aware correction would land below 0.402. The other,
and the one that matters here, is that relative strength at 6 months is not a
lone survivor among twenty independent looks: it is one face of a correlated
cluster that also holds the same block at 3 months (+2.34) and at 12 months
(+2.77). Its sign consistency across all four horizons is therefore not four
corroborating results — it is closer to one result seen four times.

Both consequences follow from the same fact, and reporting only the divisor half
is what turns a caveat into special pleading for the one cell that benefits. No
principled redivision admits this cell without also admitting the ones already
dismissed, because the dependence that would shrink the divisor is the same
dependence that makes these tests redundant rather than numerous. The family
size and the correction were fixed before this cell was singled out; changing
either now is choosing the test after seeing the answer.

**Two arguments against it that do not depend on the divisor at all.**

- *It is the cell with the largest inflation in the run.* Its i.i.d. t at 6
  months is +4.21 and HAC deflates it to +2.68 — a drop of 1.54, the largest
  anywhere in the study. What remains is what survived the biggest discount, not
  a figure that never needed one.
- *It diluted when the reserved years were added.* **These two figures are from
  the superseded pre-skip-month engine and cannot be recomputed like for like**,
  because the full-span artefact would have to be regenerated and that spends the
  reserved window. As measured then: pre-holdout +0.0784; over the full
  2015–2026 span, +0.0485. But this was **not** a relative-strength
  signature: 12 of the 16 block-horizon cells are larger pre-holdout than on the
  full span. The pre-holdout window is simply the friendlier half for this score
  generally, which is what one expects if these estimates are period-specific
  rather than persistent. (Full-span figures include reserved data and are cited
  here as caution against over-reading, never as evidence. No parameter changes
  in response to either number.)

**Distrust the overlapping column specifically.** Sign flips fire on composite
3m, momentum 3m, momentum 6m and volume 3m. Worse, the flag catches sign
changes but not magnitude collapse of the same sign: relative strength at 6
months reads t +3.52 overlapping and +0.91 independent, and at 12 months +3.42
against +2.06. Read the overlapping column alone and relative strength is the
block that works; it is the block with the largest inflation.

### The portfolio, and two numbers that are not findings

On the **pre-holdout window**, with every column covering the months the
strategy actually traded, top 20 against equal-weighting the same 100 names is
**22.52% versus 23.29%** over the whole span — a gap of **−0.78pp**, 95% CI
−7.68 to +5.00, p 0.794. Turnover **689%**. It has never beaten equal-weighting
on any window measured, and the gap is now well inside its own interval.

The gap's interval straddles zero on the whole pre-holdout span (95% CI −11.47
to +2.32, p 0.217) and excludes it in-sample only by five hundredths of a point
(−13.79 to −0.05, p 0.049), which does not survive correction for the number of
tests run. So the supported claim is the **direction**, not the magnitude: on
every window measured, this score has never beaten equal-weighting in sample.

The earlier full-span figures — 20.40% versus 21.15%, 4 of 12 years, 754%
turnover — are superseded twice over and are **not evidence**: they include
reserved data, and their benchmark column covered 139 months against the
strategy's 130, which flattered the gap roughly five-fold.

The out-of-sample **24.78% versus 22.63%** is not evidence. That window was
already used to revise this engine, and TSaM p. 917 is explicit: once the
out-of-sample data has been used you cannot fix anything, because what comes
back is overfitting. At 754% turnover it is negative after Indian STCG in any
case. The 3-month t +2.46 is not evidence either, for the reason above.

### The RSI sign was tested both ways. Neither is adopted.

Open item 1 asked whether the RSI comparison is backwards — whether scoring
`rsi14 < 50` (mean reversion) beats `> 50` (continuation). Both were measured
on the same data, via a `--rsi-flip` switch in the backtest; `RSI_MOMENTUM_FLOOR`
itself was never touched, because changing the shipped comparison would be
adoption rather than measurement.

> **Provenance of every figure in this section, and why none of them may be
> quoted alongside the ones above.** This experiment ran on 2026-09-13 over the
> *full* 2015–2026 span, before the holdout was reserved and before the
> benchmark was aligned to the strategy's traded months. So its numbers carry
> both defects the sections above were rewritten to remove: they include
> reserved data, and their equal-weight column covers 139 months against the
> strategy's 130. They are kept because they record a decision — both signs
> tested, neither adopted — and that record is worth more than the figures.
> Re-running it on the pre-holdout window is the only way to get comparable
> numbers, and nothing turns on having them.

Composite, non-overlapping, shipped → flipped. The window is repeated in every
row rather than stated once above the table, so no row can be lifted without
carrying the basis it was measured on:

| Horizon (full span, pre-alignment) | Shipped | Flipped | Detectable at 80% |
| --- | --- | --- | --- |
| 1 month — full span, incl. reserved | −0.0015 (t −0.09) | +0.0059 (t +0.39) | 0.046 |
| 3 months — full span, incl. reserved | +0.0481 (t +2.46) | +0.0430 (t +2.01) | 0.056 / 0.061 |
| 6 months — full span, incl. reserved | +0.0278 (t +0.82) | +0.0081 (t +0.26) | 0.100 / 0.092 |
| 12 months — full span, incl. reserved | +0.0843 (t +2.05) | +0.0520 (t +1.18) | 0.128 / 0.136 |

At the only powered horizon both signs sit inside the detection floor. **No
cell in either run clears Bonferroni**, across all 40 tested. The flip does not
make the score rank.

**The momentum reversal is mechanical, not empirical.** In the momentum block
the 12-month IC goes from +0.0848 (t +2.43) to −0.1055 (t −3.12), which looks
like the strongest signal anywhere in this work. It is an artefact of the
experiment's own construction: flipping the comparison inverts part of that
block by definition, so shipped and flipped momentum are partly the same series
negated. A sign reversal there is guaranteed by the arithmetic. The surprising
result would have been no change. It also rests on n = 10 against a 0.108 floor.

**The portfolio difference is the number that will tempt someone, so it is
written into the sentence that refutes it rather than set out in a table.**
Over the full 2015–2026 span, on 130 strategy months against a 139-month
benchmark and with reserved data included — so on a basis nothing else in this
file uses and none of it comparable to the figures above — flipping the sign
returned 22.88% against the shipped 20.40% and equal-weighting's 21.15%,
in-sample 20.46% against 17.28% and 20.18%, with turnover falling from 754% to
720%.

Those numbers are in prose deliberately. As a table they were a self-contained
block that survived copy-paste while the caveat above them did not, which is the
same defect this file rejects elsewhere: a warning that can be separated from
the number by copying one row is not a warning. The defect now travels inside
the same sentence as the figure.

It reads like a discovery and is not one. The 1-month rank IC under it is
**+0.0059** — no ranking signal. With an
IC of essentially zero the top-20 composition is noise, so what changed is
which twenty names the noise happened to select, plus whatever volatility tilt
comes from preferring low-RSI stocks. A portfolio result with no IC beneath it
is a story about twenty draws, not about a rule.

And it is a second variant measured on a window already spent revising this
engine, which makes adopting it the feedback failure twice over. Both signs are
recorded; neither is adopted; the shipped comparison stays where it is until
data nobody has examined says otherwise.

**Historical note, so nobody re-derives it.** An earlier null (IC −0.001 /
+0.026 / +0.004 / +0.069) circulated as this engine's result. It was not:
commit `40f20e2` says it measured "the five-check score this replaced (commit
f62a110)", and `9939ba7` replaced the scoring four minutes before that commit
landed. Those figures describe a predecessor. The ones above describe what
ships.

Keep all of this in view when reading the per-rule detail — sourcing a rule
says the indicator is real, not that our use of it earns anything.

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

### The 50/200 pair and the crossover — **Sourced** (crossover only), **Convention** (the two price tests)

Nothing in either book justifies 50 and 200 specifically. TSaM's worked examples
use 5, 10, 20, 40 and 80 days, and settle on 40 as "the fastest one that also
identifies the major price trends" (p. 317). The 50/200 pair is inherited market
convention.

That is not an argument against it — p. 310 notes most trending methods return
about the same over time and differ mainly in risk profile, and p. 317 supports
longer periods being more robust. But if anyone asks why 200 and not 150, the
honest answer today is "because everyone uses 200."

### ADX(14) > 25 — **Sourced** (threshold), and probably the wrong *shape* of rule

The threshold is unsourced. TSaM p. 387 says the ADX is a by-product of
Directional Movement and defers it to Chapter 23; the opening pages of that
chapter (pp. 1027–1034) cover risk aversion, the efficient frontier, common-sense
risk management and liquidity, with no Directional Movement section. It sits
somewhere later in that chapter, unread.

**Correction: 25 does have a citation, and it is exactly 25.** TSaM p.1066, in
the Directional Movement section that the paragraph above assumed was unread,
gives Ruggiero's rules for using the ADX as a trending indicator, beginning:
"1. If ADX crosses above 25, the market is trending." The same list adds that
below 20 the market is consolidating — so the 20/25 pair is a documented band,
not a single line, and our rule implements only its upper half.

This promotes the threshold from Convention to **Sourced**, and it was found by
one grep against text already sitting extracted on disk. Worth recording how
long it stood as "unsourced": the claim survived because nobody searched past
the pages they had already opened, which is the same failure this file records
twice more below.

Wilder's own convention, like 50/200, remains inherited for the *period* (14);
only the threshold is now sourced.

The deeper issue is not the number but the role. TSaM p. 310 is blunt: trend
trading works when the market is trending and does not work when it isn't, and
there is no technique that rescues a trending strategy in a sideways market.
That argues for ADX as a **gate on the other trend rules** — if there is no
trend, the moving-average points measure nothing — rather than as 4 points added
alongside them. As written, a company with no trend still banks up to 36 trend
points and merely forgoes 4.

### Within 15% of the 52-week high — **Convention**, searched and not found, and see *Contradicted* below

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

### RSI > 50 as a momentum floor — **Adapted**, and the corpus names different levels

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

### MACD flat band, ±0.05% of price — **Adapted**, the method is endorsed and the value is ours

MACD's 12/26/9 parameters are standard and unremarked in either book. The flat
band is ours: it exists so that a steady trend with no acceleration reads as a
real "flat" observation rather than a missing one. Normalising the histogram by
price is necessary for cross-stock comparison, for the same reason ATR is
normalised — see the volatility section.

**The method is endorsed and the value is ours by a factor of forty.**
`TA_wrkbk.pdf#50` states the engine's exact qualitative rule — ignore the signal
while the indicator hugs its reference line — and `TSaM.pdf#271` states the same
for momentum crossing zero, so the concept of a dead band is not this project's
invention. `TSaM.pdf#230` then lists **2% of price** as one of four legitimate
band constructions. Ours is **±0.05% of price**.

**That is a 40× gap, and it is the largest divergence between a sourced method
and our parameter anywhere in this file.** A band forty times narrower admits
forty times more of what the source calls noise, which means the MACD award
fires far more often than the cited construction would allow. Nothing is changed
in response — the replacement value is not measured here and adopting 2% because
a book names it would be swapping one unvalidated constant for another — but the
ratio is now stated rather than left for a reader to compute.

## Relative strength — 20 points

| Rule | Points |
| --- | --- |
| 3-month relative strength vs benchmark > 0 | 5 |
| 6-month relative strength vs benchmark > 0 | 10 |
| 12-month relative strength vs benchmark > 0 | 5 |

**Adapted on coverage, Contradicted on the window, the threshold and the SHAPE of
the weighting** — see the corpus sweep. TSaM and the CFA monographs do cover
cross-sectional momentum; what they do not cover is this construction. Neither
book covers cross-sectional relative strength against an index; TSaM's "relative
strength" discussions concern Wilder's RSI, a different thing sharing a name.

**The 5/10/5 split is contradicted in shape, not merely unsourced, and the
distinction matters.** `TSaM.pdf#605` describes Pring's KST, the only scheme in
the corpus for combining several momentum horizons into one score, as
**step-weighted in proportion to its period** — monotone increasing in horizon
length. Ours is a hump: 5 / 10 / 5 at 3 / 6 / 12 months, which hands the
12-month window **half** the weight of the 6-month. The corpus does not merely
fail to justify our profile; it states the opposite ordering.

**Recorded, not acted on.** Changing the split would be a scoring change with no
source for the replacement numbers — KST's proportional weights are not a set of
three integers we could lift — so swapping an unsourced hump for an unsourced
ramp buys nothing but motion.

### The skip month — **Sourced** for the 12-month leg, adopted 2026-09-14

**The engine now measures relative strength from t−h to t−2, not t−h to t−1.**
`RELATIVE_STRENGTH_SKIP_SESSIONS = SESSIONS_1_MONTH` in `engine.py`, mirrored in
`screenerEngine.ts`. The start of each window stays anchored at t−h and only the
end moves back, so the 12-month leg is the 2–12 construction; shifting the whole
window would give t−13 to t−1, a different quantity.

**The citation is the justification, and it covers one leg of three.**
CFA Institute Research Foundation Monograph `rf-v2016-n4-1#71`: *"The momentum
factor is based on the prior 12 months of returns, excluding the most recent
month (2–12)."* The corpus was searched for a 3-month or 6-month equivalent and
**has none**. So the 12-month leg is **Sourced**; the 3- and 6-month legs are an
**extension by consistency, with no citation**, and that is stated here rather
than allowed to shelter under the 12-month source.

**The measurement is not the reason, and this matters.** Rung D of the Tier 1
ladder measured the skip and it bought **+0.0053 IC at 6 months** — far inside
the detection floor, and nothing at any horizon cleared correction. The change is
adopted because a source states the construction; the measurement only shows the
change **costs nothing**. Adopting because a number improved would be fitting on
data already used, which is the feedback failure this file exists to record.

**The pre-registered cell is untouched, verified rather than argued.** The one
cell in `knowledge/preregistration.md` is the momentum block at 1 month, rung C.
Momentum is MACD + RSI and neutralisation residualises on sector and liquidity,
so nothing in that path reads relative strength — but that is reasoning, so it
was checked. Regenerating rung C on the changed engine leaves momentum, trend and
volume **bit-identical** and the scoreable universe identical, while relative
strength moves from +0.0413 to +0.0485 at 6 months, proving the change is live.
The pre-registered IC of −0.040666455273968276 and HAC t of −3.0475295241371669
are unchanged to every digit stored.
`test_relative_strength_cannot_disturb_the_preregistered_cell` asserts it, with a
guard that the fixture actually moves relative strength.

**A near-miss worth recording.** The first attempt at that verification compared
the artefact **to itself**: the regeneration had crashed on a stale keyword left
by renaming the flag, the old `results.json` was never overwritten, and the
"bit-identical" result included relative strength — which cannot be true if the
change is live. It was caught by noticing that impossible row, not by the exit
code, because the exit code read was the background wrapper's rather than the
Python process's. The rule this file already carries was violated in the act of
verifying a change: read the exit code from the command that produced it.

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

### ATR% > 5.0 — **Adapted**, and the sourced replacement is now named

The 5% level is arbitrary; no absolute threshold appears in the source. TSaM
p. 854 offers a principled alternative, **relative volatility**:

    RV = V(n) / V(m)   where m = f × n, f ≥ 5, and f ≥ 10 is better

— a short-window volatility divided by a long-window one, so each company is
judged against its *own* normal rather than a universal 5%. With our ATR(14),
f = 10 gives ATR(14) / ATR(140). This would replace a made-up constant with a
sourced construction and is a clean, contained improvement.

### Deep drawdown, 25% — **Convention**, searched and not found

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

**Benchmark alignment — FAILED silently until 2026-09-13.** A benchmark must
cover exactly the months the strategy traded. Ours did not: the strategy cannot
trade until enough companies clear
`SESSIONS_FOR_TECHNICAL_SCORE`, while equal-weighting can trade from the first
month in the file, so the performance table compared a strategy CAGR over 86
months against an equal-weight CAGR over 95 — and over 130 against 139 on the
full span. The index column had the same defect.

**Status: Convention, and a correction rather than a sourced rule.** No book in
this repository states it; it is arithmetic. A CAGR is a function of its
period, so differencing two CAGRs computed over different periods measures the
periods as much as the strategies.

The cost was not small and it ran in the flattering direction. **The figures
below are the superseded pre-skip-month engine's and are kept as the record of
what the alignment fix changed; restating them on the current engine would
falsify the comparison they exist to document.** Held to one window — the
pre-holdout span, so the comparison was like for like — the unaligned figures
gave 19.41% against 20.17%, a gap of **−0.76pp**. Aligned, the same window gave
19.41% against 23.29%, a gap of **−3.89pp**: about five times wider. The strategy looked better than it was because its benchmark was
credited with months the strategy could not trade.

The first draft of this paragraph took the −0.76pp from the full span and the
−3.89pp from the pre-holdout window and called the ratio five-fold. Same
answer, invalid route — and differencing across mismatched periods is the exact
error this entry exists to record. Worth leaving visible: knowing the rule does
not stop you breaking it in the paragraph where you state it.

Two details worth keeping, because both are about how the defect survived:

- **The disclosure was already present and did not work.** The table carried a
  `Months` row reading `86 | 95 | 95` directly under a heading naming 86
  rebalances. Two people extracted every other statistic from that table without
  registering it. Adding a warning would have left the artefact contradicting
  itself; aligning the data removed the contradiction. Prefer fixing the
  artefact to fixing the reader.
- **The check that now guards it** asserts both that the month counts are equal
  across all three columns *and* that subtracting the table's CAGR row equals the
  independently computed paired figure to twelve places. Before alignment those
  two numbers disagreed five-fold, and the more prominent one was wrong.

**Overlapping windows — passes in one tool and FAILS in the other.** The claim
as originally written was true of `python/ab_compare.py`, which computes
`ic_series(h, 1)` and `ic_series(h, h)` and reports the non-overlapping figure
as the headline. It is **not** true of `python/backtest.py`, the harness a
reader is far more likely to run: `decile_study` iterates
`for index, signal_date in enumerate(rebalances)` and takes `future = index +
horizon` — stride 1, overlapping, for every horizon — and the string
`ic_series` does not appear in that file at all. Its Bonferroni correction then
divides by the four horizons only, not by the far larger effective count that
overlapping sampling implies.

So the discipline is real, and it lives in the tool that did not produce the
headline. The underlying lesson stands and was learned the hard way: a 6-month
forward return sampled monthly reuses five sixths of its window and turned a
true t of 0.12 into 2.14.

**Neither tool runs in CI.** `run_checks.sh` contains zero references to
`backtest` or `ab_compare`, against a control of three for `test_python`. The
only measurement of whether this engine predicts anything sits outside the gate
that everything else must pass, so it could silently break and nothing would
notice.

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
allocations, and by this page that goal needs an exit rule and a sizing rule.

**The sizing rule now exists** and is set out below. The exit rule still does
not: what follows places a stop in advance, which is p.1032 principle 2, but
nothing yet acts on it, because the engine has no idea what anyone owns.

---

# Position sizing

The best-sourced part of this system, and it is important to read that the right
way round.

This section has real page numbers, a worked table and a decision sentence,
while the scoring layer beneath it is roughly half Convention and was measured
to have no ranking edge. The citations here lend that layer **nothing**. The
argument runs the other way, and it is stronger stated plainly: equal risk is
what the book prescribes *precisely because* the selection underneath is
unproven.

### Why equal risk — **Sourced**, and the condition is ours

TSaM p.1054: "Unless you can select which trades are most likely to be better
than another, equal risk is the most conservative approach." p.1103 gives three
ways to allocate equal risk — equal dollar amounts, equal risk by annualised
standard deviation, equal risk by average true range — and states that **ATR is
the best measure when high, low and closing prices are available**, annualised
standard deviation when only closes are, and that equal dollar weighting, "once
an industry standard, is rarely used."

Be exact about why p.1054's condition applies to us. The backtest measured the
**technical** score and found no ranking edge. The fundamental half has never
been tested at all. So what we have is **no demonstrated selection ability** —
not a demonstrated *absence* of it. Those are different claims and only the
weaker one is ours. An untested half fails p.1054's condition exactly as an
edgeless one does, so equal risk follows for both halves; but nobody should
later cite this file as having measured something about fundamentals that
nobody measured.

### The weights — **Sourced**, reproduced from the book's own table

Table 24.1 (p.1104) works it: "% of smallest" is `min_vol / own_vol`, and
"Scale" divides each by their total. So **weight ∝ 1/volatility, normalised**.
Both engines are tested against that table's printed figures rather than
against each other, so a shared mistake fails the test instead of passing it.

### Target volatility, 12% — **Adapted**, and a human chose it

p.53 gives 12%, calling it "a modest risk level", and says every result in the
book is shown at it. p.1048 gives "typically about 15%" and then calls 15%
aggressive in its own worked example. The book offers a range; **Amogh chose
12%** from it. Not a derivation, and a later reader should see both the range
and the chooser.

Long-only and unleveraged, the target can only reduce exposure, never raise it —
which is also Kaufman's advice at p.1092, to use such methods only to reduce
leverage.

### Measuring the portfolio, not averaging its parts — the costly detail

Deployment needs the portfolio's volatility, and the obvious shortcut is to
average the constituents' volatilities weighted by size. That shortcut is
wrong, not merely imprecise. Measured on 19 real Nifty 100 names:

| | portfolio volatility | invested at a 12% target |
| --- | --- | --- |
| Actual, from the portfolio's own return series | **13.0%** | **92.5%** |
| Weighted average of the parts | 22.8% | 52.7% |

Average pairwise correlation was **0.24**, not the ~0.5 assumed. The shortcut
would have parked nearly half the account permanently while looking
conservative. The engine therefore builds the weighted portfolio's daily return
series and takes its standard deviation — arithmetically `sqrt(w' COV w)`
without forming a covariance matrix, which also keeps it to one sequential sum
that both engines can agree on bit for bit.

Caveat recorded rather than buried: that 0.24 is one calm year. p.1101 says
outright that "diversification can disappear under stress", and when
correlations rise the measured portfolio volatility rises with them and
deployment falls. That is the mechanism working, not failing.

### The measurement window, 252 sessions — **Adapted**, and the corpus argues for shorter

No book here fixes a window length, so 252 is ours, chosen to match the
annualisation used everywhere else.

It is recorded as its own entry because the first implementation had no window
at all, and the bug was invisible in every test. The price file starts at
`HISTORY_START` (2015), so the sessions common to all holdings ran to about
**2890** — eleven and a half years — and the deployment fraction was therefore
an eleven-year average volatility. Every unit test passed, both engines agreed
exactly, and the number was wrong in the way that mattered most: **deployment
is supposed to fall when volatility rises, and an eleven-year mean cannot
rise.** The crisis brake, which is the entire reason a 12% target is worth
having over no target, was inert.

It also mismatched the rest of the pass. ATR(14) and `volatility30D` are
short-window measures, so the deployment fraction was being computed on a
completely different timescale from the weights it scaled.

On the real nine-name run the fix moved portfolio volatility from 17.1% to
14.9% and deployment from 70.3% to 80.6%. It was caught only by reading the
`basis` string in an actual run output — "2890 sessions common to 9 holdings" —
and noticing the number was impossible for a one-year download. No test would
have found it, because every test fixture was shorter than the window that was
missing.

### The 5% risk ceiling — **Sourced**, and it never binds

p.1032 principle 1: "No trade should ever risk more than 5% of the invested
capital." A ceiling on **risk**, not on position size; the two coincide only
when the stop sits 100% away. At a 6% stop it permits 83% of capital in one
name.

On the real 19-name run the largest per-position risk was **0.18%** against
that 5% ceiling. It does not bind, and will not at any realistic ATR once the
volatility target has already scaled positions to around 5% each. So the only
genuinely **Sourced** ceiling in this section is decorative in practice, and the
constraints actually shaping the portfolio are the two Convention caps below.
Anyone crediting p.1032 with protecting this portfolio is crediting the wrong
rule.

### Stop at 2 × ATR — **Adapted**, and the book's own multiples are not 2

Corrected after searching the whole library rather than its top-level listing.
The first version of this entry called the multiple pure Convention and said
"the multiple is not [sourced]". That was wrong.

The **form** is well sourced, twice over. p.852 describes ATR as used to place
stops, take profits, or set the current level of risk. p.1055 goes further and
argues *against* the obvious alternative: after reporting that "some more
experienced traders believe that you should never lose more than 3% of your
total investment on a single trade", Kaufman answers that "stops are more
sensible if they relate to the nature of the system, the timing of the trade,
the market volatility, or a chart pattern." An ATR stop is exactly the
volatility-related construction he prefers there. (That sentence is also the
second percentage-of-capital figure in the book, which corrects a claim made
further down this file.)

The **multiple** is where we diverge, and the book is more specific than I gave
it credit for. p.1055 lists five worthwhile stop constructions; the fifth is
"adjust the stop by the volatility, such as **3 times the current 10-day
average true range**". The trailing-stop discussion on p.1055–1056 cites ISAM's
generic stop of **12 × average true range over the past 252 days**, and then
states the design rule that matters most here: **the multiplier should vary
based on the calculation period of the trend.**

So the source offers 3 × ATR(10) and 12 × ATR(252), and a principle for
choosing between them. We use **2 × ATR(14)**, which matches neither figure and
follows neither the short nor the long pairing — our ATR period sits near the
book's short example while our multiple sits below even that. Nothing here is
fatal; it is Adapted rather than Convention, and the divergence is now named
instead of hidden. Tying the multiple to the trend period, as p.1055 prescribes,
is a concrete improvement available and is listed under Open items.

### And the source doubts stops help us at all — **Contradicted**

Recorded against a feature shipped the same day it was written, because that is
exactly when it is tempting not to.

p.1055–1056, on initial stops: "trend systems already cut losses quickly, and
mean reversion systems need a high percentage of profitable trades, the result
of holding trades that initially go the wrong way, **so it is not clear that any
stop-loss would improve those profiles.** Under highly volatile situations, they
may be a benefit, but that would need to be tested for specific strategies, and
the frequency of occurrence would be small."

Our engine is a trend-following screen. Kaufman's position is therefore that a
stop-loss may add nothing to it, and that the question is empirical rather than
settled. We publish a stop for every holding and have tested nothing about
whether it helps. That does not make publishing it wrong — p.1032 principle 2
still wants an exit known in advance — but it does mean the stop is an
untested addition to a style the source says may not benefit from one.

### Position cap 10%, sector cap 25% — **Convention**, searched and not found

p.1040 warns that a portfolio concentrating on fewer groups carries greater
risk, which is the argument *for* having caps. It names **no level**, so both
numbers are ours. They matter more than their status suggests: as shown above
the sourced risk ceiling never binds, so these two unsourced numbers are what
actually constrain concentration. On the 19-name run the sector cap bound
Financials at exactly 25.0%.

Capped weight is **not redistributed** to the uncapped names; it stays in cash.
Redistribution needs iteration to converge, and an iteration count is one more
thing two engines must agree on exactly.

### What was rejected, and why it is not an oversight

**Optimal f / Kelly** is the most-discussed sizing method in TSaM — 26 mentions
of optimal f, 24 of risk of ruin, against one statement of the 5% ceiling. It is
deliberately not used. It requires the win probability `P` and the payoff ratio
`B` from the system's own trade history, and ours is contaminated by the
feedback failure recorded above and measured no edge, so any `f` computed from
it would be a leverage number resting on a foundation this file already
describes as unusable. Kaufman's own worked example lands on **25% of capital
per trade**, and Elder's critique (p.1092) is that trading above optimal f goes
broke eventually while trading below it loses profits geometrically. Kaufman's
fallback for exactly this situation is on the same page: "the simple solution is
to keep trading the same amount, with a reserve sufficiently large to absorb
most extreme, adverse price moves."

Worth recording separately: Elder's three conclusions from that section — never
average down, never meet margin calls, **liquidate the worst position first** —
restate p.1032 principles 5 and 6. "Liquidate the worst first" therefore has two
independent citations, more than almost any rule in this file.

### A rule that is in no book here — **Convention**, re-confirmed on a corpus 2.2x larger

The first draft of this section defaulted to risking **1% of capital per
position**. Searched against every machine-readable book in the library, with
the pattern validated against a line known to exist first, that number returns
**zero** hits for 1% or 2% risk-per-trade phrasing. It is practitioner folklore,
and it was about to be written in as a default with citation-shaped confidence.

**No book count is stated here, deliberately.** This paragraph has now been
wrong about the size of the library twice: once at seven files, which was a
top-level directory listing rather than the library, and once at 134, which was
true for about an hour. A bulk download is still running against an 885-item
catalogue, so any figure written down now has a short life and would make this
entry false again by tomorrow. The search behind the finding was last run over a
rebuilt corpus of 165 machine-readable documents and 19,081 chunks; re-run it
when the download finishes, which is cheap because
`Books_TO_study/_tools/build_corpus.py` is incremental.

The finding itself is robust to the count, which is the point: every book added
so far has moved the denominator and none has produced a hit.

An earlier version of this entry said "nowhere in any of the seven books" and
"exactly one hit for a percentage of capital — the 5% ceiling at p.1032". Both
were wrong, and wrong in the same way: the seven files at the top level of
`Books_TO_study/` are not the library, they are its first directory listing.
The rest sit in a subdirectory nobody had opened. Searching all 134 finds a
**second** percentage-of-capital statement, at p.1055 — see the stop entry
above — so the "exactly one hit" claim was false even though the 1% conclusion
it supported survives, and survives more strongly.

That is the useful lesson and it is worth more than the sizing section. Every
statement built on that first search was true of what was searched and wrong
about the corpus, because the extent of the source was never itself checked.
"Verified against the books" is only as good as the set of books you looked at.

---

# Open items

Ranked by value, cheapest first where value ties.

0. **Tie the stop multiple to the trend period.** TSaM p.1055–1056 states that
   the ATR multiplier should vary with the calculation period of the trend, and
   offers 3 × ATR(10) and 12 × ATR(252) as the short and long ends of that idea.
   We use a fixed 2 × ATR(14), which follows neither. Cheapest sourced
   improvement now available, and unlike most entries here it replaces a number
   we invented with a rule the book actually states.
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
   it, per TSaM p. 310. The second half of this item — find the Directional
   Movement section and source the threshold — is **done**: p.1066 gives
   Ruggiero's "ADX crosses above 25, the market is trending", so only the
   gate-versus-points question remains open. Worth noting it took one grep
   against text already extracted on disk, which is the cheapest any item here
   has ever closed.
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
