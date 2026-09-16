# V1 engine — frozen 2026-09-16

What the engine does today, and what is known to be wrong with it. Written at
the close of the validation phase so that the next change has to argue against
a written baseline rather than against memory.

**Frozen means:** no reweighting, no new indicator, no threshold tuning inside
the technical factor family. A genuinely new hypothesis re-opens it; a variation
on trend / momentum / relative strength / volume does not.

## What ships

| | |
|---|---|
| Schema | `v6` |
| Scoring hash | `e2cebaa95afdbcf2` (guarded by `scripts/check_doc_figures.py`) |
| Technical blocks | trend 40, momentum 30, relStrength 20, volume 10 |
| Composite | `fundamental x (1-w) + technical x w`; a missing technical half falls back to fundamental-only rather than diluting toward zero |
| Pass gate | `minimum_total_score` **50** |
| Verdict bands | Strong 70, Good 60, Average 45, else Weak |
| Watchlist | top 20 of the passing list |
| Sizing | equal risk by `atrPct`, 12% portfolio volatility target, 2x ATR stops |
| Parity | Python and TypeScript engines are bit-identical, enforced in CI |

## What has actually been tested

**The technical score. Exhaustively, and it failed.**

| level | result |
|---|---|
| composite | 1m IC −0.0033; 0 of 20 cells clear their detection floor |
| 4 blocks | none carries the composite |
| 12 primitives | 0 of 48 cells clear detection **and** family-corrected significance |

Deciles separate in the right direction at 6 and 12 months (+4.45pp, +5.98pp)
on an IC less than half its own floor, non-monotonically. It beat equal-weight
in 3 of 8 years, clustered in down years — a defensive tilt, not selection
skill. Detail in [component-stop-condition.md](component-stop-condition.md).

**The fundamental score. Not at all.** There is no point-in-time data, so
nothing on the fundamental side — including the 50-point gate that decides who
is screened in — has ever been measured against returns. This is the single
largest unvalidated surface in the engine.

## Known defects and limitations

### Live, in the shipped engine

1. **The volume block pays for the wrong thing.** `engine.py:2387` awards +5
   points for `volumeRatio20D > 1.0`. That primitive is the only one of forty-
   eight cells to clear both statistical bars, and it is **negative at every
   horizon**. Registered as a holdout candidate in [holdout.md](holdout.md);
   deliberately **not** acted on.
2. **The 50-point gate is provisional and the code says so.** It was lowered
   from 65 so that rescaling the quality and growth scales would not silently
   tighten the screen, and calibrated so a bundled sample with *invented*
   figures passed the same 9 of 11 companies. It has never been validated
   against returns.
3. **Verdict bands are labels, not predictions.** 70/60/45 were chosen to
   spread a list for reading, and are not fitted to anything.
4. **The twelve primitives are roughly three bets.** `smaCross` and
   `relativeStrength6M` correlate +0.91 per date; `priceOverSma50` and `rsi14`
   +0.89. The trend and relStrength blocks are substantially the same wager, so
   the 40/30/20/10 weights do not mean what their labels suggest.
5. ~~656 zero-volume bars~~ **FIXED 2026-09-16.** The panel held 581
   forward-filled market holidays and 47 per-symbol no-trade bars, each
   inserting an artificial 0% return. Verified to originate at the provider --
   a single-ticker download returns the same bar -- and now dropped at the
   ingestion boundary in `price_history_rows_from_download`, guarded by
   `TradingCalendarTests`. The frozen study was re-run unchanged on the clean
   panel: max abs delta IC 0.00174 across 80 cells, no sign flips, same single
   cell clearing both bars. **The measurement was not contaminated and the FAIL
   branch stands.** Rows where the price moved but volume was absent now carry
   a BLANK volume rather than a zero, so `volumeRatio20D` reads them as not
   measured instead of as a false denominator.

### Data, and what cannot be obtained

6. **Banks and NBFCs are largely unscoreable.** Yahoo publishes no Gross NPA,
   Net NPA or capital adequacy, so lenders are reported "not scored" rather
   than scored on the wrong model. That is the correct degradation and it is
   still a hole: 23 of the 100 names are Financial Services.
7. **Promoter holding is approximate.** `heldPercentInsiders` is US-style
   insider holding, right where a classic promoter exists (TCS 71.8%) and wrong
   in kind where one does not (HDFC Bank 0.0015 against a true nil). Not
   fixable from Yahoo.
8. **Pledged percentage is unavailable** at any free source. Left empty, never
   defaulted to zero, because a zero would award governance points and suppress
   a hard red flag.
9. **ROCE is FY-based while Yahoo's own ROE and ROA are TTM**, so a row can mix
   periods across columns. Documented in
   [yahoo-data-contract.md](yahoo-data-contract.md).

### Structural, and not fixable by better code

10. **Survivorship.** The universe is the *current* Nifty 100 applied to past
    dates. Every backtest figure is biased optimistic by an amount not
    estimated here.
11. **Sample size is the binding constraint.** About 86 monthly rebalances and
    roughly 7 independent 12-month observations. At 12 months the HAC degrees
    of freedom fall to 5. No estimator lifts this.
12. **Costs are flat at 15 bps per side**, with no spread or turnover scaling —
    least believable exactly where finding 1 lives, in the least liquid names.
13. **The fundamental archive holds one distinct month.** About twelve are
    needed. See `scripts/archive_health.py`.

## Families tested and frozen

| family | registered | result |
|---|---|---|
| trend / momentum / relStrength / volume | — | FAIL at composite, block and primitive level; re-confirmed on the corrected panel |
| idiosyncratic volatility (126-session) | `bfb9fe8` | **FAIL** — 0 of 4 horizons positive, none detected; total vs idio indistinguishable |
| short-term reversal (21-session) | `356a1ac` | **FAIL** — 1M IC +0.0205 against a 0.056 floor, no decile separation, 87.9% turnover; and −0.86 correlated with `priceOverSma50`, so not a distinct family |

The volatility run also showed low total volatility is −0.65 correlated with
beta per date, so it was substantially a low-beta bet; residualising halved
that to −0.37 and moved the IC almost not at all.

## What would re-open the engine

Only one of these, and each needs its own pre-registration:

- A **genuinely different factor family** — not a variation on the four blocks,
  and not a variation on volatility either.
- **Point-in-time fundamentals** reaching ~12 vintages, which makes the whole
  fundamental side testable for the first time.
- A **longer price history**, which the power decomposition showed buys ~42%
  more detectable effect against ~14% for widening the universe.

## What must not happen

- Backfilling historical dates with today's fundamentals. It is look-ahead, it
  would look like it worked, and it would poison the only asset the project is
  still accumulating.
- Reading a leave-one-out improvement as a discovery. None of them clears its
  own floor.
- Spending a holdout rung on a hypothesis formed by reading these results
  without first clearing the confounds written down beside it.
