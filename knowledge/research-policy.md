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

---

## Amihud input-readiness audit — 2026-09-16

Inputs only. **No forward returns, no ICs, no research budget consumed.**
Reproducible: `scripts/venv-python.sh scripts/amihud_readiness.py`.

| check | result |
|---|---|
| Volume unit (whole shares) | **PASS** — median 1,907,573, 100% integral |
| Corporate-action invariance | **PASS** |
| **Price basis for traded value** | **FAIL** |
| Missing-volume contract | **PASS** — 29 blank, 0 zero, both skipped |
| Cross-sectional coverage | **PASS** — 100% of windows meet the minimum |
| Extreme-value inspection | **PASS** — diagnosed, never clamped |

## READINESS: FAIL

### Splits are fine — that trap was checked and is not present

Median traded value after ÷ before a split:

| ticker | split | ratio | a raw-volume panel would show |
|---|--:|--:|--:|
| BAJFINANCE 2016-09-08 | 1:5 | 0.640 | 5.0 |
| RELIANCE 2017-09-07 | 1:2 | 1.066 | 2.0 |
| ITC 2016-07-01 | 1:1.5 | 0.888 | 1.5 |

The provider restates volume into post-split units alongside the price, so
`close × volume` is internally consistent across a split. Verified directly:
an `auto_adjust=False` download returns **byte-identical volume**, and neither
series shows a 5× discontinuity at the BAJFINANCE split.

### Dividends are not fine, and that is the failure

The panel stores `auto_adjust=True` closes, adjusted for splits **and
dividends**. The dividend adjustment deflates each stock's historical prices by
**its own** dividend history, so the deflation differs across the cross-section
— and Amihud ranks cross-sectionally.

Cumulative adjusted/raw factor at 2016-06-30:

| ticker | factor |
|---|--:|
| VEDL | **0.332** |
| COALINDIA | 0.452 |
| ITC | 0.697 |
| INFY | 0.756 |
| TATASTEEL | 0.756 |
| TCS | 0.784 |
| HDFCBANK | **0.912** |

**A 2.75× spread.** Vedanta's 2016 traded value is understated by 67%, HDFC
Bank's by 9%. Since Amihud is `|return| / traded value`, a deflated denominator
*inflates* the illiquidity score: **high-dividend stocks are made to look
systematically more illiquid, and increasingly so the further back the sample
goes** (the spread narrows to 1.17× by 2024).

A uniform deflation would have been harmless — it cancels in a ranking. Only
the dispersion matters, and the dispersion is large.

Note the numerator is fine: dividend-adjusted returns are the correct total
return. The defect is confined to the denominator.

### What a fix would require

The panel would need a **split-adjusted, dividend-unadjusted close** column for
traded value, keeping the existing adjusted close for returns. Concretely:
`auto_adjust=False` supplies exactly that basis, so the download gains a
column, `price_history_to_csv` and its parser gain a field, and the panel is
rebuilt and re-verified against the calendar invariants.

That is a data change, not a signal change, and it would happen **before** any
Amihud return is computed — so it is not post-hoc repair. But it is a schema
change to the one dataset every other study also reads, and it is the user's
call whether Amihud is worth it.

### Status

**Amihud is NOT registered.** Budget remains **1 of 3**: the audit consulted no
forward outcomes, so it spent nothing.

| candidate | status |
|---|---|
| Reversal | spent + frozen |
| MAX | screened distinct, **parked** — ~0.53 with total volatility, entangled with a failed family |
| Amihud | screened distinct, **input audit FAILED** on price basis |
| BAB | quarantined |

---

## Amendment — repair of inputs vs rescue of results

The earlier rule — an input-readiness failure means stop, not repair — was too
strict in one direction: it rewarded leaving a known data defect in place.
Replaced prospectively by:

> **An input-readiness failure discovered BEFORE any forward outcome for that
> factor has been inspected MAY be repaired**, provided all of:
>
> 1. no forward outcome for the factor has been computed;
> 2. the defect is a general data-semantics or correctness issue, not a
>    parameter of the candidate signal;
> 3. the repair is determined by the mechanics of the data, not chosen to
>    produce a result;
> 4. the repaired input is **re-audited before registration**.
>
> **Once forward outcomes for a factor have been observed, input or
> specification changes cannot rescue that study.** They require a new research
> branch, a new registration, and they consume a new budget slot.

The line is *when the outcome was seen*, not *whether a change was made*. A
defect found by auditing inputs is a fixable bug; the same change made after a
disappointing IC is a specification search.

This amendment authorises the dual-close panel repair below. Applied to the
record: the Amihud denominator defect was found with **no Amihud forward return
ever computed**, the defect is in the shared panel rather than in Amihud, and
the correction (use a dividend-unadjusted close for a rupee traded value) is
determined by what traded value *means*.

---

## Dual-close panel repair — 2026-09-16

Authorised under the repair-vs-rescue amendment. **No Amihud forward return had
been computed, and none was computed during the repair.**

### What changed

Price panel **schema v1 → v2**: `CloseUnadjusted` appended — split-adjusted,
**not** dividend-adjusted — for traded value only. `Close` keeps its meaning
(split *and* dividend adjusted) and every return, indicator and existing study
still reads it. The basis was verified empirically, not from the flag name:
`auto_adjust=True`'s Close equals `auto_adjust=False`'s `Adj Close` exactly,
and the latter's `Close` is the split-adjusted-only series.

A **second download** rather than a derived column: scaling the adjusted close
by a ratio would put floating-point drift into the OHLC every other study
reads. Mirrored in TypeScript as `closesUnadjusted`, so cross-engine parity
holds. A v1 file still parses, with the column absent — and Amihud **refuses**
a v1 panel rather than falling back to `Close`, which would silently restore
the defect.

### The denominator correction, validated mechanically

`old traded value / new traded value` equals the cumulative dividend factor
exactly (to 1e-12) for every ticker tested:

| ticker | adjClose/unadjClose | oldTV/newTV | match |
|---|--:|--:|---|
| VEDL | 0.3320 | 0.3320 | ✓ |
| COALINDIA | 0.4516 | 0.4516 | ✓ |
| ITC | 0.6969 | 0.6969 | ✓ |
| TCS | 0.7843 | 0.7843 | ✓ |
| HDFCBANK | 0.9120 | 0.9120 | ✓ |

The old basis dispersed **2.75×** across the cross-section at 2016-06-30. On
the new basis the audit reports a spread of **1.0000 .. 1.0000 (1.00×)** — the
dispersion is gone, because the unadjusted close *is* the price shares traded
at.

### Re-audited after rebuild

| check | before | after |
|---|---|---|
| Volume unit | PASS | PASS |
| Corporate-action invariance | PASS | PASS |
| **Price basis for traded value** | **FAIL (2.75×)** | **PASS (1.00×)** |
| Missing-volume contract | PASS | PASS |
| Cross-sectional coverage | PASS | PASS (100%) |
| Extreme-value inspection | PASS | PASS |

**READINESS: PASS.** Calendar invariants re-run: 0 synthetic sessions, 0
no-trade bars, 29 blank-volume rows, 0 month-ends on a synthetic session.

### Collateral effect

**Volume: byte-identical, 0 differing cells.**

The adjusted OHLC differ in **135,109 of 266,095** cells — but not because of
this change. Adding the `auto_adjust=False` call to a multi-ticker download
changes **0 of 21** adjusted closes in a controlled test; the drift is
provider-side float variation between two separate downloads, bounded at
**8.8e-7 relative**, or **0.013 bps** on a daily return.

The substantive proof is the frozen study re-run on the v2 panel: across 80
cells the largest IC move is **0.00075** and the median **0.0000072**, with the
same single cell (`volumeRatio20D` 6m) clearing both bars. **Conclusions
unchanged.**

`SCORING_HASH` moved to `cce5e6369b60810b` because the guard covers every
module constant and two schema constants changed; the scoring functions have
zero diff lines. Recorded in `holdout.md`.

### Budget

Still **1 of 3**. Amihud is now eligible for registration; slot 2 is consumed
only when a registered return study actually runs.
