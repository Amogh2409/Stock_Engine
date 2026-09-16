# Pre-registration — short-term reversal

**Status: registered, NOT RUN.** Committed before any result exists.

Second family under `knowledge/research-policy.md`. Spends **1 of the 3**
permitted further families.

## 0. Policy conditions, checked before writing this

| condition | how it is met |
|---|---|
| 1. Predates the previous result | Named in `bfb9fe8`, the volatility registration, which predates the volatility result `9da389a` |
| 2. Economic rationale | §1 below, stated before any measurement |
| 3. Materially distinct | The frozen family bets on *continuation* over 3–12 months; this bets on *mean reversion* over 21 sessions. Opposite sign, opposite horizon |
| 4. Point-in-time inputs | Daily closes only, from the calendar-corrected panel |
| 5. Specification fixed before execution | This file |
| 6. One primary specification | 21 sessions, no skip, no alternates |
| 7. Failure freezes the family | §7, with the repairs named |
| 8. A pass needs replication | §8 |

## 1. The hypothesis and why it could be true

> **Stocks with the most negative cumulative return over the previous 21
> trading sessions outperform over the following month.**

The mechanism is liquidity provision, not prediction. A stock pushed down by
concentrated selling pressure compensates whoever absorbs that pressure, and
the compensation is paid back as the order imbalance clears — over days and
weeks, not quarters. It is a claim about the price of immediacy.

This is **not** the inverse of the frozen momentum block. That block measures
3–12 month continuation. Reversal is a distinct, shorter-horizon effect that
the literature has long held can coexist with momentum, and the two are
measured over non-overlapping windows here.

## 2. The signal, fixed now

| | |
|---|---|
| **Formation** | previous **21 genuine trading sessions**, ending at the signal date |
| **Signal** | **negative** cumulative simple return over that window |
| **Skip** | **none** |
| **Direction** | a larger negative prior return ranks **higher** |
| **Minimum history** | **21 valid sessions** in the window, else not scored |
| **Rebalance** | monthly, the existing framework |
| **Winsorisation** | none — the pipeline is rank-based, so clipping cannot change an ordering (same reasoning as the volatility registration) |

### The sign, spelled out

The signal is **−(21-session cumulative return)**. So:

> **A POSITIVE IC supports reversal. A negative IC means momentum continued.**

Written down for the third time because it is the thing most easily got
backwards, and because here the wrong sign would not look absurd — it would
look like a momentum result and might be believed.

## 3. Horizons, and why 1 month is primary

- **Primary: 1 month.** Single horizon, single decision.
- **Diagnostic: 3, 6, 12 months.** Reported, never decisive.

This departs deliberately from the volatility registration, which demanded
consistency across horizons. The hypothesis here is explicitly *short-term*:
requiring a 21-session effect to persist at 12 months would be a test the
hypothesis does not predict passing, and failing it would say nothing. A
reversal effect that decays by 6 months is what the mechanism predicts, not
evidence against it.

The cost is that a single primary horizon has no cross-horizon consistency
check to lean on. §6 compensates by tightening what the one horizon must show.

## 4. Universe, costs, detection

- Universe and eligibility: the engine's own refusal in `rank_on`, as before.
- Pre-holdout only; `HOLDOUT_START = 2023-01-01` untouched.
- Costs: existing framework, 15 bps per side, `DEFAULT_TOP_N = 20`.
- Detection: HAC at lag `horizon − 1`, the 80% power floor, stationary
  bootstrap (2000 draws, seed 20260913), Bonferroni.

**Turnover is a first-class concern here, not a footnote.** A 21-session signal
re-ranks fast, and reversal is the one family where costs can plausibly consume
the entire effect. Turnover and the cost-adjusted spread are reported with the
primary result, not below it.

## 5. Multiple testing

**Family size: 4** — one estimator at four horizons. All four are computed and
read; only the 1-month cell can produce a pass.

Smaller than the volatility study's 8 because there is no second estimator.
There is no mechanism check here: the signal has one definition and nothing to
compare it against that would not be a second specification.

## 6. The decision rule, fixed now

Reversal **passes** only if **all four** hold at the **1-month** horizon:

1. **Detection.** `mean IC ≥ detectable_ic_80pct` for that cell.
2. **Significance.** `hac_p_bonferroni < 0.05` at family 4.
3. **Economic separation after costs.** Decile spread (Q1−Q10) **positive and
   greater than 0.30pp** — 15 bps per side, both legs. (The volatility
   registration mis-stated this as 0.60pp; the arithmetic is corrected here.)
4. **Persistence of sign.** Positive mean IC in **both** halves of the
   pre-holdout window, split at the median rebalance date.

Condition 4 replaces the cross-horizon consistency that a single primary
horizon cannot provide. A one-month effect that appears in only one half of an
eleven-year sample is a regime, not a factor, and this is the cheapest check
that distinguishes them without spending the holdout.

**Sign is not free.** A significantly negative IC means momentum continued at
this horizon. That is a different hypothesis, is not registered, and does not
pass inverted.

## 7. On FAIL

> **The short-term reversal family is frozen.**

Named in advance, because each is a move that will look reasonable afterwards:

- no changing 21 → 5, 10, or 63 sessions;
- no adding a skip period of 3 days or 1 week;
- no residualising momentum, beta, or sector out of the signal;
- no volatility or liquidity screen to "clean up" the universe;
- no switching from cumulative return to a z-scored or ranked variant;
- no moving the primary horizon to 1 week because 1 month disappointed.

Under the policy this also spends 1 of 3 families whatever the outcome.

## 8. On PASS

A pass makes reversal a **candidate**, not a component.

1. Not merged into the technical score, at any weight.
2. Replicated as an independent factor, with its own turnover and costs — and
   given the turnover concern in §4, a pass whose spread does not survive its
   own trading costs is **not** a pass in any practical sense, and must be
   reported as such even if it clears condition 3.
3. Incremental value over the frozen composite tested as its own registered
   question.
4. Only then does a holdout rung come into view.

## 9. Caveats recorded in advance

- ~89 names per date, ~9 per decile; the extreme buckets are the noisiest part.
- 21 sessions is roughly one rebalance interval, so formation and the forward
  month abut. There is no overlap and no look-ahead — formation ends at the
  signal date and the trade fills at the next session's open — but the two
  windows are adjacent, and any microstructure effect spanning the boundary
  would land in both.
- The frozen momentum block already contains a mechanical short-horizon
  element; the diagnostic correlation between this signal and the twelve frozen
  primitives is reported so that "distinct family" is checked rather than
  asserted.
- Survivorship: the universe is the current Nifty 100 applied to past dates.
- Size remains unavailable point-in-time and is not a diagnostic here.
