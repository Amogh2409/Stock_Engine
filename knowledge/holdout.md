# Reserved data

**Reserved: 2023-01-01 to the end of the price file. Do not measure against it.**

`python/backtest.py` truncates there by default. `--no-respect-holdout` lifts the
truncation and exists only for the single final test this file is written to
protect; using it for anything else spends the window permanently.

## Why a window is reserved at all

TSaM p. 917 states the rule without qualification: once the out-of-sample data
has been used, you cannot fix anything, because that is feedback and the result
is always overfitting. A window only answers a question once. Every look costs
part of the answer, and no amount of care afterwards buys it back.

This repository has already spent one window that way, and the rulebook records
it: a null was measured, the engine was reworked in response, and the reworked
engine was re-scored on the same 2022-onward data. The +2.15% that came back is
an in-sample number wearing an out-of-sample label.

## What this window is, honestly

**It is not pristine, and calling it pristine would be the exact failure this
file exists to prevent.**

On 2026-09-13 the full 2015-2026 span was measured, which includes 2023 onward.
Those results were read at composite level and per block. So the window has been
**observed once**.

What has *not* happened is the thing p. 917 actually forbids: **no engine
parameter has been changed in response to it.** The scoring rules, thresholds
and weights are byte-identical to what they were before that measurement. The
changes made since are to the measurement apparatus — standard errors, sampling,
a CI on the CAGR gap — not to the thing being measured.

So the honest status is: **used once for observation, never used for fitting.**
That is weaker than a window nobody has looked at and stronger than one that has
been optimised against. A later test on it is real evidence, discounted by the
fact that the person running it already knows roughly what it says.

If that discount is unacceptable for the decision at hand, the remedy is time,
not argument: reserve a forward window from today and wait.

## Rules while it is reserved

1. **Do not read per-period results inside it.** `--respect-holdout` is on by
   default precisely so this takes a deliberate act.
2. **Do not tune anything against anything.** The rule is not "don't tune on the
   holdout" — it is that a parameter chosen because it improved a number, on any
   window, is fitted. Measuring is free; adopting is not.
3. **When it is finally spent, say so here**, with the date, what was tested and
   what came back. A reserved window that quietly becomes a working one is worse
   than none, because it carries authority it no longer has.
4. **One test.** Not one test per variant. If four variants are in play, the
   choice among them must be made on pre-holdout data, and only the winner is
   tested here. Testing all four and reporting the best is the multiple-testing
   failure wearing a holdout's clothes.

## What the pre-holdout window leaves

2015-11 to 2022-12 is roughly 86 monthly rebalances. That is 86 independent
1-month observations and about 7 independent 12-month ones, so a 12-month claim
was never going to be settled on this data with or without a holdout. The
Newey-West standard errors added in Tier 0 keep all overlapping windows with a
valid SE, which recovers some of that, but it does not manufacture years.

This is the real constraint on the whole project and no statistical technique
lifts it. Eleven years of one index is a small sample for a cross-sectional
question, and the honest ceiling on what can be concluded here is set by that
rather than by the estimator.

## Related

- `knowledge/rulebook.md`, "Testing methodology" — what the book requires and
  where this repository has failed it.
- `python/backtest.py` — `HOLDOUT_START`, and `--no-respect-holdout`.
