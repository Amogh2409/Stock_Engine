# Pre-registration — idiosyncratic volatility

**Status: registered, NOT RUN.** Committed before any result exists. The commit
order is the evidence; `git log` is the audit trail. Nothing in this file may be
revised after a number has been seen except through a dated amendment that says
what changed and why.

This is the first hypothesis from a factor family other than the frozen one. It
is registered alone. Reversal, betting-against-beta, MAX and illiquidity are
**not** registered here and must not be measured in the same run — one family
at a time, or the multiple-testing accounting becomes fiction.

## 1. The hypothesis

> **Lower historical idiosyncratic volatility predicts better subsequent
> cross-sectional performance among Nifty 100 constituents.**

Directional and cross-sectional. It is not a claim about the market, about
timing, or about absolute returns.

### Why this is a different family, not a variation

The frozen family — trend, momentum, relative strength, volume — measures the
*direction and persistence* of price. This measures the *dispersion of the part
of price that the benchmark does not explain*. The component study showed the
frozen family's twelve primitives are roughly three correlated bets; if
idiosyncratic volatility were a fourth copy of them, that would show up as a
high cross-sectional correlation with the existing primitives, and §8 measures
exactly that as a diagnostic.

## 2. The signal, fixed now

| | |
|---|---|
| **Formation window** | **126 trading sessions**, ending at the signal date |
| **Estimator** | OLS of daily stock return on daily benchmark return over the window; idiosyncratic volatility is the **standard deviation of the residuals** |
| **Benchmark** | `^NSEI`, the repo's existing benchmark (see caveat below) |
| **Returns** | simple close-to-close, on genuine sessions only |
| **Minimum observations** | **at least 100 valid session returns** inside the 126-session window, else the stock is **not scored** at that date |
| **Ranking direction** | **lower idiosyncratic volatility ranks higher** |
| **Signal fed to the IC** | **negative** idiosyncratic volatility |

126 sessions is the primary window and the **only** window. It is roughly six
months, long enough for a residual standard deviation to be estimated from ~126
points and short enough to describe the recent regime. 63 and 252 are not
alternatives to be tried later; see §9.

### The sign convention, stated explicitly

The repo's IC is computed between the signal and the forward return, and the
engine's convention is that a **high score is good**. So the signal is
**−idiovol**, and therefore:

> **A POSITIVE IC supports the hypothesis. A negative IC refutes it.**

This is written down because the single most consequential finding of the last
study was a sign, and a pipeline that fed raw idiosyncratic volatility would
report the correct result with the opposite sign and be read backwards.

### Winsorisation: NONE, and the reason is not laziness

Declared now: **no winsorisation of the signal.** Not as a preference, but
because it would be inert. The primary metric is Spearman rank IC and the
secondary decile assignment is also rank-based, and **winsorisation cannot
change a rank** — clipping the 1st and 99th percentiles to their boundary
values leaves the ordering identical. Declaring a winsorisation rule here would
be a ritual that changes no number.

It would matter if the raw values were used — in a regression, or in a
value-weighted portfolio. They are not. Forward **returns** enter raw into
decile mean returns, exactly as the existing study treats them; they are not
winsorised either, because "the existing framework unless there is a compelling
pre-results reason" is the standing instruction and there is none.

If any later analysis uses the raw values, that analysis needs its own
registration.

## 3. Universe and eligibility

The **same point-in-time rules the technical study already uses**: at each
rebalance date a stock is eligible only if the engine can score it as at that
date, via the engine's own refusal in `rank_on`. No separate liquidity or size
filter is introduced — introducing one would be a new degree of freedom and
would also confound §8.

Recorded, not fixed: the universe is the **current** Nifty 100 applied to past
dates. Survivorship biases every figure optimistically and is not corrected.

## 4. Rebalance and horizons

- Monthly, on `month_end_sessions`, the existing framework.
- **Pre-holdout only.** `respect_holdout=True`; the window from
  `HOLDOUT_START = 2023-01-01` is not touched.
- Forward horizons **1, 3, 6 and 12 months**, matching `DECILE_HORIZONS`.

A PASS here does **not** authorise spending the holdout. That is a separate
registration with its own rung.

## 5. Metrics

**Primary:** Spearman rank IC between −idiovol and forward return, per
rebalance date, at each horizon.

**Secondary,** reported always, never used to overturn the primary:
decile spread (Q1−Q10), monotonicity as rising/falling steps of 9, turnover,
maximum drawdown of the decile-1 portfolio, and hit frequency (share of dates
with IC > 0).

**Costs:** exactly the existing framework — `DEFAULT_COST_BPS_PER_SIDE = 15.0`,
`DEFAULT_TOP_N = 20`. Unchanged, despite a known reason to doubt a flat cost in
the least liquid names: changing it here would confound a cost question with a
factor question, and the low-volatility tail is not the same as the illiquid
tail. If costs are to be modelled properly that is its own change, applied to
every study at once.

**Detection:** the framework the repo already trusts, unmodified — HAC standard
errors at lag `horizon − 1`, effective degrees of freedom `n // h`, the 80%
power floor `detectable_ic_80pct`, the stationary bootstrap at
`BOOTSTRAP_DRAWS = 2000` and `BOOTSTRAP_SEED = 20260913`, and Bonferroni.

## 6. Multiple testing, declared before the run

**Family size: 8.** Two estimators (§7) at four horizons.

The decision in §9 keys **only** on idiosyncratic volatility, so on a strict
reading only 4 cells could produce a claim. Family 8 is declared anyway,
because all 8 will be computed and read, and a correction that counts only the
cells hoped to win is not a correction. This is deliberately conservative and
costs power; that is the intended direction of the error.

## 7. The mechanism check: total vs idiosyncratic volatility

Total volatility — the standard deviation of raw daily returns over the same
126 sessions, same minimum observations, same direction — is computed
**alongside** idiosyncratic volatility.

This is **not a second attempt at significance.** Total volatility cannot
produce a PASS; §9 does not consult it. It answers a different question:

- **Both behave alike** → the effect is generic low-volatility, and the
  residualisation against the benchmark is doing no work. That is a weaker and
  much more crowded claim.
- **Idiosyncratic is materially cleaner** → the benchmark-orthogonal component
  carries the information, which is a different and more specific finding.
- **Total is cleaner** → the hypothesis as stated is wrong even if something
  nearby is right, and what is nearby is not registered here.

"Materially cleaner" is fixed now as: idiosyncratic volatility's mean IC
exceeds total volatility's **by at least 0.02 at a majority of horizons (3 of
4)**, in the same direction. Anything less is reported as "indistinguishable".

## 8. Confound diagnostics — measured, NOT neutralised

Reported as per-date cross-sectional Spearman correlations between the signal
and each of:

- **beta** — the OLS slope from the same regression, free;
- **size** — market capitalisation at the signal date;
- **liquidity** — median daily traded value over the same 126 sessions.

Summarised mean / median / P25 / P75, per date then aggregated, never pooled
into one matrix — the same treatment the component study used, for the same
reason.

**These are diagnostics.** No neutralisation is performed. A sector-, size- or
beta-neutral version of this factor is a **different hypothesis** and needs its
own registration; running one after seeing these results would be the
specification search this file exists to prevent.

Also reported diagnostically: the correlation between −idiovol and each of the
twelve frozen `CONTINUOUS_FEATURES`, to establish whether this is genuinely a
new family or a fourth copy of the existing three bets.

## 9. The decision rule, fixed now

Idiosyncratic volatility **passes** only if **all four** hold. Conjunctive, not
best-of, and identical in form to the rule the frozen family failed:

1. **Detection.** `mean IC ≥ detectable_ic_80pct` for that cell.
2. **Significance after the family.** `hac_p_bonferroni < 0.05` at family 8.
3. **Economic separation.** Decile spread (Q1−Q10) **positive** and above the
   round trip it implies — **0.60pp** at 15 bps per side, both legs.
4. **Horizon consistency.** Same IC sign at **≥3 of 4** horizons, and
   conditions 1–2 met at **≥2** of them.

**Sign is not free**, exactly as before: a significantly *negative* IC refutes
the hypothesis rather than passing it inverted. "High idiosyncratic volatility
predicts returns" is a different hypothesis and is not registered.

### On FAIL

> **This family is frozen on the same terms as the technical family.** No
> changing 126 → 63 → 252 sessions. No switching the benchmark from `^NSEI` to
> `^CNX100`. No adding a liquidity screen, a size screen, or a neutralisation
> to see whether the effect appears. No swapping the residual standard
> deviation for a downside or EWMA variant.

Each of those is a specification search, and each is listed because each is a
move I can imagine making after a disappointing number.

### On PASS

A pass makes this a **candidate**, not a component of the engine.

1. **It is not merged into the technical score.** Not at any weight.
2. It is first **replicated as an independent factor** — its own portfolio, its
   own costs, its own turnover.
3. Only then is **incremental value over the frozen model** tested: does adding
   it to the existing composite improve anything the existing composite does,
   measured as its own registered question.
4. Only then, if it survives all of that, does a holdout rung get spent.

## 10. Caveats recorded in advance

- **The benchmark is Nifty 50 (`^NSEI`) while the universe is Nifty 100.** This
  is the repo's existing benchmark and is kept for consistency; switching it is
  a degree of freedom and is forbidden post-results by §9. The mid-cap tail of
  the universe will carry slightly larger residuals for this reason, which
  biases the signal toward smaller constituents — which is precisely why size
  is a declared diagnostic in §8.
- ~89 scoreable names per date means ~9 per decile. The extreme buckets are the
  noisiest part of the run.
- Overlapping horizons at 3/6/12 months reuse returns. HAC corrects the
  standard error; it does not restore independence. At 12 months the effective
  degrees of freedom fall to about 5, and that column is close to powerless.
- The panel was corrected on 2026-09-16 to drop 581 forward-filled holiday bars.
  This study runs on the corrected panel only. Realised volatility is precisely
  the quantity those bars distorted — an artificial 0% return suppresses a
  standard deviation — so running this on the old panel would have been the
  clearest possible case of measuring an artefact.
- The universe is survivorship-biased, as in §3.

## 11. What is registered, in one line

One family, one window, one estimator, one direction, four horizons, a
mechanism check that cannot rescue a failure, three diagnostics that are not
neutralisations, and a failure branch that freezes rather than re-specifies.
