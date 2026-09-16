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
