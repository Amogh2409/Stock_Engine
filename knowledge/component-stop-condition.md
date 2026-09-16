# Stop condition — component attribution of the technical score

Written **before** the run was read. The results existed on disk when this was
committed; they had not been opened. `git log` orders the two commits, which is
the only reason a predeclared rule is worth anything.

## Why a component run at all

The composite technical score measures a powered null: zero of twenty cells
clear their own detection floor, and the 1-month IC is −0.0033 (HAC t −0.16,
n 86) in the figures the repo ships. Each of the four blocks was then measured
separately and none carried the composite.

"Not detected" is not the same as "backwards", and this run is the first to put
the composite's own deciles on the record. They separate in the *right*
direction at the longer horizons — top minus bottom +4.45pp at 6 months and
+5.98pp at 12 — but the separation is not monotone (7 falling steps of 9 at 6
months, 4 of 9 at 12), it is −0.05pp at 1 month, and the IC behind it still
sits far below its own floor (+0.0512 against 0.121 at 6 months). A spread that
size with an IC that far under the floor is what noise looks like when ten
buckets are drawn from ~89 names.

A sum can hide an offsetting pair. A flat total is equally consistent with
"every ingredient is noise" and with "one ingredient works and the rest cancel
it out". Blocks are themselves sums of two to five primitives, so the same
objection survives one level down. `CONTINUOUS_FEATURES` is where it stops:
twelve raw quantities, each ranked on alone. After this there is no lower level
to retreat to, which is what makes a stop condition meaningful here.

## What is measured

Twelve primitives, four blocks, four leave-one-block-out composites, each at
1/3/6/12 months. **Family size 80.** Correlations are computed per rebalance
date and then summarised, never pooled into one matrix — pooling cannot show
whether redundancy persists through time.

## The rule, fixed now

A primitive **survives** only if it clears all four. Conjunctive, not a
best-of:

1. **Detection.** `|mean IC| ≥ detectable_ic_80pct` for that cell — the repo's
   existing 80%-power floor, computed from that cell's own HAC standard error.
   This is the same standard the composite and all four blocks already failed;
   no new, softer threshold is invented for this run.
2. **Significance after the family.** `ic_p_bonferroni < 0.05` at family 80.
   Twenty cells were searched before; eighty are searched now, and the
   correction has to grow with the search or the run is just a wider net.
3. **Economic separation.** Top-minus-bottom decile spread positive and larger
   than the round trip it implies. At 15 bps per side the floor is **0.60pp**
   (enter and exit, both legs). A spread inside costs is not an edge.
4. **Horizon consistency.** Same IC sign at **≥3 of 4** horizons, and
   conditions 1–2 met at **≥2** of them. One horizon out of four at p<0.05 is
   what a family of 80 produces on noise.

### Sign is not free

The engine bets that a high score is good. A primitive whose IC is
significantly **negative** does not pass — it refutes the current use of that
primitive. Inverting it is a *new hypothesis*, and the repo already has the
machinery (`--invert`, the rung system, `holdout.md`) that says a hypothesis
formed by looking at these results cannot be validated on these results.

## On FAIL — what is given up

If no primitive clears all four:

> **No further technical reweighting, no new indicator, and no threshold
> retuning will be performed inside the existing technical factor family.**

That is the whole point of writing this down. The failure modes it forecloses,
by name:

- reweighting blocks toward whichever scored least badly here
- adding a thirteenth indicator to a family of twelve that measured nothing
- moving RSI bands, ADX cutoffs, or the 52-week-high distance
- "the signal is there, it just needs a filter"
- reading a leave-one-out improvement as a discovery rather than as the
  variance it is at family 80

The permitted responses are the ones that change the *inputs*, not the
arithmetic over them: point-in-time fundamentals (the archive currently holds
two vintages, both September 2026, which is why the fundamental side cannot yet
be tested at all), a longer price history, or a different factor family
entirely — each of which needs its own pre-registration.

## On PASS

A survivor is a *candidate*, not a finding. It goes to the holdout ladder like
any other hypothesis: registered as a cell, with its direction and horizon
fixed in advance, before the holdout is spent on it.

## Caveats recorded in advance

- Deciles over ~100 names are ~10 per bucket; tails are thin and the extreme
  buckets are the noisiest part of the whole run.
- Overlapping horizons at 3/6/12 months reuse returns. HAC lags handle the
  standard error; they do not restore the lost independence.
- Leave-one-out composites are not independent of each other — four of them
  share three quarters of their content.
- The universe is the current Nifty 100. Survivorship is not corrected here and
  biases every cell in the same optimistic direction.

---

# Result — 2026-09-16

Run: 87 rebalance dates, 48 primitive cells, 16 block cells, 16 leave-one-out
cells, family 80. Report at `data-store/reports/components/report.md`.

Priced from `price_history_20260916`, which is newer than the file behind the
shipped figures, so the composite baseline here is IC −0.0034 at 1 month rather
than the −0.0033 quoted elsewhere. Every comparison below is against this run's
own baseline, never across the two files.

## Against the rule: FAIL

**No primitive clears all four conditions. None clears even the first two.**

One cell out of forty-eight meets both detection and family-corrected
significance — `volumeRatio20D` at 6 months, IC **−0.0639** against a floor of
0.041, HAC t −4.74, Bonferroni p 0.039. Its IC is negative, so under "Sign is
not free" it does not pass. It is a refutation, not a survivor.

Three other cells clear the detection floor and nothing else:
`relativeStrength3M` at 6m (+0.0675) and 12m (+0.0647), `obvPressure20D` at 12m
(+0.0474). All three fail Bonferroni by a wide margin (p 0.24, 0.95, 1.00). At
12 months the HAC degrees of freedom are **5**; that column is close to
powerless and should not be leaned on.

**The FAIL branch is now in force.** No reweighting, no thirteenth indicator, no
threshold retuning inside the technical factor family.

## The one thing this run did detect points the wrong way

`volumeRatio20D` is negative at every horizon — IC −0.029, −0.043, −0.064,
−0.068 — with the positive-IC share falling from 41% to 31%, and a top-minus-
bottom decile spread of −1.0, −3.2, −8.1, −12.0pp. It is the most consistent
signal in the run, and it runs opposite to how the engine uses it:
`engine.py:2387` awards **+5 points** when `volumeRatio20D > 1.0`.

Leave-one-out agrees. Dropping the volume block raises the composite IC at
every horizon — 1m −0.0034 to +0.0012, 3m +0.0183 to +0.0254, 6m +0.0512 to
+0.0596, 12m +0.0425 to +0.0511. Dropping `relStrength` lowers it at every
horizon. Volume is subtracting; relative strength is carrying what little there
is. Note that **no leave-one-out variant clears its own floor either**, so that
ordering is a consistent point estimate and not a detected effect.

### Why this is not yet a licence to delete the rule

The decile pattern is not a clean inverse. Q10 — the *lowest* volume ratio — is
the best bucket at every horizon (21.5% at 6m against 13.4% for the highest),
but the middle eight buckets are flat and monotonicity is 6 rising steps of 9.
The effect sits almost entirely in one tail. The obvious confound is that the
quietest names are the least liquid, where the flat 15 bps cost assumption is
most likely to be wrong — the measured edge could be an execution cost the
backtest does not charge.

So: acting on this is a **new hypothesis**, formed by looking at these results,
and this file already says such a hypothesis cannot be validated on them. It
goes to the holdout ladder with its direction and horizon fixed in advance, or
it does not get acted on.

## The twelve primitives are not twelve measurements

Per-date Spearman, summarised rather than pooled. Stable, tight quartiles:

| pair | mean rho |
|---|--:|
| smaCross / relativeStrength6M | +0.91 |
| priceOverSma50 / rsi14 | +0.89 |
| priceOverSma200 / smaCross | +0.87 |
| priceOverSma200 / distFrom52WHighPct | +0.78 |
| priceOverSma200 / relativeStrength6M | +0.77 |
| smaCross / relativeStrength12M | +0.75 |

At the block level `relStrength / trend` is +0.56. The score is not twelve
independent opinions; it is roughly three, counted repeatedly, with the
trend and relative-strength blocks substantially the same bet. That is a
structural finding about the score's design, independent of whether any of it
predicts anything — and it explains why block-level results looked so much like
the composite.

---

# Re-run on a corrected panel — 2026-09-16

The panel the run above used contained rows that were never trading sessions:
**581 forward-filled market holidays** across 6 dates, plus 47 per-symbol
no-trade bars. Each inserted an artificial 0% daily return into every window
that averages returns, and counted toward any gate phrased as a number of
sessions. That is upstream of the whole study, so the study was re-run.

**Nothing was retuned.** Same primitives, same weights, same horizons, same
stop condition, same detection floors, same costs, same methodology. The only
change is the panel. This was not a rescue attempt — it asks whether the
measurement itself was contaminated.

## The answer: it was not

| | |
|---|---|
| Cells compared | 80 |
| **Max abs delta IC** | **0.00174** (adx14, 12m) |
| Median abs delta | 0.00031 |
| Sign flips | **none** |
| Cells clearing both bars, before | `volumeRatio20D` 6m, IC −0.0639 |
| Cells clearing both bars, after | `volumeRatio20D` 6m, IC **−0.0635** |

Composite: 1m −0.0034 → −0.0040, 3m +0.0183 → +0.0181, 6m +0.0512 → +0.0507,
12m +0.0425 → +0.0427.

ADX moved most, which is the one result that should have been predicted in
advance: it is built on true range, and a flat OHLC bar has a true range of
zero. That the largest contamination landed exactly where the mechanism says it
should is a check on the diagnosis, not a coincidence.

**The FAIL branch stands, now on data that is not contaminated.** The technical
family is re-frozen on the same terms.

The volume finding also survives materially unchanged, so the data-quality
confound recorded against it in `holdout.md` is **cleared** — but the liquidity
and cost confounds are not, and it remains a holdout candidate rather than a
change.

Both result sets are preserved:
`data-store/reports/components/technical-components-pre-calendar-fix.json` and
`…-post-calendar-fix.json`.
