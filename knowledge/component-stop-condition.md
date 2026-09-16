# Stop condition — component attribution of the technical score

Written **before** the run was read. The results existed on disk when this was
committed; they had not been opened. `git log` orders the two commits, which is
the only reason a predeclared rule is worth anything.

## Why a component run at all

The composite technical score measures a powered null: zero of twenty cells
clear their own detection floor, the 1-month IC is −0.0033, and the top decile
*underperforms* the bottom by 4.5pp at 6 months and 6.0pp at 12. Each of the
four blocks was then measured separately and none carried the composite.

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
