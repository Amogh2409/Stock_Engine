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

**The decision to spend the window is therefore deferred to Tier 2**, where the
after-tax arithmetic at 600%+ turnover is computed. If acting on a confirmed
1-month reversal would not be profitable after Indian STCG at the turnover it
requires, then the correct action is to **not run this test at all** and to say
so. Learning that here is cheaper than learning it after the window is gone.

## 8. Status

**NOT RUN.** No reserved data has been read for this hypothesis.

When it is run, append below: the date, the command, `mean_ic`, `hac_t`, the
bootstrap CI, the verdict against §5, and the conclusion actually drawn.
