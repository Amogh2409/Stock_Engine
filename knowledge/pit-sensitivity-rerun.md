# PIT_WITH_COVERAGE sensitivity rerun — 2026-09-17

**Mode: `PIT_WITH_COVERAGE`. Not `PIT`, not `SURVIVORSHIP_FREE`.**

A data-correctness rerun of the already-frozen studies on the official
point-in-time Nifty 100 membership. **No parameter, signal, horizon, cost,
threshold, stop condition or factor definition changed.** No new hypothesis was
tested; no research-budget slot was consumed; the holdout was not touched.

## Coverage that produced these numbers

| | |
|---|--:|
| rebalance dates | 96 |
| mean count coverage | **96.4%** |
| minimum count coverage | 93.0% |
| mean index-weight coverage | **93.4%** |
| minimum index-weight coverage | 92.3% |
| rebalances at 100% coverage | **0 of 96** |

Missing constituents remain systematically the shorter-tenure, lower-weight
names, so this **reduces** survivorship bias without eliminating it.

## Production technical composite

| h | static IC | PIT IC | delta | floor | detected? |
|---|--:|--:|--:|--:|---|
| 1 | −0.0041 | −0.0030 | +0.0011 | 0.057 | no |
| 3 | +0.0181 | +0.0198 | +0.0017 | 0.090 | no |
| 6 | +0.0507 | +0.0316 | −0.0191 | 0.126 | no |
| 12 | +0.0427 | +0.0357 | −0.0070 | 0.247 | no |

| | strategy CAGR | equal-weight CAGR | turnover |
|---|--:|--:|--:|
| STATIC current universe | 22.51% | 23.27% | 688% |
| **PIT_WITH_COVERAGE** | **12.27%** | **12.73%** | 687% |

**Survivorship bias was inflating CAGR by about 10 percentage points a year** —
on both the strategy and its benchmark. The relationship between them is
unchanged: the screen still loses to contemporaneous equal weight.

`CONCLUSION UNCHANGED.` The shipped score still fails validation.

## Component study — and the one result that did change

1 sign flip of 12 at 1 month (`obvPressure20D`, +0.0028 → −0.0041, both far
below their floors). Everything else keeps its direction.

**`volumeRatio20D` loses its significance.**

| h | static | PIT | significant? |
|---|--:|--:|---|
| 1 | −0.0290 (p 1.000) | −0.0326 (p 1.000) | no → no |
| 3 | −0.0422 (p 0.282) | −0.0355 (p 1.000) | no → no |
| **6** | **−0.0635 (p 0.040) SIG** | **−0.0533 (p 0.141)** | **YES → no** |
| 12 | −0.0682 (p 0.242) | −0.0582 (p 0.914) | no → no |

`CONCLUSION CHANGED` for this cell, in the direction of a weaker claim: under a
historically correct universe, **zero of 48 primitive cells clear both bars.**
The direction is unchanged — still negative at every horizon — so the engine
still pays +5 points for a quantity that ranks the wrong way; it is simply no
longer a statistically distinguishable finding. The holdout candidate registered
against it is weakened, not strengthened.

## Idiosyncratic volatility

| h | static | PIT | floor |
|---|--:|--:|--:|
| 1 | −0.0057 | +0.0311 | 0.060 |
| 3 | −0.0301 | +0.0488 | 0.084 |
| 6 | −0.0559 | +0.0672 | 0.119 |
| 12 | −0.1019 | +0.0731 | 0.188 |

Every horizon flips sign, and the mechanism verdict moves from
"indistinguishable" to "idiosyncratic materially cleaner". **Nothing clears a
floor.** `MAGNITUDE CHANGED, VERDICT UNCHANGED` — FAIL → FAIL.

## Short-term reversal

1M +0.0205 → **+0.0346** against a floor of 0.052, p 0.245; both halves
positive (+0.0301, +0.0386); turnover 87.9% → 89.0%.

`MAGNITUDE CHANGED, VERDICT UNCHANGED` — FAIL → FAIL. Closer to its floor, and
still short of it.

## Amihud — the largest change in the whole rerun

| h | static | PIT | floor |
|---|--:|--:|--:|
| **1 (primary)** | **+0.0435** | **−0.0140** | 0.0354 |
| 3 | +0.0823 | −0.0257 | 0.0458 |
| 6 | +0.1183 | −0.0074 | 0.0496 |
| 12 | **+0.1562** | **−0.0074** | 0.0535 |

Every horizon inverts. The decile spread goes +2.90pp → **−0.12pp**. All five
registered conditions now fail, where four of five previously held.

`MAGNITUDE CHANGED, VERDICT UNCHANGED` — FAIL → FAIL, and the registered FAIL
stands either way per the 2026-09-17 amendment.

**The consequence for the quarantined hypothesis is the point.** The
"long-horizon illiquidity premium" — 3M +0.0823, 6M +0.1183, 12M +0.1562, the
strongest apparent signal this project has produced — **does not survive a
historically correct universe.** It was an artefact of measuring illiquidity
across today's survivors: the names that were illiquid and then fell out of the
index were invisible to the static panel.

That hypothesis was quarantined at birth pending PIT size data. It should now
be recorded as **refuted on universe grounds**, before any size question is
even reached. No research budget was spent to learn this.

## Verdict summary

| study | static | PIT | changed? |
|---|---|---|---|
| Production composite | FAIL | FAIL | CONCLUSION UNCHANGED |
| Component study (overall) | FAIL | FAIL | CONCLUSION UNCHANGED |
| — `volumeRatio20D` 6M cell | significant | **not significant** | **CONCLUSION CHANGED** |
| Idiosyncratic volatility | FAIL | FAIL | MAGNITUDE CHANGED |
| Short-term reversal | FAIL | FAIL | MAGNITUDE CHANGED |
| Amihud | FAIL | FAIL | MAGNITUDE CHANGED |

**No registered verdict flipped from FAIL to PASS.** The only decision-boundary
crossing in the entire rerun made a finding weaker, not stronger.

## What did not happen

No production scoring change. No parameter, weight, horizon, cost or threshold
moved. No failed family was rescued. No new hypothesis was tested. No holdout
was spent. Research budget remains 2 of 3.
