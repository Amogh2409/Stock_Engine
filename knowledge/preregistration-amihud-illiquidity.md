# Amihud Illiquidity Factor — Pre-Registration

## 1. Status and research budget

Written **before** any Amihud forward return, IC, decile return, spread or
performance statistic has been calculated.

The candidate passed the prospective signal-distinctness screen without
consulting forward returns. Closest previously tested signal: `idioVol`,
|mean per-date Spearman ρ| **0.334**, |median| **0.340** — both below the 0.70
duplication threshold. (See §17: these are the figures for the **63-session**
signal registered here, re-measured for this document.)

Passing the screen means only that Amihud is distinct enough to justify
consideration as a new family. **It is not evidence that the factor predicts
returns.**

Budget before this study: **1 of 3** slots spent. Executing the registered
study below consumes **slot 2 of 3 regardless of outcome**.

## 2. Hypothesis

> **Stocks with higher historical Amihud illiquidity will, on average, earn
> higher subsequent cross-sectional returns**, as compensation for bearing
> greater liquidity risk.

The raw Amihud quantity enters **without sign inversion**: higher Amihud =
higher signal. **A positive Spearman IC supports the registered hypothesis.**

A negative IC does not establish the inverse hypothesis. No alternative
directional claim may be adopted from this run.

## 3. Data requirements

Requires price-panel **schema v2**. The factor must **refuse to execute**
against a v1 panel or any dataset lacking the split-adjusted,
dividend-unadjusted close.

- **Return price**: the dividend-adjusted `closes`. Basis for total return.
- **Traded-value price**: `closesUnadjusted` — empirically verified as
  split-adjusted, not dividend-adjusted, aligned with the provider's restated
  volume.
- **Volume**: the existing field. Verified whole shares, split-consistent, with
  no fabricated zero-volume sessions remaining.

Skipped as invalid: missing volume; volume ≤ 0; missing traded-value close;
traded-value close ≤ 0; adjusted return not computable. **Missing observations
are never converted to zero and never treated as infinite illiquidity. No
imputation.**

## 4. Daily measure

```
r(i,t)           = closes(i,t) / closes(i,t-1) - 1
TradedValue(i,t) = closesUnadjusted(i,t) × Volume(i,t)
ILLIQ(i,t)       = |r(i,t)| / TradedValue(i,t)
```

Numerator is dividend-adjusted total-return movement. Denominator is
contemporaneous traded value without stock-specific dividend deflation.

A fixed positive scaling constant is permitted for display only and must not
alter ordering.

## 5. Formation window

**63 genuine trading sessions**, ending on the rebalance date. The
rebalance-date close may be used: the portfolio forms only after that session
closes. **The forward-return window begins strictly after the rebalance
timestamp. No future session may enter the factor.**

Minimum valid daily observations: **45 of 63**. Below that, the stock receives
no signal at that date. **No extension of the lookback to fill gaps.**

## 6. Aggregation

**Arithmetic mean** of valid daily observations over the 63-session window.

No winsorisation. No clipping. No median substitution. No log transform. No
rank averaging of the daily observations.

Extremes may be diagnosed and reported but remain in the primary specification
unless they violate an established data-validity invariant.

## 7. Cross-sectional ranking

At each monthly rebalance, eligible stocks are ranked by the aggregated signal.
**Higher Amihud = more illiquid = higher rank.**

Decile reports must label the economic direction explicitly, not rely on
ambiguous Q1/Q10 notation. Primary spread:

```
most-illiquid decile return − most-liquid decile return
```

A positive spread supports the registered direction.

## 8. Rebalance schedule and universe

Exactly the existing point-in-time universe machinery, monthly rebalance dates,
pre-holdout sample, trading-session rules and forward-return machinery. **No
universe modification for Amihud. No minimum-liquidity screen may be added
after results are observed.**

## 9. Forward horizons

- **Primary: 1 month.** The only horizon allowed to determine pass/fail.
- **Diagnostic: 3, 6, 12 months.** Reported; **may not rescue a failed
  1-month primary**.

All four are computed and inspected, so all four are in the family.
**Family size: 4.**

## 10. Primary statistical metric

Mean monthly cross-sectional Spearman rank IC between the registered signal and
1-month forward return.

Reported: mean IC; HAC t-statistic; HAC-based 80%-power detection floor;
bootstrap confidence interval; Bonferroni-adjusted p; positive-IC share; number
of rebalance dates; number of stock-date observations.

**The repository's existing implementations are reused, never reimplemented as
a factor-specific variant.**

## 11. Time consistency

The pre-holdout sample is split at its median rebalance date. The primary
1-month mean IC is reported for each half. **Both half-sample ICs must carry
the registered positive direction.** A stability requirement, not an
independent significance test.

## 12. Portfolio diagnostics

For the 1-month horizon: most-liquid decile return; most-illiquid decile
return; high-minus-low spread; monotonicity; monthly turnover; transaction-cost
estimate; spread after the existing cost framework; maximum drawdown of the
extreme deciles.

The repository's existing cost implementation, unchanged: **15 bps per side**
through the existing turnover-aware machinery. **No Amihud-specific cost
assumption may be substituted after results are observed.**

> Because the strategy deliberately selects less-liquid securities, **the
> existing cost model may understate real implementation costs. This limitation
> is disclosed even if the registered test passes.**

## 13. Pass conditions

All five, at the 1-month horizon:

1. Mean IC positive.
2. |Mean IC| clears the registered 80%-power detection floor.
3. Clears Bonferroni-adjusted significance at family 4.
4. Mean IC positive in **both** pre-holdout halves.
5. Most-illiquid minus most-liquid decile spread positive.

A statistical PASS does not imply implementability. For practical viability the
spread must also remain positive after the existing cost model.

## 14. Verdicts

- **FAIL** — one or more predictive conditions fail. Freeze the
  Amihud/illiquidity family. No immediate rescue study.
- **PREDICTIVE BUT NOT IMPLEMENTABLE** — all predictive conditions pass, but
  the spread does not survive the cost model. Reported as predictive ranking
  information that is not economically usable. **Not an investable PASS.**
- **PASS** — all predictive conditions pass and the spread survives costs.
  Permits only: independent replication; consideration for the holdout ladder;
  incremental-value testing against frozen factors. **No immediate integration
  into the production technical score.**

## 15. Failure branch — prohibited rescues

If the study fails, these are explicitly prohibited as immediate follow-ups:

63 → 21 sessions; 63 → 126 or 252; arithmetic mean → median; → geometric or
harmonic; raw → log Amihud; winsorising after seeing the tails; removing
high-illiquidity observations for looking extreme; a minimum-liquidity filter;
a size filter; sector neutralisation; beta neutralisation; volatility
neutralisation; moving the primary horizon to 3/6/12M; changing missing-volume
handling; changing the traded-value price basis; alternative denominator
definitions; combining Amihud with turnover or volume into a composite.

Any such idea is a new hypothesis and must satisfy the research policy
independently.

## 16. Data-readiness history

The first Amihud readiness audit **failed before any forward outcome was
calculated**. The defect was general price-panel semantics: the panel used the
dividend-adjusted close in the traded-value denominator, creating
stock-specific historical deflation. Cumulative adjusted/raw factor at
2016-06-30: VEDL 0.332, COALINDIA 0.452, ITC 0.697, TCS 0.784, HDFCBANK 0.912 —
roughly **2.75× cross-sectional dispersion**.

The shared panel was repaired before registration by adding a split-adjusted,
dividend-unadjusted close. Post-repair, `old traded value / corrected traded
value` matches the cumulative dividend factor to ~1e-12, and the denominator
basis audit reports cross-sectional scaling **1.0000 .. 1.0000**.

**No Amihud forward return, IC, decile return or spread was observed before
this repair.**

## 17. Existing signal distinctness

Screened against all previously tested primitives without accessing forward
returns.

**Measured at the registered 63-session formation**, not at the generic
21-session candidate window used in the earlier backlog sweep. The two are
different signals, and distinctness evidence must describe the one being
registered:

| | 21-session (earlier sweep) | **63-session (registered)** |
|---|--:|--:|
| closest signal | `idioVol` | `idioVol` |
| \|mean ρ\| | 0.321 | **0.334** |
| \|median ρ\| | 0.316 | **0.340** |

Next closest at the registered window: `totalVol` +0.221, `distFrom52WHighPct`
−0.112, `volumeRatio20D` −0.111. Everything in the frozen technical family sits
below 0.09 in absolute mean.

Clears `|mean ρ| > 0.70 OR |median ρ| > 0.70`. Amihud qualifies as a genuinely
eligible new candidate. **This says nothing about predictive validity.**

## 18. Unavailable diagnostics

Point-in-time historical market capitalisation is unavailable. Size exposure is
**NOT MEASURED** — not passed, not failed, not neutral, not controlled.

Current market capitalisation must not be backfilled into historical
observations. No price-derived proxy may be substituted and called size.

## 19. Holdout protection

Only the existing permitted pre-holdout sample. A PASS does not authorise
spending the holdout; that follows the existing ladder and requires its own
recorded decision.

## 20. Execution discipline

1. Commit this pre-registration. 2. Record its commit hash and SHA-256.
3. Implement. 4. Add known-truth tests. 5. Red-verify the important guards.
6. Commit the implementation **unrun**. 7. Execute **exactly once**.
8. Record the complete result regardless of outcome.

Known-truth tests must establish, at minimum:

- increasing Amihud values rank in the positive registered direction;
- reversing the signal sign reverses the known-truth IC;
- missing volume is skipped, not read as zero;
- a v1 panel without `closesUnadjusted` is rejected;
- the formation window cannot consume the first forward-return session;
- split handling does not mechanically change traded value;
- dividend adjustments do not enter the traded-value denominator.

**No forward outcome may be inspected until the implementation commit exists.**

---

# Result — 2026-09-16

Executed once against the registration at `b20e86c`, implementation `55266e7`,
on the schema-v2 panel. 87 rebalance dates, 7,621 stock-date observations,
63/45 formation, family 4. Outputs: `data-store/reports/amihud/`.

**Slot 2 of 3 is now spent.**

## Verdict: FAIL

| h | mean IC | floor | HAC t | p (Bonf) | IC>0 | illiquid − liquid |
|---|--:|--:|--:|--:|--:|--:|
| **1 (primary)** | **+0.0435** | **0.0446** | 2.78 | 0.027 | 64% | +2.90pp |
| 3 (diagnostic) | +0.0823 | 0.052 | 4.59 | 0.000 | 76% | +9.79pp |
| 6 (diagnostic) | +0.1183 | 0.069 | 5.15 | 0.001 | 83% | +22.06pp |
| 12 (diagnostic) | +0.1562 | 0.115 | 4.64 | 0.023 | 97% | +53.31pp |

Against §13, at the 1-month primary horizon:

| condition | result |
|---|---|
| 1. Mean IC positive | **PASS** (+0.0435) |
| 2. Clears the 80%-power detection floor | **FAIL** — 0.0435 against 0.0446 |
| 3. Bonferroni significance at family 4 | **PASS** (p 0.027) |
| 4. Positive in both pre-holdout halves | **PASS** (+0.0204, +0.0636) |
| 5. Illiquid-minus-liquid spread positive | **PASS** (+2.90pp) |

**Four of five conditions hold. Condition 2 fails by 0.0011 IC** — the effect
is about 97.5% of the size this sample could detect at 80% power.

Net spread after the registered cost model was **+2.88pp** (round trip 0.02pp
on 6.0% turnover), so the study would have been implementable had it been
predictive. It was not, under the registered rule.

### This is a FAIL, and the margin does not change that

A detection floor is not a target to be approached. It states the effect size
this sample could distinguish from noise at 80% power, and 0.0435 is below it.
The registration fixed that bar before the number existed precisely so that a
narrow miss could not be argued into a pass afterwards. It is being recorded as
a FAIL with the margin stated, not as a near-pass.

## The diagnostic horizons, and what may not be done with them

3, 6 and 12 months each clear **both** their floor and Bonferroni
significance, with the IC rising monotonically (0.0435 → 0.0823 → 0.1183 →
0.1562) and the positive-IC share rising from 64% to **97%**. The most-illiquid
decile compounded +2,795.8% against +181.8% for the most liquid, with a
*shallower* drawdown (−25.9% against −34.2%).

**§9 forbids these from rescuing the primary result, and they do not.** The
registered hypothesis was about the 1-month horizon and it failed there.

The pattern is consistent with a longer-horizon effect. That observation is a
**hypothesis formed by reading these results**, and §15 explicitly prohibits
"switching the primary horizon from 1M to 3M/6M/12M". It may become a new
registration in a later independent research round, under a new slot, with the
provenance of the idea stated — it must not be launched as a follow-up now.

## FAIL branch, now in force

> **The Amihud / illiquidity family is frozen.**

Prohibited as immediate follow-ups, exactly as listed in §15: 63 → 21/126/252
sessions; mean → median, geometric or harmonic; raw → log Amihud; winsorising
after seeing the tails; dropping extreme observations; minimum-liquidity, size,
sector, beta or volatility filters and neutralisations; moving the primary
horizon; changing missing-volume handling or the traded-value basis;
alternative denominators; compositing with turnover or volume.

## Disclosures carried from the registration

**The cost model understates this factor specifically.** §12 registered this in
advance: a strategy that deliberately selects less-liquid securities is exactly
where a flat 15 bps per side is least believable. Turnover was low (6.0%), so
the modelled cost was trivial — but the modelled cost is not the real one, and
this disclosure stands regardless of the verdict.

**Size exposure: NOT MEASURED.** Point-in-time market capitalisation does not
exist for these dates. Not passed, not failed, not controlled. Given the
illiquid decile is likely to be the small-cap decile, this is a real and
unresolved confound, and it is the strongest single reason not to read the
diagnostic horizons as an illiquidity premium.

**Bootstrap CI at 1 month:** [+0.0134, +0.0739], excludes zero — which is
condition 3 agreeing with itself, not a fourth independent check.

## Budget

**2 of 3 spent.** Reversal (frozen), Amihud (frozen). MAX remains parked and
BAB quarantined; neither is registered.

---

## Amendment — 2026-09-17, before the PIT sensitivity rerun

`research-policy.md` states that once forward outcomes for a factor have been
observed, input changes cannot rescue that study and require a new branch. The
Amihud outcome **has** been observed (FAIL, §13 condition 2). This amendment
therefore has to exist before the dataset changes underneath it.

**What changed and why.** The universe. Every study in this repository ranked
today's Nifty 100 applied backwards; the official index over 2015-2026 held 195
investable securities and 87 of them are absent from today's list. That is a
correctness defect in a shared input, discovered independently of this study
and repaired for every study at once.

**What this rerun is, and is not.**

> It is a **data-correctness sensitivity rerun**, asking whether the registered
> conclusion survives a historically correct universe.
>
> It is **NOT** a new hypothesis, **NOT** a rescue, and **NOT** a second
> attempt at the registered test.

Nothing registered moves: formation stays 63/45, the signal stays raw and
un-inverted, the primary horizon stays 1 month, the family stays 4, the cost
model stays 15 bps per side, and the five pass conditions stay as written.

**The registered verdict stands regardless of the outcome.** A FAIL that
becomes a PASS under a corrected universe does not retroactively pass the
original test; it would be a *new finding about the universe*, requiring its
own registration and its own slot before anything could be claimed from it.
The research budget is unchanged at 2 of 3 — this consumes no slot, because it
tests no new hypothesis.

**Mode is PIT_WITH_COVERAGE**, never PIT or SURVIVORSHIP_FREE: about 3% of
constituents by count and 5% by index weight remain unpriceable, and what is
missing is systematically the shorter-tenure, lower-weight names.
