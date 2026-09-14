# Three exit rules, proposed and not implemented

The engine produces **entries only**. Against a stated goal of buy/sell guidance
that is the largest functional gap, and it has been open since the project
started: a holding leaves the book when next month's re-rank drops it, which is
not an exit rule but the absence of one.

These are proposals. **None is implemented, and none should be until it has been
tested** — a stop level chosen because it improved a backtest is a fitted
parameter, and this project has spent a great deal of effort not doing that.

One thing to hold in view throughout: **rank buffering already cut turnover by
more than half and raised gross return** (rung C monthly, 583% → 256%, 20.31% →
24.76%). Any exit rule has to beat that, and buffering is free. An exit rule that
adds turnover has to earn its tax bill, which §2 of `rulebook.md`'s Tier 2
section puts at **3.48pp a year** at monthly frequency.

---

## 1. Volatility stop — exit at 2 × ATR below the entry price

**The rule.** On entry, record `entry - 2 * ATR(14)`. Exit at the next session's
open if the close breaches it. Re-entry only at a subsequent rebalance.

**Why this one first.** It is the only one of the three with a source already in
the rulebook. `STOP_ATR_MULTIPLE = 2.0` exists in `engine.py` for position
sizing, and the rulebook records it as **Adapted** — TSaM pp.1055–1056 ties the
stop multiple to the trend period and its own multiples are not 2. So the
parameter is already written down, already sourced-with-a-caveat, and already
used for sizing. Applying it to exits is the smallest new claim available.

**How it would be tested.**

- Add `--stop-atr N` to `backtest.py`, defaulting to off. Never to `engine.py`:
  this is a measurement variant and the shipped engine must keep scoring what it
  ships, which is the rule `--rsi-flip` established.
- The comparison is **rung C with the stop against rung C without it**, on the
  pre-holdout window, with the universe asserted identical — the guard
  `test_every_strategy_benchmark_pair_covers_the_same_months` already exists and
  would cover it.
- Report the **paired** monthly return difference with a HAC standard error at
  lag 0, not two separate CAGRs. The difference is the estimand.
- Report turnover and after-tax return at ₹10 lakh, because a stop that fires
  often converts long-term gains to short-term ones and the tax arithmetic is
  where these rules usually die.
- **The pre-registered failure branch**: if the paired difference straddles zero
  — which is the expected outcome given every other result here — the rule is
  recorded as tested and not adopted, and `STOP_ATR_MULTIPLE` stays a sizing
  constant.
- **Do not sweep N.** Testing 1.5, 2.0, 2.5 and 3.0 and reporting the best is the
  search this project has spent 125 cells learning to distrust. Test 2.0, because
  2.0 is what is already written down.

**What would make it interesting rather than merely null.** If the stop cuts
drawdown materially while leaving the CAGR difference straddling zero, that is a
real result — the engine's max drawdown is −28.11% and a rule that reduces it
without costing return is worth having even with no measurable alpha.

---

## 2. Rank-decay exit — leave when the score falls below its own entry percentile

**The rule.** Record the holding's cross-sectional percentile at entry. Exit when
it falls more than *k* percentile points below that, rather than when it leaves a
fixed top-N band.

**Why it is different from buffering.** Buffering is absolute — top 2N or out.
This is relative to where the name started, so a holding bought at the 99th
percentile is sold on a drop to the 70th, while one bought at the 55th survives
the same absolute move. It targets *deterioration* rather than *rank*.

**How it would be tested.**

- `--rank-decay k` in `backtest.py`. The natural comparison is a **three-way**:
  no exit rule, buffering at 2N, and rank-decay — because the interesting
  question is not whether it beats doing nothing but whether it beats the cheap
  thing that already works.
- The IC is unchanged by construction — this changes which names are held, not
  the ranking — so **do not report an IC per variant**. That error was made once
  in Tier 2 and caught; reporting one number three times as a trade-off is worse
  than reporting nothing.
- Report turnover, gross and after-tax CAGR, and the paired difference against
  buffering with its interval.
- **k must be fixed in advance**, and the honest choice is a round number with a
  stated rationale (25 points = one quartile), not a swept optimum.

**The obvious failure mode, stated in advance.** At 1-month horizon the score's
IC is −0.0033; if the score does not rank returns, a rule that acts on *changes*
in the score is acting on changes in noise, and should show up as pure added
turnover. That is a clean falsifiable prediction and worth making before running.

---

## 3. Time-based exit — hold exactly twelve months and one day

**The rule.** Every position is held to LTCG qualification regardless of rank,
unless a hard stop fires. Rebalance adds new names only into cash from matured
exits.

**Why it is worth proposing despite pointing the wrong way.** It is the only
proposal that attacks the **structural tension** identified in Tier 2 head-on:
the only horizon with a signal is the only horizon that can never reach LTCG, and
the incremental tax cost of monthly trading is 3.48pp a year. A 12-month hold
converts essentially all realised gains from 20% to 12.5% and consumes the ₹1.25
lakh exemption, which on the measured figures is worth roughly 3pp.

**And it almost certainly destroys the signal**, which is the point of testing it
rather than arguing about it. The momentum IC decays 1m → 12m as −0.0407 →
−0.0111, and at 12 months it is nowhere near its floor of 0.0356. The quarterly
variant already measured this in miniature: turnover 134%, after-tax return up,
signal gone.

**How it would be tested.**

- `--min-hold-months 12` in `backtest.py`.
- The comparison must be **after-tax on both sides at a stated capital**, with
  equal weight built on the strategy's own periods. Building it any other way
  reintroduces the benchmark-alignment defect that has now occurred twice.
- Report the realised short/long split, which is the diagnostic that says whether
  the rule did what it claims.
- **The interesting number is not the CAGR.** It is whether the tax saving
  (~3pp) exceeds the signal loss. Those can be reported separately: the gross
  CAGR difference is the signal cost, the tax-drag difference is the saving, and
  the rule is worth adopting only if the second exceeds the first.
- Expected outcome: **it does not**. The gross edge at 1 month is 5.38pp and the
  12-month IC is inside its floor, so a 12-month hold plausibly gives up more
  than 3pp of gross to save 3pp of tax. If that is what comes back, the finding
  is that **the tension is unresolvable at this signal strength**, which closes a
  question rather than leaving it open.

---

## What all three share

- They go in `backtest.py`, never `engine.py`. The scoring hash must not move.
- They are measured on the **pre-holdout window only**, and every figure they
  produce is exploratory and adds to a search count already past 125.
- Each needs its failure branch written down **before** it runs, because all
  three have an obvious way to look good on one window.
- None of them should be adopted on a measured improvement alone. The only
  adoption this project has made — the skip month — rested on a citation, with
  the measurement showing the change cost nothing rather than serving as the
  reason. That is the standard.
