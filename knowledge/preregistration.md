# Pre-registration — momentum block, 1-month, neutralised

**Written 2026-09-14, before any holdout data was touched.** Committed before
any further measurement. Nothing in this file may be revised after the reserved
window is read; a revision after the fact makes it not a pre-registration.

**The holdout test described here has NOT been run.**

---

## 1. The cell

Exactly one cell. One variant, one block, one horizon, one statistic.

| | |
| --- | --- |
| Variant | Rung C — continuous scoring, sector- and size-neutralised |
| Block | `momentum` |
| Horizon | 1 month |
| Statistic | Spearman rank IC of block subtotal against forward return |
| Universe | The same eligibility gate as the shipped engine |
| Features | The current engine's twelve, unchanged. `engine.py` is untouched |

**The divisor is 1.** That is the whole point of naming one cell in advance. A
test across four horizons and five blocks would put the divisor back at 20 and
reset the argument this file exists to make.

## 2. What was observed pre-holdout

Rung C, `data-store/reports/rung_c_neutral/`, 86 traded periods,
2015-10-30 to 2022-11-30.

| h | IC | iid t | HAC t | boot t | floor | bootstrap 95% CI | p×20 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **1m** | **−0.0407** | −3.03 | **−3.05** | −3.10 | 0.0380 | **[−0.0673, −0.0154]** | **0.061** |
| 3m | −0.0308 | −2.33 | −2.84 | −2.95 | 0.0314 | [−0.0518, −0.0115] | 0.170 |
| 6m | −0.0185 | −1.40 | −2.10 | −2.16 | 0.0266 | [−0.0350, −0.0023] | 1.000 |
| 12m | −0.0111 | −0.72 | −1.07 | −1.09 | 0.0356 | [−0.0327, +0.0089] | 1.000 |

n = 86, df = 85 (no overlap at 1 month), HAC SE 0.013344, ic_sd 0.124474.

**The magnitude decays monotonically with horizon** — 0.0407 / 0.0308 / 0.0185 /
0.0111 — which is the shape a short-horizon reversal effect should have, and is
not what a spurious cell would be expected to produce by construction. It is
weak evidence and it is recorded as weak evidence.

## 3. The prediction

**NEGATIVE. The momentum block as scored is anti-predictive at one month.**

Stated as a direction and not as a magnitude, deliberately. The pre-holdout
estimate was selected out of a search and its magnitude is therefore biased away
from zero. Predicting −0.0407 would be predicting the selection bias along with
the effect.

## 4. The prior, and why this cell is different from relative strength

`knowledge/rulebook.md` lines 597-617 already carried this hypothesis **before
the ladder was built**, tagged Contradicted:

> Awarding points for a high RSI treats it as a **continuation** signal… TSaM
> does not settle this in our favour. The one piece of evidence it offers
> (pp. 389–390 …) is that **the sign flipped**. Before roughly 1998 the RSI
> worked as a trend indicator… After 1998 it has been "a much better
> mean-reverting indicator"… **This rule is a live hypothesis, not a documented
> finding.** Testing the mean-reversion sign is the single highest-value
> experiment available.

That entry predates this measurement. **A hypothesis written down before the
search is not selected by it** — which is precisely what the exploratory policy
in `rulebook.md` says it cannot offer for a search-found cell. Relative strength
at 6 months has no such prior and is not pre-registered.

## 5. The decision rule, fixed now

Run **once**, on the reserved window from 2023-01-01, at the 1-month horizon,
rung C, momentum block. `--no-respect-holdout`, one invocation.

**PASS** requires all three, and they are conjunctive:

1. `mean_ic < 0` — the predicted sign;
2. `hac_t ≤ −2.0167` — the two-sided 5% critical value at df 43, divisor 1;
3. the 95% bootstrap CI lies entirely below zero.

**FAIL** is anything else, including a negative IC that misses (2) or (3).

### On PASS

Conclude: **the directional prediction, written down before the search, held on
data never used to find it.** That is evidence the momentum block is
anti-predictive at one month.

It does **not** establish the magnitude — the pre-holdout figure is selected and
biased. It does **not** establish which feature is responsible (see §6). It does
**not** license adoption on its own: whether acting on it is *profitable* is a
separate question, decided by the after-tax turnover arithmetic in Tier 2, not
by this test.

### On FAIL

Conclude: **the prediction did not hold.** No adoption. The RSI sign stays as
shipped, and the rulebook entry moves from "live hypothesis" to "tested once,
not supported".

Do **not** conclude the effect is absent. See §7 — this test has 56% power
against the effect it was built to detect, so a fail is close to a coin toss
even if the effect is real and exactly as large as observed.

Either way, **the window is spent** and this file is updated with the date, the
figure, and the verdict.

## 6. Caveats recorded in advance

- **The block is two features, and attribution is NOT established.** `momentum`
  is MACD (15 points) + RSI (15 points), equally weighted. The prior in §4 is
  about RSI only. A pass would support "the block is anti-predictive", not "the
  RSI sign is wrong". Decomposing the block on pre-holdout data is deliberately
  not done before this test is run, because doing so would add cells to a search
  whose count is already the problem.
- **p×20 = 0.061 does not clear correction** on the pre-holdout window. This cell
  is not significant there and is not claimed to be.
- **The search count is 80+ cells and is a lower bound** — design choices are
  degrees of freedom too. The prior in §4 is what separates this cell from the
  rest of that search; it is not a claim that the search was small.
- **Neutralisation is part of the cell.** Rung C uses a sector map that is a
  snapshot as of 2026-09-10 (stale, mild look-ahead) and a size control that is
  log trailing median turnover — a liquidity proxy, **not** market cap.
- **Every standard error in this project understates**, by roughly a quarter at
  the longer horizons, measured against a series with known true SE. At 1 month
  there is no overlap, so this cell is the least affected.

## 7. What this test can and cannot see — read before deciding to spend it

The reserved window holds **44 traded periods** (the cut surrenders 44 of 130, a
figure already published in the guide; no holdout return was read to obtain it).

| | |
| --- | --- |
| n | 44 |
| SE of the mean, carrying rung C's ic_sd | 0.018765 |
| t critical, df 43 | 2.0167 |
| **Detection floor at 80% power** | **0.0536** |
| Observed pre-holdout \|IC\| | 0.0407 — **below the floor** |
| t if the effect repeats exactly | 2.167 |
| **Power at α = 0.05** | **56%** |

**The effect this test was designed to detect is smaller than the effect the
test can reliably detect.** If the truth is exactly the pre-holdout figure, this
test fails 44% of the time. That is the single most important number in this
file.

It does not make the test worthless — 56% is far better than the pre-holdout
window's own power against a realistic effect — but it does mean a FAIL carries
little information, while a PASS carries a lot.

### The window is not a fixed asset — there are three options, not two

The reserved window gains one period a month, so its power against this effect
grows. Re-derived from the momentum block's own ic_sd at rung C (0.124474) and
the observed |IC| (0.040666), using `_t_critical` and a normal approximation to
the noncentral t:

| n | when | floor at 80% power | t if the effect repeats | power | effect vs floor |
| --- | --- | --- | --- | --- | --- |
| 44 | now | 0.0536 | 2.167 | **56%** | below floor |
| 56 | +1 year | 0.0473 | 2.445 | 67% | below floor |
| 68 | +2 years | 0.0428 | 2.694 | 76% | below floor |
| 76 | **+2.7 years** | 0.0405 | 2.848 | **80%** | **above floor** |
| 80 | +3 years | 0.0394 | 2.922 | 82% | above floor |

**This assumes ic_sd and the effect both stay where the spent window put them.**
Both are estimates from the same 86 periods, and neither is guaranteed forward.

So the options are:

1. **Spend now.** A 56% test. A pass is informative; a fail is close to a coin
   toss and the window is gone either way.
2. **Do not spend at all**, if Tier 2's after-tax arithmetic shows that acting on
   a confirmed reversal is unprofitable at 583–733% turnover. Then the test
   answers a question whose answer cannot be used.
3. **Wait.** Power reaches 80% at n = 76, about 2.7 years from now. `rulebook.md`
   names exactly this as one of only two legitimate routes: "either a period held
   back and never examined, or forward paper-trading from today"
   (`rulebook.md:962`).

**The counterargument to waiting is serious and is not resolved here.** Waiting
assumes the effect is stationary, and the prior in §4 says the opposite.
`rulebook.md:619-628` puts it plainly: the RSI sign flipping inside a single
market means "its sign is **regime-dependent**, and a fixed +15 for RSI > 50
encodes a constant where the source documents a variable… the risk is not merely
that the rule is unproven; it is that the rule is **directionally wrong in some
regimes**". Three years of waiting is three years of regime risk on a hypothesis
whose defining property is that its sign is unstable — and a test run in 2029
over 2023–2029 may be averaging regimes that disagree, which is the same defect
that made the original US evidence unusable.

Both sides are recorded and **neither is chosen here**. Tier 2 may make the
choice moot, which is the cheapest way to resolve it: if the after-tax answer is
no, options 1 and 3 both collapse into option 2.

**The decision to spend the window is therefore deferred to Tier 2**, where the
after-tax arithmetic at 600%+ turnover is computed. If acting on a confirmed
1-month reversal would not be profitable after Indian STCG at the turnover it
requires, then the correct action is to **not run this test at all** and to say
so. Learning that here is cheaper than learning it after the window is gone.

## 8. Status

**NOT RUN.** No reserved data has been read for this hypothesis.

When it is run, append below: the date, the command, `mean_ic`, `hac_t`, the
bootstrap CI, the verdict against §5, and the conclusion actually drawn.

---

## 9. Amendment log

Appended, never rewritten. Sections 1–8 are as originally committed at `2536a0d`.

### 2026-09-14 — the engine's relative-strength window changed

`engine.py` now skips the most recent month in relative strength
(`RELATIVE_STRENGTH_SKIP_SESSIONS`), sourced for the 12-month leg by CFA
`rf-v2016-n4-1#71`. §1 says "engine.py is untouched", which was true when
written and is no longer.

**The pre-registered cell is unaffected, and this was verified, not assumed.**
Rung C regenerated on the changed engine:

| | before | after |
| --- | --- | --- |
| momentum / trend / volume blocks | — | **bit-identical** |
| scoreable universe, all 86 periods | — | identical |
| momentum 1m `mean_ic` | −0.040666455273968276 | −0.040666455273968276 |
| momentum 1m `hac_t` | −3.0475295241371669 | −3.0475295241371669 |
| bootstrap CI | [−0.067347, −0.015366] | [−0.067347, −0.015366] |
| relStrength 6m (the change is live) | +0.0413 | +0.0485 |

`test_relative_strength_cannot_disturb_the_preregistered_cell` asserts it, with a
guard that the fixture actually moves relative strength.

**Nothing in §§1–7 changes**: not the cell, not the prediction, not the decision
rule, not the power analysis. The features named in §1 are still the engine's
twelve; one of them is now measured over a window a source states. The holdout
test remains **NOT RUN**.

### 2026-09-14 — the bootstrap percentile index was off by one rank

Audit finding 7. `means[int(0.025 * draws)]` took index 50 of 2000 where the
nearest-rank 2.5th percentile is index 49; both tails were off by one.

**§2's published bootstrap CI moves by that one rank**, from
**[−0.0673, −0.0154]** to **[−0.0675, −0.0155]**. §2 is not rewritten — that is
what an amendment log is for — and the superseded pair is recorded here so a
reader comparing the two knows which is current.

Everything else in the cell is unchanged to every stored digit: `mean_ic`
−0.040666455273968276, `hac_t` −3.0475295241371669, `ic_t` −3.0297595211989994,
`bootstrap_t` −3.0980523911121942, floor 0.037983442542370106, p×20
0.061481547200361045.

**The decision rule in §5 is unaffected.** It tests the sign, `hac_t ≤ −2.0167`,
and whether the CI lies entirely below zero. The corrected interval still lies
entirely below zero, and the t did not move.

The holdout test remains **NOT RUN**.

### 2026-09-14 — Tier 2 answers the question §7 deferred

§7 deferred the spend decision to the after-tax arithmetic, and said plainly that
if acting on a confirmed reversal were unprofitable at 583–733% turnover, the
correct action was to **not run this test at all**.

**That branch is now closed, and closed against the expectation.** Measured on
the pre-holdout window, holding the 20 lowest-momentum names monthly on rung C
scoring:

| | turnover | gross | after 20% | vs after-tax equal weight |
| --- | --- | --- | --- | --- |
| no buffer | 964% | 28.67% | 22.07% | **+1.90pp** |
| buffer 2N | 710% | 29.97% | 23.19% | +3.02pp |

At a retail ₹10 lakh, s.112A exemption applied to **both** sides, equal weight
measured over the **same 86 months**.

Two superseded versions of this row, both corrected on 2026-09-14 and both
wrong in the strategy's favour. The first read **+5.26pp**, computed with the
exemption off — which taxes long-term gains from the first rupee and so
penalises equal weight at 97.1% long-term while the reversal at 100% short-term
consumes none of it. The second read **+4.37pp**, computed against a 95-month
equal-weight book while the strategy ran 86 — a 7.92-year CAGR differenced
against a 7.17-year one, which is the benchmark-alignment defect `c96780d`
fixed for the performance table and which returned in a code path that bypassed
`align_to()`.

The incremental tax cost of trading monthly at that turnover is **3.48pp a
year** against a gross edge of 5.38pp — the hurdle is real, it is clearable, and
it takes about two thirds of the advantage. **Tax does not make this
untradeable, but it leaves little.** (An earlier draft put the hurdle at 3.23pp,
computed against a 95-month equal-weight book; superseded.)

**What does not clear is the edge itself.** Paired bootstrap on the CAGR
difference: +5.38pp, 95% CI **[−0.01, +11.94]**, p 0.051 unbuffered; +6.68pp, CI
[−0.12, +13.64], p 0.053 buffered. It straddles zero unadjusted, and the search
is now 125+ cells.

**So the decision is NOT made here, because the ground for making it changed.**
The "do not spend, it is untradeable" argument is withdrawn — it was the cheapest
available reason to skip the test and it turned out to be false. What remains is
the argument in §7 that was always the real one: the test has **56% power**, and
the effect it looks for sits below its own detection floor.

Three options stand, unchanged in substance and now unchanged by tax:

1. **Spend now** at 56% power.
2. **Wait** — 80% power at n = 76, about 2.7 years, against the regime risk in §7.
3. **Do not spend**, on power grounds alone rather than on tax grounds.

The holdout test remains **NOT RUN**, and nothing in §§1–7 is altered.

### 2026-09-16 — two fundamental-side fixes; the cell is unchanged

An external code review of the engine's design produced three claims of material
bugs. All three were checked by running the code and **all three were wrong**:
the bank model is a 100-point five-bucket model, not a 50-point one (a perfect
bank and a perfect non-financial return identical totals from equivalent
inputs); negative P/E already scores zero rather than full marks; and portfolio
volatility is already correlation-aware, being the standard deviation of the
portfolio's own return series.

Two of the review's smaller points were correct and are now fixed:

- `hard_red_flags` no longer infers negative net worth from a negative
  debt-to-equity ratio. The inference only holds for GROSS-debt providers; a
  NET-debt provider gives a negative ratio to a company with more cash than
  debt. Equity is tested directly when present, price-to-book otherwise.
- `grossNpa` moved from `BANK_REQUIRED_FIELDS` to `BANK_OPTIONAL_FIELDS`. It
  carries no points, so requiring it blocked lenders over a field never read.

**THE PRE-REGISTERED CELL IS UNAFFECTED, AND THIS WAS VERIFIED, NOT ASSUMED.**
`python/backtest.py` holds zero references to fundamentals, red flags or bank
fields, so neither change can reach the measurement. Rung C was regenerated on
the changed engine and the cell came back bit-identical:

| | before | after |
| --- | --- | --- |
| `mean_ic` | −0.040666455273968276 | **identical** |
| `hac_t_stat` | −3.047529524137167 | **identical** |
| `bootstrap_ci_lo` / `hi` | −0.06747798313532546 / −0.015490827037360294 | **identical** |
| `detectable_ic_80pct` | 0.037983442542370106 | **identical** |

`SCORING_HASH` moved (`8ed6a95f…` → `e2cebaa9…`) because `BANK_REQUIRED_FIELDS`
is a module constant the guard hashes. It is re-recorded in this same change, as
the guard's own failure message requires.

**Nothing in §§1–7 changes**: not the cell, not the prediction, not the decision
rule, not the power analysis. The holdout test remains **NOT RUN**.

One change the review asked for was deliberately NOT made. Replacing the
one-year operating-cash-flow rejection with a multi-year test changes which
companies are admitted, which makes it a hypothesis rather than a correctness
fix. It is registered here as an experiment to be benchmarked against the
current rule, and must not be adopted on plausibility alone.

### 2026-09-16 — the technical family is measured out to its primitives, and stops

The composite measured a powered null; so did all four blocks. A sum can hide an
offsetting pair, so the objection survived down to `CONTINUOUS_FEATURES` — the
twelve raw quantities the score is built from. Each was ranked on alone, at
1/3/6/12 months, with two per-date correlation matrices and four
leave-one-block-out composites. Family size 80.

The decision rule was written and committed **before** the results were opened;
`git log` orders the two commits. It lives in
[component-stop-condition.md](component-stop-condition.md), which also holds the
outcome.

**Outcome: FAIL.** No primitive clears detection and family-corrected
significance together. The one cell that clears both — `volumeRatio20D` at 6
months, IC −0.0639 — is negative, and the engine pays +5 points for the quantity
it says to avoid. Leave-one-out agrees that the volume block subtracts at every
horizon, though no leave-one-out variant clears its own floor.

Per the FAIL branch, now in force: **no reweighting, no new indicator, no
threshold retuning inside the technical factor family.** Acting on the volume
result is a new hypothesis formed by looking at these results and needs its own
cell on the holdout ladder — with the liquidity confound (the effect sits in the
lowest-volume decile, where the flat 15 bps cost is least believable) stated in
advance.

The cell registered at the top of this file is untouched. This run changes no
score; `--components` is a measurement flag.

### 2026-09-16 — a second family is registered, and not yet run

The technical family reached its FAIL branch and was re-frozen on a corrected
panel. The first hypothesis from a genuinely different family is registered in
[preregistration-idiosyncratic-volatility.md](preregistration-idiosyncratic-volatility.md):
lower idiosyncratic volatility predicts better cross-sectional performance.

Registered ALONE. Reversal, betting-against-beta, MAX and illiquidity are not
registered and must not be measured in the same run.

**Not run.** The file is committed before any result exists, and its hash is
recorded in the commit that follows it.

### 2026-09-16 — low volatility FAILED; a research budget is imposed

The idiosyncratic-volatility family failed its registered rule: 0 of 4 horizons
positive where 3 were needed, none detected, every decile spread negative, and
the idio-versus-total mechanism check indistinguishable. Frozen.

Two negative results in a row make the next danger a search rather than a test,
so `knowledge/research-policy.md` now caps price-only alpha research at **2-3
further families** and sets eight conditions a new family must meet. BAB is
QUARANTINED: the volatility study's beta diagnostic made it attractive, which
is precisely what disqualifies it from this cycle.

Short-term reversal is registered in
[preregistration-short-term-reversal.md](preregistration-short-term-reversal.md)
and spends 1 of 3. **Not run.**
