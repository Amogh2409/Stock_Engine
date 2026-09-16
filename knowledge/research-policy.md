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

Spent so far: **0 of 3.** Short-term reversal, if registered, is the first.

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
| **Short-term reversal** | Liquidity provision: recent losers are compensated for absorbing selling pressure. Distinct from the frozen family, which is medium-term continuation. | **next, if any** — named in `bfb9fe8`, which predates the volatility result |
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
