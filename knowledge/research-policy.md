# Research policy — what may be tested, and how much

Two substantial negative results now stand:

| family | registered | result |
|---|---|---|
| trend / momentum / relStrength / volume | — | **FAIL** at composite, block and primitive level |
| low / idiosyncratic volatility | `bfb9fe8` | **FAIL** — 0 of 4 horizons positive, none detected |

Both were measured honestly and neither was rescued. That is the asset this
policy exists to protect.

## Why a policy, and why now

The danger after two failures is not a third failure. It is the sequence:

> reversal → MAX → BAB → illiquidity → another → another

Run long enough, that finds something, and the something is chance. Bonferroni
inside a single study does not correct for the number of *studies*, and a repo
that keeps drawing from a candidate list until one clears its bar has become an
automated p-value search wearing the clothes of rigour. Every individual step
looks disciplined. The aggregate is not.

## New factor family policy

A new factor may be tested only if all eight hold:

1. **The hypothesis existed before the previous study's result was seen.**
   Evidenced by a commit that predates the result, not by recollection — the
   backlog below is that record.
2. **There is an economic or mechanical rationale**, stated before the run, not
   reverse-engineered from a number.
3. **It is materially distinct** from every already-tested family — not a
   reparameterisation of one.
4. **Inputs are available point-in-time.** No backfilling today's data onto
   past dates, ever.
5. **The specification is fixed before execution**, in a committed
   pre-registration.
6. **One primary specification only.** Not a window sweep.
7. **Failure freezes the family**, with the tempting repairs named in advance.
8. **A pass requires independent replication before integration**, and never a
   direct merge into the shipped score.

## The exploration cap

> **At most 2–3 further independent factor families, then price-only alpha
> research PAUSES** — regardless of outcome.

Spent so far: **1 of 3.** Short-term reversal, registered at `356a1ac` and run
once, FAILED — and it counts, despite turning out to be largely a
re-measurement of two frozen primitives, because refunding a family after
seeing its result is the accounting this cap exists to prevent.

The cap is the part that actually binds. Conditions 1–8 police each study's
internal honesty; only a cap polices the *number* of studies, and the number is
what turns a clean method into a search. When the cap is reached, the next
move is not a fourth family. It is to wait for the fundamental archive, which
is the one genuinely new source of information this project is acquiring.

## Hypothesis backlog

Recorded so that condition 1 is checkable later. **Listing is not scheduling.**
Nothing here may be run without its own registration, and nothing here may be
promoted because a diagnostic in another study made it look attractive.

| candidate | rationale | status |
|---|---|---|
| ~~Short-term reversal~~ | Liquidity provision. | **FAILED 2026-09-16**, frozen. Its signal proved −0.86 correlated with `priceOverSma50` and −0.84 with `rsi14`: not a distinct family after all |
| MAX / lottery demand | Investors overpay for right-skewed payoffs. | backlog |
| Betting-against-beta | Leverage-constrained investors bid up high beta. | **QUARANTINED — see below** |
| Illiquidity (Amihud) | Compensation for immediacy. Inherits the blank-volume caveat. | backlog |

### Two things quarantined by how they were discovered

**Betting-against-beta.** The volatility study measured
`corr(−total volatility, beta) ≈ −0.65` per date. That makes BAB feel
promising, and that is exactly the disqualification: it is a hypothesis made
attractive by a diagnostic in a completed study. Running it now would be the
specification search this policy forbids, one level up. It stays in the backlog
for a later, independent round — and if it is ever run, the registration must
state that this is where the idea came from.

**Low volatility as a portfolio-weighting scheme.** The same study found low
*total* volatility gave a materially shallower drawdown (−20.9% against −45.5%
for the noisiest decile) despite failing as an alpha factor. That is a real
observation and it belongs in **portfolio construction**, not stock ranking —
a different bucket with a different success criterion, since risk shaping does
not require return prediction. It must not be tested in this discovery cycle:
it was found by reading the results of a failed study, and turning a failure's
by-product into the next hypothesis is how a null becomes a finding.

## Meanwhile: the fundamental archive matures

Collection runs monthly and unattended. The archive does not have to be
complete before it teaches anything, provided immature horizons are **labelled**
rather than quietly reported:

| vintages | what becomes legitimate |
|---|---|
| 2–3 | coverage and stability diagnostics only — no return claims |
| enough for forward outcomes | preliminary 1-month studies, labelled preliminary |
| more | 3-month studies |
| ~12 | 6- and 12-month validation |

`scripts/archive_health.py` reports the count. The rule that matters: a study
run on a short panel is reported with its horizon's maturity stated, never as
though the panel were complete.

## Amendment — 2026-09-16, after the reversal result

**Condition 3 must be estimated before registration, not only reported after.**

Reversal was registered as materially distinct on horizon grounds — 21 sessions
against the frozen family's 3–12 months. The argument was reasonable and it was
wrong: the realised signal correlates −0.86 with `priceOverSma50` and −0.84
with `rsi14`. It was short-term reversal measured twice, once in each
direction, and `rsi14`'s own 1-month IC of −0.0273 already implied the answer.

So, for every future candidate, before it is registered:

> Compute the per-date cross-sectional Spearman correlation between the
> candidate signal and every already-tested primitive. The candidate **FAILS
> distinctness** if, against any one of them, **either**
>
> - `|mean per-date rho| > 0.70`, **or**
> - `|median per-date rho| > 0.70`.
>
> The interquartile range is reported diagnostically alongside.

**Mean alone is not enough**, and the failure mode is specific: a candidate
correlating +0.90 with a primitive on half the dates and −0.80 on the other
half has a mean near zero and would pass a mean-only screen while being a
sign-switching restatement of that primitive. The median catches it. Adding the
median costs nothing and closes the hole.

This is a screen against obvious duplication, not an alpha test, and it is
deliberately not a hypothesis test — no p-value, no correction, no power
calculation. It touches **no forward returns at all**, so it cannot leak
information about outcomes and cannot consume statistical power.

This costs nothing worth protecting. It needs no forward returns, spends no
statistical power, and consumes no budget — it is a property of the signals
alone. Applied here it would have saved a family.

**Failing the screen does not consume budget.** A candidate ruled a
reparameterisation was never a family, so nothing was spent on it. Only a
registered study that executes spends a slot.

**The budget is a maximum, not a quota.** If the screen shows the remaining
candidates are mostly transformations of things already tested, stopping at 1
of 3 is a stronger research decision than running two more studies because the
allowance exists. Nothing obliges the third slot to be used, or the second.

**Not applied retroactively.** Reversal stays spent.

---

## Distinctness screen — run 2026-09-16

Signal-only, 87 rebalance dates, **no forward returns computed**. Full table in
`data-store/reports/distinctness/distinctness.json`.

| candidate | closest already-tested primitive | |mean| / |median| | verdict |
|---|---|--:|---|
| **MAX** | `totalVol` | 0.521 / **0.535** | potentially distinct |
| **Amihud illiquidity** | `idioVol` | 0.321 / 0.316 | potentially distinct |

**Neither is a reparameterisation.** Both clear the 0.70 gate, and the second
clears it comfortably. That was not the expected outcome — the reversal result
suggested the price-only candidate space might be largely redundant, and on
this evidence it is not.

For reference, the gate catches what it was built to catch: reversal, screened
retrospectively, sits at −0.856 against `priceOverSma50`.

### What the screen does not say

Passing means **not a duplicate**. It does not mean unrelated, and the
distinction matters for MAX.

**MAX correlates +0.52 / +0.54 with total volatility**, stably (P25 +0.45,
P75 +0.59). About half its cross-sectional variation is shared with a family
that has already been tested and **failed**. The mechanical gate passes it, and
a judgement under condition 3 should still weigh that a MAX study would be
partly re-testing a null already measured. Its next-closest neighbours —
`idioVol` +0.50, `reversal` −0.39 — tell the same story: MAX is a tail
representation of volatility, related to two failed families at once.

**Amihud is the cleaner candidate on distinctness.** Its largest association is
+0.32 with idiosyncratic volatility, which is the expected and economically
sensible one — illiquid stocks are more volatile — and everything else sits
below 0.21. Nothing in the frozen family comes near it.

But Amihud carries the data dependency MAX does not: it divides by traded
value, so it inherits the volume history that was only repaired on 2026-09-16.
The contract is pinned by test — absent volume is skipped as MISSING, never
read as zero, which would divide into infinity and put the least-*measured*
stock at the illiquid extreme — and 29 sessions currently carry a blank volume.
That is small, and it is a dependency a registration must state.

### Budget

Still **1 of 3**. The screen spent nothing: it computed no forward returns, so
it could not learn anything about outcomes.

Neither candidate is registered. Passing the screen makes a candidate
*eligible* for registration under conditions 2, 4 and the rest — it does not
register it, and the budget is a maximum rather than a quota.
