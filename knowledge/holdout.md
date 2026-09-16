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
parameter has been changed in response to it.** That sentence is the whole of
the argument and it is still true.

**The scoring rules are no longer byte-identical, and an earlier version of this
file wrongly said they were.** On 2026-09-14 one scoring parameter changed:
`RELATIVE_STRENGTH_SKIP_SESSIONS` in `engine.py`, which moves relative strength
from a t−h to t−1 window to t−h to t−2. It was adopted **on a citation** — CFA
Institute Research Foundation Monograph `rf-v2016-n4-1#71`, *"excluding the most
recent month (2–12)"* — and explicitly **not** on any measurement: the ladder
showed the change buys +0.0053 IC at 6 months, far inside the detection floor,
and the rulebook records that the data shows the change costs nothing rather
than serving as the reason for it.

**A second change landed on 2026-09-16, and it touches admission rather than
scoring.** `hard_red_flags` no longer infers negative net worth from a negative
debt-to-equity ratio. That inference only holds when the provider reports GROSS
debt; a provider reporting NET debt gives a negative ratio to a company holding
more cash than it owes, so the rule was rejecting some of the strongest balance
sheets in the universe as insolvent. Equity is now tested directly where an
export carries it, with the price-to-book sign as the fallback. In the same
change `grossNpa` moved from required to reported-only, because it carries no
points and was blocking lenders over a field the model never reads.

Both came from an external code review of the engine's design — **not from the
reserved window**, which has not been read since 2026-09-13. Neither is a
measurement-driven adjustment, and neither can be: `python/backtest.py` contains
zero references to fundamentals, red flags or bank fields, so nothing here can
reach the measurement at all. That was verified rather than assumed by
regenerating rung C on the changed engine — the pre-registered momentum cell
came back bit-identical on all five stored figures.

**So it is not feedback, and p. 917 is still satisfied.** A parameter changed
because a book states the construction is not a parameter changed because the
reserved window said so. The argument is weaker than "nothing has changed at
all" — it now depends on the provenance of each change rather than on there
being none — and it remains valid. Every future change must be held to the same
test, which is what the scoring-hash guard below is for.

The other changes since remain what they were: measurement apparatus — standard
errors, sampling, a CI on the CAGR gap — which do not touch what is scored.

So the honest status is: **used once for observation, never used for fitting.**
That is weaker than a window nobody has looked at and stronger than one that has
been optimised against. A later test on it is real evidence, discounted by the
fact that the person running it already knows roughly what it says.

If that discount is unacceptable for the decision at hand, the remedy is time,
not argument: reserve a forward window from today and wait.

## An asymmetry, recorded rather than resolved

The single observation that partly spent this window was of the **old engine's
output**. For the blocks whose inputs have since changed — relative strength, and
therefore the composite — the **new** engine's behaviour on reserved data has
never been observed.

This does not make the window pristine, and it must not be used to argue that it
is. Whoever runs the final test still knows roughly what the 2023-onward period
did, which is the discount that matters and it applies to every block. But the
asymmetry is real and belongs on the record: momentum, trend and volume are
unchanged and were observed; relative strength and the composite are changed and
their current form was not.

The one pre-registered test (`knowledge/preregistration.md`) is on the momentum
block, which falls on the **observed, unchanged** side of that line. It gets no
benefit from this asymmetry.

## The guard against this file going false again

`npm run check:docs` compares figures against the measurement artefact. It cannot
check a prose claim about what has changed, which is exactly how the
byte-identical sentence above survived a scoring change.

So the same check now also hashes the source of `engine.py`'s two scoring
functions and fails when it moves. A scoring change therefore cannot land without
someone being told, in the same commit, that this file and
`knowledge/preregistration.md` make claims about what has changed and must be
re-read. Re-record the hash in the commit that changes the scoring, never
separately.

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

## Candidates waiting for a rung

Hypotheses formed by looking at pre-holdout data. Listed here so that acting on
one is a deliberate spend rather than a drift, and so that the count is visible:
every entry is a test the holdout could be asked to run, and it can only be
asked a very small number of times.

### The volume block points the wrong way (registered 2026-09-16)

The component run found `volumeRatio20D` negative at all four horizons, and its
6-month cell is the only one of forty-eight to clear both the detection floor
and the family-corrected p. `engine.py:2387` pays +5 points for the quantity it
says to avoid. See [component-stop-condition.md](component-stop-condition.md).

If this is ever tested, these are fixed now, before the holdout is touched:

- **Direction**: removing the `volumeRatio20D` rule, NOT inverting it. The
  decile pattern is not a clean inverse — only the lowest-volume bucket is
  distinct, so "buy quiet names" is not what was measured and must not be what
  is tested.
- **Horizon**: 1 month, the rebalance frequency the engine actually trades.
  6 months is where the statistic was strongest, which is exactly why it is not
  the horizon to test on.
- **The confound to settle first**: the effect lives in the least liquid tail,
  where a flat 15 bps per side is least believable. Re-measure it under a cost
  model that scales with turnover or spread BEFORE spending a rung. If the edge
  dies there, no holdout test is warranted at all.
- **Data-quality confound: CLEARED 2026-09-16.** The panel had contained 581
  forward-filled holiday bars with volume 0, feeding this primitive's
  denominator directly. They are removed and the study re-run unchanged: the
  6-month IC moved from −0.0639 to −0.0635. The finding was not an artefact of
  the synthetic bars. The liquidity and cost confounds above are untouched.
- **Failure branch**: if removal does not improve the holdout composite, the
  volume block stays as it is and this candidate is closed rather than
  re-specified at another horizon.

## Related

- `knowledge/rulebook.md`, "Testing methodology" — what the book requires and
  where this repository has failed it.
- `python/backtest.py` — `HOLDOUT_START`, and `--no-respect-holdout`.
