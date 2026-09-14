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
