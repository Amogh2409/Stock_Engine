# TradeBot Handbook

**Complete technical reference for the Indian equity screening engine.** Every
formula, every threshold, every command, every result, and every known limit.

Written 2026-09-14 against commit `23f0d0c`. Line references are to that commit.

> **Read §1 before anything else.** The engine is well-built and well-tested. On
> current evidence it is not a stock picker, and the handbook says so early
> because a document that buries that is misleading however accurate the rest is.

---

## Table of contents

1. [The honest state of the evidence](#1-the-honest-state-of-the-evidence)
2. [What this project is](#2-what-this-project-is)
3. [Architecture: two engines, held identical](#3-architecture-two-engines-held-identical)
4. [Setup](#4-setup)
5. [Every command](#5-every-command)
6. [Input and output formats](#6-input-and-output-formats)
7. [The scoring model](#7-the-scoring-model)
8. [Every indicator formula](#8-every-indicator-formula)
9. [Position sizing](#9-position-sizing)
10. [The backtest](#10-the-backtest)
11. [The statistical machinery](#11-the-statistical-machinery)
12. [Measurement variants](#12-measurement-variants)
13. [The after-tax model](#13-the-after-tax-model)
14. [Determinism](#14-determinism)
15. [The working rules](#15-the-working-rules)
16. [The knowledge documents](#16-the-knowledge-documents)
17. [File map](#17-file-map)
18. [What is blocked](#18-what-is-blocked)
19. [Known documentation drift](#19-known-documentation-drift)
20. [Quick reference](#20-quick-reference)

---

## 1. The honest state of the evidence

Everything measured here comes from **one window** — 2015-10-30 to 2022-11-30,
86 traded months — searched **125+ ways**. Every pre-holdout figure is
**exploratory** under the policy in `knowledge/rulebook.md`: nothing measured
there is called significant, whatever its p-value.

### What has been measured

Only the **technical half**, which carries **40%** of the composite score. The
fundamental half — 60%, and the thing that actually gates admission — has never
been backtested once.

### The composite result

| horizon | rank IC | HAC t | df | n | p×20 | detection floor | clears? |
|---|---|---|---|---|---|---|---|
| 1 month | **−0.0033** | −0.16 | 85 | 86 | 1.000 | 0.058 | no |
| 3 months | +0.0183 | +0.95 | 27 | 84 | 1.000 | 0.056 | no |
| 6 months | +0.0504 | +2.15 | 12 | 81 | 1.000 | 0.071 | no |
| 12 months | +0.0434 | +1.81 | 5 | 75 | 1.000 | 0.082 | no |

**Zero of twenty cells clear their own detection floor**, at any horizon, in any
block. Nothing clears multiple-testing correction.

### Why the null is uninformative

The smallest IC this sample can reliably detect at 80% power is **0.058**. A
plausible cross-sectional effect is roughly **0.02–0.05**. The floor sits *above
the entire range of effects anyone would expect to find*, so the null is an
**absence of evidence, not evidence of absence**.

### The portfolio result, which does not depend on statistical power

Top 20 monthly against equal-weighting the same 100 names over the same months:

| | strategy | equal weight | gap | 95% CI | p |
|---|---|---|---|---|---|
| shipped points model | 22.52% | 23.29% | **−0.78pp** | [−7.68, +5.00] | 0.794 |

Turnover **689%** a year. **It has never beaten equal-weighting on any window
measured.** The gap now sits well inside its own interval, so the honest
statement is direction, not magnitude.

### The one pre-registered hypothesis

`knowledge/preregistration.md` names exactly one cell in advance — momentum
block, 1-month, rung C — and predicts a **negative** IC. Observed pre-holdout:
**−0.0407, HAC t −3.05, p×20 0.061**. **Status: NOT RUN.** The reserved window
gives it only **56% power**, and the effect sits below that test's own floor.

### Tier 2: can it survive tax?

Holding the 20 lowest-momentum names monthly, at ₹10 lakh with the s.112A
exemption applied to both sides, over the same 86 months:

| | gross | after 20% STCG | drag |
|---|---|---|---|
| reversal, 964% turnover | 28.67% | 22.07% | 6.60pp |
| equal weight | 23.29% | 20.17% | 3.12pp |

**Incremental tax cost of monthly trading: 3.48pp a year.** The gross edge is
+5.38pp, so **+1.90pp survives after tax** — and that gross edge straddles zero
(CI [−0.01, +11.94], p 0.051). Tax does not make it untradeable; the edge is
simply not established.

---

## 2. What this project is

A **deterministic, explainable, rule-based screening engine** for Indian
equities. It reads a Screener.in CSV export of company fundamentals, optionally
reads daily price history, scores every company out of 100, ranks them, and
produces a watchlist with position sizes and stop levels.

It does **not** place orders. Nothing here is investment advice.

Three surfaces, all producing identical numbers:

| surface | path | what it is |
|---|---|---|
| Browser | `src/` | React app — upload CSV, screen, inspect, export |
| Python | `python/engine.py` | CLI pipeline with data persistence |
| Notebook | `Indian_Equity_Quantitative_Engine.ipynb` | One-cell Colab pipeline, generated from the Python |

---

## 3. Architecture: two engines, held identical

`python/engine.py` (5,521 lines) is the **source of truth**.
`src/utils/screenerEngine.ts` (3,821 lines) mirrors it bit-for-bit.

Two separate mechanisms keep them together, and they are often confused:

**(a) Codegen sync — `npm run check:python`.** `scripts/build_python_source.mjs`
embeds `engine.py` verbatim into `src/utils/pythonEngineSource.ts` and generates
`src/data/nifty100Snapshot.ts`. `--check` verifies they are in sync and exits 1
if not. **After any change to `engine.py` you must run `npm run build:python`
and `npm run generate:notebook`, or this fails.**

**(b) Behavioural parity — `src/tests/parity.test.ts`.** 39 tests driving
`src/tests/fixtures/parity_driver.py` through `src/tests/helpers/pythonBridge.ts`,
comparing 26 fields per evaluation across 8 screens. This is the test that
catches a scoring divergence.

### The measurement/engine boundary

**Measurement variants belong in `python/backtest.py`, never in `engine.py`.**
The engine must keep scoring what it ships. Changing a shipped comparison to see
whether it backtests better is *adoption*, not *measurement* — and adoption on
data already used is the feedback failure the whole project is built to avoid.

`--rsi-flip` established the pattern; `--continuous`, `--neutral`,
`--no-skip-month`, `--buffer`, `--invert` all follow it. `python/backtest.py`
is **not** mirrored into TypeScript.

The **one** scoring change ever adopted (`RELATIVE_STRENGTH_SKIP_SESSIONS`) rested
on a citation, with the measurement showing it cost nothing rather than serving
as the reason.

---

## 4. Setup

### Node

Requires Node `^22.22.2 || ^24.15.0 || >=26.0.0`, npm `>=10`. Node 25 installs
with warnings but is unsupported by jsdom/vitest.

```bash
npm ci
npm run dev            # http://localhost:3000
```

### Python

The engine imports pandas and numpy, which system Python usually lacks.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt      # offline runs and tests
.venv/bin/pip install -r requirements-network.txt   # adds live prices and NSE refresh
```

`scripts/venv-python.sh` runs any script with the project interpreter. Set
`PARITY_PYTHON` to override it — this also redirects the vitest parity suites.

### Environment switches

| variable | effect |
|---|---|
| `PARITY_PYTHON` | interpreter for `venv-python.sh` and the parity/notebook suites |
| `TRADEBOT_DATA_DIR` | relocates the engine's data root |
| `RUN_NETWORK_TESTS=1` | adds `NetworkIntegrationTests` to `test_python.py` |
| `KEEP_WORKDIR=1` | retains `run_checks.sh` temp directories |
| `PORT`, `NODE_ENV` | server binding and mode |

### Data root precedence

`resolve_data_root` (`engine.py:3778-3805`), in order:

1. `--data-dir DIR`
2. `TRADEBOT_DATA_DIR`
3. Google Drive, when `from google.colab import drive` succeeds →
   `/content/drive/MyDrive/IndianStockEngine`
4. `<project root>/data-store`

Subdirectories: `config`, `fundamentals`, `market_data`, `cache`, `reports`,
`watchlists`, `logs`.

---

## 5. Every command

### npm scripts

| script | command | purpose |
|---|---|---|
| `dev` | `tsx server.ts` | dev server, binds 127.0.0.1, port `PORT` else 3000 |
| `build` | build:python → vite build → esbuild | produces `dist/` and `dist-server/` |
| `preview` | `vite preview` | serve the built app |
| `clean` | `rm -rf dist dist-server` | |
| `lint` | `tsc --noEmit` | expect exit 0 |
| `test` | `vitest run` | **234 tests**, 6 suites |
| `start` | `node dist-server/server.cjs` | production server, binds 0.0.0.0 |
| `build:python` | `node scripts/build_python_source.mjs` | regenerate the TS mirror artefacts |
| `check:python` | same `--check` | verify sync, exit 1 if stale |
| `check:docs` | `scripts/check_doc_figures.py` | figures match the artefact + scoring hash |
| `generate:notebook` | `tsx generate_ipynb.ts` | rebuild the .ipynb |
| `verify` | `bash run_checks.sh` | the full release gate |
| `screen` | `engine.py` | live run: NSE refresh + price download |
| `screen:offline` | `engine.py --offline` | cached data only |
| `screen:selftest` | `engine.py --self-test` | **90 tests** |
| `test:python` | `test_python.py` | **161 tests**, loads the engine from the notebook |

### The five checks before any commit

```bash
npm run lint            # tsc --noEmit                → expect exit 0
npm run check:python    # generated files in sync     → expect exit 0
npm run check:docs      # figures match the artefact  → expect exit 0
.venv/bin/python test_python.py          # 161 tests  → expect exit 0
npx vitest run                           # 234 tests  → expect exit 0
.venv/bin/python python/backtest.py --self-test  # 35 → expect exit 0
```

**Read each exit code from the command that produced it.** `cmd | tail` returns
*tail's* exit code — this has already caused one false "passed" report here.

### `python/engine.py`

```
usage: engine.py [-h] [--offline] [--self-test] [--data-dir DIR]
                 [--config FILE] [--archive]
```

| flag | default | effect |
|---|---|---|
| `--offline` | off | cached Nifty 100 snapshot and price history only, no network |
| `--self-test` | off | run `EngineTests` (90) and exit |
| `--data-dir DIR` | — | read and write all run data under DIR |
| `--config FILE` | `<data root>/config/config.json` | settings file |
| `--archive` | off | archive the newest fundamentals export and exit |

Exit codes: `0` ok · `1` self-verification failed or unexpected error ·
`2` invalid config or nothing to archive.

The engine **runs its own 90-test suite before screening** and aborts if any
fail (`engine.py:5463-5471`). It always seeds `np.random.seed(42)`.

### `python/backtest.py`

| flag | type | default | purpose |
|---|---|---|---|
| `--prices CSV` | str | required¹ | price-history CSV |
| `--top-n` | int | `20` | portfolio size |
| `--cost-bps` | float | `15.0` | cost per side, bps (0.30% round trip) |
| `--out-dir DIR` | str | — | write `report.md` and `results.json` |
| `--variants-tried` | int | `1` | reported verbatim in the report |
| `--variants-note` | str | "No parameter was fitted to the data." | |
| `--self-test` | flag | off | run 35 offline checks and exit |
| `--no-respect-holdout` | flag | off | **spends the reserved window** |
| `--rsi-flip` | flag | off | score RSI *below* the floor instead of above |
| `--continuous` | flag | off | magnitudes (winsorised z) instead of thresholds |
| `--neutral` | flag | off | residualise on sector + log turnover |
| `--no-skip-month` | flag | off | restore the pre-2026-09-14 relStrength window |
| `--buffer N` | int | `1` | sell only when a holding leaves the top N×top_n |
| `--portfolio-block NAME` | str | — | rank the portfolio on one block |
| `--invert` | flag | off | hold the **worst**-ranked names |
| `--tax-stcg RATE` | float | `0.20` | short-term rate (s.111A) |
| `--capital RUPEES` | float | — | portfolio size, enables the s.112A exemption |

¹ required unless `--self-test`.

**Reproducing the Tier 2 headline:**

```bash
python/backtest.py --prices <file> --out-dir data-store/reports/tier2_reversal \
  --continuous --neutral --portfolio-block momentum --invert --capital 1000000
```

### Other scripts

| script | purpose |
|---|---|
| `scripts/forward_log.py --prices <csv>` | write this month's selections; refuses to overwrite |
| `scripts/check_doc_figures.py` | three passes: CURRENT, RETIRED, SCORING hash |
| `scripts/venv-python.sh <script>` | run with the project interpreter |
| `scripts/build_python_source.mjs [--check]` | codegen / verify |
| `python/ab_compare.py --engine A=dir --engine B=dir --prices csv` | A/B two engine revisions |

---

## 6. Input and output formats

### Price history CSV

`PRICE_HISTORY_COLUMNS = ["Date", "Ticker", "Open", "High", "Low", "Close", "Volume"]`
(`engine.py:1709`).

`parse_price_history_csv` (`engine.py:2505`) strips BOM, normalises line endings,
matches columns case-insensitively (`date`, `ticker|symbol`, `close`, `volume`,
`open`, `high`, `low`), **requires Date + Ticker + Close**, and skips rows failing
the date check, with a blank ticker, or an unparseable close. Returns
`{ticker: {dates, closes, volumes, opens, highs, lows}}` sorted by date.

The benchmark `^NSEI` (Nifty 50) must be present — `market_calendar` raises
without it. History starts `2015-01-01` (`HISTORY_START`).

### Screener fundamentals export

Columns consumed include: Name, NSE code, Current Price, Market Capitalization,
Sales growth 3Years, Profit growth 3Years, ROCE, Return on equity, Debt to
equity, Interest Coverage, Cash flow from operations, Promoter holding, Pledged
percentage, Price to Earning, Price to book value, Dividend yield, Industry.

Banks/NBFCs additionally need `Return on assets`, `Gross NPA %`, `Net NPA %`,
`Capital adequacy ratio`.

> **`data-store/fundamentals/sample_screener_export.csv` holds 31 rows of
> invented figures**, of which 11 overlap the 101 priced tickers. It is a
> fixture. There is no real export in this repository.

### Sector map

`data/nifty100_source.csv` — the raw NSE constituents file:
`Company Name,Industry,Symbol,Series,ISIN Code`. Covers **100 of 100**
non-benchmark tickers, 17 industries. Snapshot as of **2026-09-10**.

### Backtest outputs

`--out-dir` writes two files:

- **`report.md`** — human-readable, with limitations stated at the top.
- **`results.json`** — `config`, `performance` (full / in_sample / out_of_sample,
  each with strategy / equal_weight / index / span / cagr_vs_equal_weight),
  `deciles`, `block_deciles`, `periods`, `yearly`, `turnover`, `buffer_multiple`,
  `portfolio_block`, `inverted`, `after_tax`, `quality`.

---

## 7. The scoring model

### Composite

```python
composite = fundamental * (1 - W/100) + technical * (W/100)
```

`technical_weight_pct` default **40**. `minimum_total_score = 50` gates on the
**fundamental** total; ranking sorts on the **composite** (`engine.py:3286-3290`).

### Fundamental score — 100 points (`score_general`, `engine.py:2914`)

**Never measured.** These are the rules, not validated findings.

| block | max | rule |
|---|---|---|
| financialQuality | 30 | `15·clip(ROCE/40, 0, 1)` + `15·clip(ROE/40, 0, 1)` |
| growth | 25 | `12.5·clip(g/30, 0, 1)` each for sales and profit growth |
| balanceSheetSafety | 20 | `clip(10 − 5·D/E, 0, 10)` + `10·clip(ICR/5, 0, 1)` |
| valuation | 15 | `c·clip(1.5 − x/ỹ, 0, 1)`, c = 10 for P/E, 5 for P/B |
| governance | 10 | promoter holding `5·clip(PH/75,0,1)` (2.5 if PH = 0) + pledge `clip(5 − PP, 0, 5)` |

`total = clamp(sum, 0, 100)`.

### Financial-sector model (`score_financial`, `engine.py:2973`)

```
15·clip(ROA/1.5, 0, 1) + 15·clip(ROE/20, 0, 1)
  + 10·clip((CAR − 9)/7, 0, 1) + 10·clip((2 − netNPA)/2, 0, 1)
```

`grossNpa`, `casa`, `financingMargin` are **reported, never scored**. Missing any
of `returnOnAssets`, `grossNpa`, `netNpa`, `capitalAdequacy` → verdict
`Not scored`.

### Technical score — 100 points (`calculate_technical_score`, `engine.py:2264`)

`TECHNICAL_BLOCK_MAX = {"trend": 40, "momentum": 30, "relStrength": 20, "volume": 10}`

**Gate:** returns `None` unless `history_rows >= SESSIONS_FOR_TECHNICAL_SCORE`
(200) and `data_status != "UNAVAILABLE"`.

| block | rule | points |
|---|---|---|
| trend | `isAboveSma200` | 12.0 |
| trend | `isAboveSma50` | 8.0 |
| trend | `isSma50Above200` | 8.0 |
| trend | `adx14 > 25.0` | 4.0 |
| trend | `distFrom52WHighPct > −15` | 8.0 |
| momentum | `macdHistogram/price·100 > 0.05` | 15.0 |
| momentum | `rsi14 > 50.0` | 15.0 |
| relStrength | `relativeStrength3M > 0` | 5.0 |
| relStrength | `relativeStrength6M > 0` | 10.0 |
| relStrength | `relativeStrength12M > 0` | 5.0 |
| volume | `volumeRatio20D > 1.0` | 5.0 |
| volume | `obvPressure20D > 0` | 5.0 |

**Every award is binary.** There is no partial credit. That is the defect
`--continuous` exists to measure: RSI 51 and RSI 89 are the same input.

Flags, never points: `atrPct > 5.0` → "High Volatility"; `rsi14 > 80.0` →
"Overbought"; `drawdownFromPeakPct < −25.0` → "Deep Drawdown".

Final: `blocks[k] = round1(clamp(blocks[k], 0, MAX[k]))`,
`score = clamp(Σ blocks, 0, 100)`.

> **The stated weights are not the realised weights.** Measured over 87 dates and
> 7,621 observations, the points model realises **36.1 / 32.0 / 22.7 / 9.2**, not
> 40 / 30 / 20 / 10 — because what a block contributes to a *ranking* is its
> cross-sectional spread, and trend's five features are near-collinear.

### The −15 literal

The 52-week test uses a bare `-15` (`engine.py:2306`) — the only scored threshold
with no named constant. When `high52Week` is available but `dist <= -15`, **no
breakdown line is emitted at all**.

### Hard red flags (`engine.py:2757`), in fixed order

1. `pb < 0 or de < 0` → "Negative net worth"
2. `pp > maxPromoterPledgePct` → "High Promoter Pledge"
3. non-financial + `requirePositiveOcf`: missing → "OCF missing"; `<= 0` → "Negative OCF"
4. `coverage < minimum_fundamental_coverage` → "Insufficient Data (x%)"
5. `sales <= 0` → "Non-positive Sales"
6. `not 0 <= ph <= 100` / `not 0 <= pp <= 100`
7. `mcap <= 0`
8. `pp > 0 and ph == 0` → "Pledge without promoter holding"
9. `duplicateConflict`

Coverage = `available/len(fields)·100` over 11 fields (non-financial) or 13
(financial).

---

## 8. Every indicator formula

### Window constants

```python
SESSIONS_52_WEEK = 252        SESSIONS_6_MONTH = 126
SESSIONS_1_MONTH = 21         SESSIONS_3_MONTH = 63
SESSIONS_12_MONTH = 252       RELATIVE_STRENGTH_SKIP_SESSIONS = 21
ATR_ADX_PERIOD = 14           ATR_ADX_WINDOW = 14*5 + 1 = 71
RSI_PERIOD = 14               BOLLINGER_PERIOD = 20
BOLLINGER_DEVIATIONS = 2.0    OBV_LOOKBACK = 20
```

### Smoothing primitives

**`_sequential_mean(values)`** — left-to-right float sum ÷ n.
`mean(v) = (((0 + v₀) + v₁) + … ) / n`

Built-in `sum()` is deliberately avoided: since Python 3.12 it compensates float
rounding and can differ from JavaScript in the last bit — enough to flip a
price-versus-SMA comparison on a flat series.

**`_wilder_average(values, n)`**
- seed `A_{n−1} = (1/n) Σ_{k<n} v_k`
- `A_i = (A_{i−1}·(n−1) + v_i) / n` for `i ≥ n`
- returns the final scalar

**`_ema_series(values, p)`**, `α = 2/(p+1)`
- seed `E_{p−1} = mean(v[0:p])`
- `E_i = α·v_i + (1−α)·E_{i−1}`
- output length `len(values) − p + 1`, `[]` if too short

### The indicators

| indicator | formula | min sessions | range |
|---|---|---|---|
| SMA50 / SMA200 | `_sequential_mean(prices[-50:])` / `[-200:]` | 50 / 200 | price units |
| RSI(14) | `100 − 100/(1 + avgGain/avgLoss)`, Wilder-smoothed | 15 | 0–100 |
| MACD(12,26,9) | `line = ema12[i+14] − ema26[i]`; signal = EMA9(line); hist = line − signal | 34 | price units |
| ATR(14) | `_wilder_average(trueRanges, 14)`, `TR = max(h−l, \|h−pc\|, \|l−pc\|)` | 71 window | price units |
| ATR% | `atr/current·100` | | percent |
| ADX(14) | `+DM`/`−DM` → Wilder-smooth → `±DI = 100·S±/STR` → `DX = 100·\|+DI − −DI\|/(+DI + −DI)` → `ADX = wilder(DX,14)` | 71 window | 0–100 |
| Bollinger %B | population sd over 20; `spread = 2·sd`; `((last − (mean − spread))/(2·spread))·100` | 20 | ~0–100 |
| OBV pressure | `(signed/gross)·100`, signed adds volume on up closes | 20 | −100..+100 |
| Volume ratio 20D | latest volume ÷ mean of last 20 reporting sessions | 20 | ratio |
| 52-week high dist | `((current − max(prices[-252:]))/max)·100` | 252 | ≤ 0, percent |
| Drawdown from peak | `((last − max(prices))/max)·100` | 20 | ≤ 0, percent |
| Volatility 30D | `sqrt(Σ(r−r̄)²/(n−1))·sqrt(252)·100` | 20 returns | annualised % |
| ROC(n) | `(prices[-1]/prices[-(n+1)] − 1)·100` | n+1 | percent |

**ATR/ADX return `None` if any high or low in the 71-session window is NaN.**

### Relative strength — the skip-month construction

```python
skip = RELATIVE_STRENGTH_SKIP_SESSIONS          # 21
skipped = pairs[:len(pairs) - skip]
relativeStrength3M  = _relative_strength(skipped, 63  - 21)   # 42
relativeStrength6M  = _relative_strength(skipped, 126 - 21)   # 105
relativeStrength12M = _relative_strength(skipped, 252 - 21)   # 231

# _relative_strength(pairs, n):
#   ((S_t - S_{t-n})/S_{t-n} - (B_t - B_{t-n})/B_{t-n}) * 100
```

This is the **2–12 construction**: the window *start* stays at t−h and only the
*end* moves back one month. Shifting the whole window would give t−13 to t−1, a
different quantity.

**Sourced for the 12-month leg only** — CFA Institute Research Foundation
Monograph `rf-v2016-n4-1#71`: *"the prior 12 months of returns, excluding the
most recent month (2–12)."* The corpus has no 3- or 6-month equivalent, so those
two legs are an **extension by consistency, with no citation**.

### `data_status`

`COMPLETE` when all of `("sma50","sma200","smaCross","relativeStrength6M","high52Week")`
are available; `PARTIAL` if at least one; `UNAVAILABLE` if none.

`empty_technicals()` returns **34 keys, 29 raw values**. Only **12 feed the
score**; 17 are computed and never scored: atr14, atrPct, bollingerPercentB,
currentPrice, diMinus14, diPlus14, drawdownFromPeakPct, high52Week, macdLine,
macdSignal, roc1M, roc3M, roc6M, roc12M, sma50, sma200, volatility30D.

---

## 9. Position sizing

Equal-risk weighting from TSaM p.1103 / Table 24.1 p.1104.

```python
# Step 1 — equal risk: weight inversely proportional to volatility
raw[t]   = smallest / values[t]        # values = atrPct, else volatility30D
scale[t] = raw[t] / Σ raw              # summed in sorted(ticker) order

# Step 2 — volatility targeting
series[d]     = Σ_t scale[t] · r_t(d)
portfolio_vol = sd(series) · sqrt(252) · 100
                # last 252 sessions common to all holdings, variance ÷ (n−1),
                # requires ≥ 60 sessions
deployment    = min(1.0, target_volatility_pct / portfolio_vol)   # target 12.0
weight        = scale[t] · deployment · 100

# Step 3 — per-position risk ceiling (TSaM p.1032)
stop_pct = STOP_ATR_MULTIPLE (2.0) · atrPct
weight   = min(weight, MAX_RISK_PER_POSITION_PCT (5.0) · 100 / stop_pct)

# Step 4a — position cap
weights[t] = min(weight, max_position_weight_pct (10.0))

# Step 4b — sector cap, iterated in sorted order
if group_total > max_sector_weight_pct (25.0):
    factor = 25.0 / group_total; scale members

stopDistancePct = round1(2.0 · atrPct)
stopPrice       = round1(price · (1 − stop_pct/100))
```

**Capped weight is not redistributed** — it stays in cash. Redistribution needs
iteration to converge, and an iteration count is one more thing two engines must
agree on exactly.

Constants: `DEFAULT_TARGET_VOLATILITY_PCT = 12.0`, `MAX_RISK_PER_POSITION_PCT = 5.0`,
`STOP_ATR_MULTIPLE = 2.0`, `SESSIONS_FOR_PORTFOLIO_VOLATILITY = 60`,
`DEFAULT_MAX_POSITION_WEIGHT_PCT = 10.0`, `DEFAULT_MAX_SECTOR_WEIGHT_PCT = 25.0`.

The **5% risk ceiling is Sourced and never binds**; the two Convention caps
(10% / 25%) are what actually constrain concentration.

---

## 10. The backtest

### Execution model

- Signal on the **last session of each month**.
- Enter at the **open of the next session**; exit at the **open of the session
  after the next signal date**. The trade is never priced at a level the signal
  already knew about.
- Equal-weighted top N (default 20).
- Cost: `2 · turnover · (cost_bps/10000)`, default 15 bps per side.
- Names missing a price at either end are **dropped and counted**, never carried
  at zero.

### The holdout

`HOLDOUT_START = "2023-01-01"`. `month_end_sessions` truncates there **by
default** and **raises `SystemExit`** rather than returning an empty list — a
finished-looking backtest of nothing is worse than a crash.

`--no-respect-holdout` spends the window. See §16.

### Benchmarks

- **Equal weight** — every covered ticker, same schedule, same execution.
- **^NSEI** — buy and hold the index closes.

Both are cut by `align_to()` to the months the strategy actually traded. This
matters: the strategy cannot trade until enough companies clear the session
minimum, so unaligned it compares an 86-month CAGR against a 95-month one. That
defect has occurred **twice** and been fixed twice.

### Rebalance splits

`full` / `in_sample` / `out_of_sample`, split at `OUT_OF_SAMPLE_START = "2022-01-01"`.

---

## 11. The statistical machinery

### Rank IC — `spearman()` (`backtest.py:1255`)

Pearson correlation on **mid-ranks** (average ranks for ties). Returns `None` for
n < 3.

**Under the permutation null, `Var(ρ) = 1/(N−1)` exactly, for any tie structure.**
This was verified by simulation: even with only two distinct score values across
89 names, `Var·(N−1) = 1.0005`. Ties cost *headroom* (ρ_max ≈ 0.9989), not
precision.

### Newey-West HAC standard error (`backtest.py:1322`)

```
S  = γ₀ + 2·Σ_{k=1..L} (1 − k/(L+1))·γ_k
γ_k = (1/n)·Σ_{t=k..n−1} d_t·d_{t−k}
se  = sqrt(S/n),     L = h − 1
```

Bartlett weights guarantee non-negative variance where Hansen-Hodrick does not.
Returns NaN if `S ≤ 0`.

**Why it exists:** overlapping windows are not a defect — applying an i.i.d.
standard error to them is. Newey-West keeps every window with a valid SE.

### Degrees of freedom — the effective count

```python
horizon     = hac_lag + 1
effective_n = n if horizon <= 1 else max(2, n // horizon)
hac_df      = max(1, effective_n - 1)
```

`n // h` reproduces the non-overlapping series length exactly at every horizon
(84//3 = 28, 81//6 = 13, 75//12 = 6). Referring a HAC t to `n−1` over-rejects:
at 6 months it gave p 0.0030 where the answer is 0.0099.

**This is a conservative proxy, not the textbook fix.** Fixed-b asymptotics
(Kiefer & Vogelsang 2005) give a nonstandard limiting distribution with fatter
tails than Student's t at any df, so the honest p sits *above* this one.

### Detection floor

```
detectable = (t_crit(df, α=0.05) + Z_FOR_80_PERCENT_POWER) · SE
Z_FOR_80_PERCENT_POWER = 0.8416
SE = hac_se when hac_lag > 0, else sd/sqrt(n)
```

The multiplier is `t_critical(df) + z(0.80)`, **not** the flat 2.8 that holds only
for large samples — at df = 9 the critical t is 2.262, so 2.8 understates by
about a tenth at precisely the horizon where a reader is likeliest to read
no-power as no-effect.

### Stationary bootstrap (`backtest.py:1375`)

Politis-Romano: geometric block lengths with `p = 1/mean_block`, circular
wrapping, `mean_block = max(1, hac_lag+1)`, `BOOTSTRAP_DRAWS = 2000`,
`BOOTSTRAP_SEED = 20260913`.

Percentile index: `max(0, min(count−1, ceil(q·count) − 1))` — nearest rank, not
`int(q·n)`.

> **The bootstrap is NOT a conservative check on HAC**, and the docstring that
> said so has been withdrawn. It is *smaller* than HAC in 10 of 15 overlapping
> cells. Scored against a series whose true SE is known, **every** estimator
> understates: at h=6, i.i.d. −61%, HAC −22%, bootstrap −25%. No block length
> fixes the bootstrap; no Bartlett bandwidth fixes HAC. **Read every t here as
> inflated by roughly a quarter at the longer horizons.**

### Phase-averaged non-overlapping statistics (`backtest.py:1662`)

At horizon h there are h valid non-overlapping series. The study used to keep
phase 0 only, which discarded (h−1)/h of the observations and made the column
depend on which month the price file began in — at 12 months, 6 windows of 75.

All phases are now averaged. **The point estimate is averaged; the standard error
is not reduced by √h**, because the phases are not independent of each other
(phase 0's first window spans months 0..h and phase 1's spans 1..h+1). The
reported SE is the mean of the per-phase SEs, which is conservative.

### Multiple testing

`bonferroni(p, tests) = min(1.0, p · max(1, tests))`, with
`family = 4 horizons × (1 composite + 4 blocks) = 20` per run.

**Policy** (see §15): everything pre-holdout is exploratory; correction applies
only within the single pre-registered final test; the search count is stated
wherever an exploratory cell appears, and is a **lower bound**.

### CAGR difference CI (`backtest.py:1450`)

Months resampled **jointly** as (strategy, benchmark) pairs aligned on
`signal_date`, so the contemporaneous correlation survives. Each resampled path
is **compounded**, not averaged — CAGR is a function of the path, not a mean.

```
p = min(1, 2·min(P(d ≤ 0), P(d ≥ 0)))
```

Ties counted on **both** sides: a strict `> 0` sorted exactly-zero into the
negative bucket and reported p 0.000 for two identical series.

### Performance (`backtest.py:1113`)

`years = n/12` · `CAGR = Π(1+r)^{1/years} − 1` · `annual_vol = sd·sqrt(12)` ·
`sharpe_rf0 = (mean·12)/annual_vol` · `calmar = CAGR/|maxDD|`.

### The IC variance decomposition

```
Var(IC across months) = Var(true monthly IC) + E[1/(N_t − 1)]
```

The sampling term is the **mean over months** of `1/(N_t−1)` using the real
per-month universe sizes — **not** `1/(median N − 1)`, which understates it
because `1/(x−1)` is convex.

Measured at 1 month: observed Var 0.03683381 = sampling 0.01159237 + residual
0.02524144. **Noise is only 31.5%**; the rest is genuine time-variation
(residual sd 0.159, bootstrap CI [0.124, 0.187], P(residual ≤ 0) = 0.0000).

**The consequence that matters:** eliminating *all* cross-sectional noise would
cut se(mean IC) from 0.020695 to 0.017342 — **16%**. The binding constraint is
86 months, not 89 names.

---

## 12. Measurement variants

### `--continuous` — magnitudes instead of thresholds

Each of the 12 features is winsorised and z-scored across the cross-section, then
combined with the engine's own weights.

```python
WINSOR_TAIL = 0.025
cut = min(max(1, int(n·0.025)), max(0, (n−3)//2))
clip to [ordered[cut], ordered[n−1−cut]]
z = (v − mean)/sd,   var = Σ(v−mean)²/(n−1)
```

The `max(1, …)` matters: plain `int(n·0.025)` is **zero for every n below 40**,
silently disabling clipping. The `(n−3)//2` bound stops a tiny group being
flattened.

**Two things are matched to the points model on purpose**, so a difference
measures thresholding and nothing else:

1. An absent feature takes the **minimum** z, not the mean — the points model
   awards nothing for absent and nothing for failed alike.
2. Each block is rescaled so its cross-sectional SD equals the points model's
   subtotal SD on that date. Unmatched, the two modes realised
   38.2/32.1/21.3/8.4 against 36.1/32.0/22.7/9.2 — a difference of up to 9.4%.

### `--neutral` — sector and size neutralisation

Frisch-Waugh: demean within sector bucket, then regress the demeaned score on
demeaned log turnover.

```
β = Σ x̃ỹ / Σ x̃²      residual = ỹ − β·x̃
```

- **Sector** from `data/nifty100_source.csv`, 100/100 coverage, snapshot
  **2026-09-10**. Stale, and a milder look-ahead than market cap: an industry
  label is not a function of returns.
- **Size** is `log(median(close·volume))` over 252 sessions — a **liquidity
  proxy**, fully point-in-time, **not market cap**. There is no historical market
  cap in this repository.
- Buckets below `MIN_SECTOR_BUCKET = 3` pool into "Other", applied **per date** to
  eligible names. A bucket that cannot support a mean is demeaned against the
  whole cross-section, because demeaning a bucket of one sets that name to
  exactly zero — which reads as "average" and means "alone".

Measured: minimum bucket size 3, "Other" holds 9–11, zero names lack turnover.

### `--buffer N` — rank buffering

A holding survives until it leaves the top N×top_n. Survivors keep rank order and
fill first; remaining slots go to the best-ranked names not held.

**It changes which names are held, not the ranking** — the score's IC is
unchanged by it *by construction*. Reporting "IC at each buffer level" would
print one number three times and call it a trade-off.

### `--rsi-flip`, `--no-skip-month`, `--portfolio-block`, `--invert`

- `--rsi-flip` scores `rsi14 < 50` instead of `> 50`. The momentum block is
  recomputed and re-clamped, never adjusted by arithmetic on the total — MACD's
  15 and RSI's 15 sum exactly to the cap of 30.
- `--no-skip-month` restores the pre-2026-09-14 relStrength window.
- `--portfolio-block NAME` ranks the portfolio on one block.
- `--invert` holds the worst-ranked names — this is how the pre-registered
  reversal is traded.

---

## 13. The after-tax model

### The rates

Stated from knowledge with statutory references; **this repository holds no tax
data**.

| | |
|---|---|
| s.111A short-term, listed equity | **20%** since 23 July 2024 |
| s.112A long-term, listed equity | **12.5%** above a ₹1.25 lakh annual exemption |
| Holding period to qualify as long-term | **12 months** |

### The simulation (`after_tax_performance`, `backtest.py:832`)

Lot-tracking, not a turnover approximation — the question turns entirely on *when*
each position is sold relative to the 12-month line, and a turnover estimate
cannot see the line.

- Positions tracked as `[units, cost basis, acquisition date]`.
- Sells realise gains, classified by `_months_held(since, entry) >= 12`.
- `_months_held` implements the s.2(42A) test:
  `(y₂−y₁)·12 + (m₂−m₁) − (1 if d₂ < d₁ else 0)`.
- The **exemption** is consumed first-come-first-served within each Indian
  financial year (April–March); losses cannot consume it.
  `exemption_unit = 125000 / capital`.
- `years = (last exit − first entry).days / 365.25` — **not** `len(periods)/12`,
  which is only a year count on a monthly schedule.

**Equal weight is built on the strategy's own periods** — same months, same
dates, same lot-history window. Building it from the full calendar compares a
7.92-year CAGR against a 7.17-year one, which moved the Tier 2 headline by a
factor of 2.3.

### Two simplifications, both stated

1. Tax charged at realisation, not at financial-year end. Removes the within-year
   deferral benefit, so it **overstates** the drag — conservative.
2. Adding to a position keeps the original acquisition date rather than opening a
   FIFO lot. Makes long-term treatment slightly **more** likely than the statute
   allows — flatters the strategy. Bounded by forcing every gain short-term:
   equal weight 16.81% → 16.02%, and the buffered gap moves +4.17 → +4.47pp.
   Worth under a point, and it runs against the strategy.

### Why `--capital` matters

Without it the exemption is off, which taxes long-term gains from the first
rupee. The side that bears that is **equal weight** at 97.1% long-term; the
reversal at 100% short-term consumes none of it. **Omitting it inflates the
strategy's gap.** Supply a size for any published comparison.

| capital | equal weight after tax | gap | gap, buffered |
|---|---|---|---|
| not modelled | 19.25% | +2.82pp | +3.95pp |
| **₹10 lakh (headline)** | **20.17%** | **+1.90pp** | +3.02pp |
| ₹50 lakh | 19.48% | +2.59pp | +3.71pp |
| ₹1 crore | 19.36% | +2.70pp | +3.83pp |
| ₹10 crore | 19.26% | +2.81pp | +3.93pp |

---

## 14. Determinism

The two engines must produce identical doubles, so:

**`round1(x) = ⌊10x + ½⌋/10`** — half-up, bit-identical to JavaScript's
`Math.round(x*10)/10`. **Python's `round()` is banker's rounding and must never
be used for scores.** `round1(74.55) = 74.6` where `round(74.55, 1) = 74.5`.

**`clamp(v, lo, hi) = max(lo, min(hi, v))`.**

**`_sequential_mean`** — left-to-right summation, never `sum()`.

**Sorting is by code point**, never `localeCompare`. Ties break on ticker
ascending: `sort(key=lambda pair: (-pair[1], pair[0]))`.

**Seeds:** `DETERMINISTIC_SEED = 42` in the engine; `BOOTSTRAP_SEED = 20260913`
in the backtest.

**The scoring hash.** `npm run check:docs` hashes the source of
`compute_technical_indicators` and `calculate_technical_score` **plus all 106
module-level ALL_CAPS constants**, and fails when it moves. When it fails,
re-read `knowledge/holdout.md` and `knowledge/preregistration.md` — both make
claims about what has and has not changed — then re-record `SCORING_HASH` **in
the same commit**.

> The first version of that guard hashed only the function bodies and **failed its
> own red test**: editing `RSI_MOMENTUM_FLOOR` did not trip it, because module
> constants sit outside the functions.

---

## 15. The working rules

These are not style preferences. Each was written after a specific failure.

- **Never tune a threshold to improve a result.** Measuring is fine; adopting a
  parameter because it improved a number, on any window, is fitting.
- **Never re-measure on a window already used to revise the engine**, and say so
  explicitly if you are about to.
- **Read exit codes from the command that produced them.** `cmd | tail` returns
  tail's exit code.
- **A grep count is not evidence until you have read the matching lines.** Zero
  counts are often shell mangling — in zsh an unquoted `--include=*.py` is
  glob-eaten and an unquoted `$VAR` holding two flags is passed as one argument.
  A fixed-width context pattern cannot match near a line boundary, so a zero from
  a windowed search is weaker than a zero from a plain one.
- **Before trusting a passing test, ask what it would print if the thing under
  test were broken.** If the answer is "the same", it carries no information.
  **Verify red in place**, not from a copy in `/tmp` — a copy has resolved its
  paths wrongly and "failed" for the wrong reason here. And back the file up
  first: `git checkout` on a file with uncommitted work destroys it.
- **Check the artefact against itself**, not only its figures against their
  source. A correct number under a wrong heading passes every data check.
- **Never `git add -A`.** Stage explicit paths; read `git diff --cached --stat`
  before every commit.
- **`engine.py` is the source of truth.** Regenerate after any change.
- **Update `knowledge/rulebook.md` in the same commit as any rule change**, with
  its status: Sourced / Adapted / Convention / Contradicted.
- **Do not verify your own freshly computed numbers** when another session can.
  That is the weakest check either one runs.

### The exploratory policy

Everything measured on the pre-holdout window is **exploratory**. No exploratory
cell is called significant, whatever its p. Multiplicity correction applies only
within the single pre-registered final test. The search count is stated wherever
an exploratory cell appears, and is a **lower bound** — design choices are degrees
of freedom too.

**The gap this policy does not close:** labelling stops us calling it significant;
it does not stop the exploration choosing *what gets tested on the holdout*. So
the holdout answers *"does the variant we selected hold up on unseen data"*, not
*"is there a real effect here"* — and must be stated as the former.

---

## 16. The knowledge documents

| file | what it holds |
|---|---|
| `knowledge/rulebook.md` (1,632 lines) | The audit trail for every technical scoring rule, each tagged Sourced / Adapted / Convention / Contradicted, plus the full measured record and the testing-methodology failures. **Explicitly excludes the fundamental half.** |
| `knowledge/holdout.md` | Reserves 2023-01-01 onward. States honestly that the window is **not pristine** — observed once on 2026-09-13 — while maintaining no parameter has changed *in response* to it. |
| `knowledge/preregistration.md` | One cell, named in advance, divisor 1. Momentum block, 1-month, rung C, predicted **negative**. Conjunctive decision rule, both branches stated. **NOT RUN.** |
| `knowledge/blocked.md` | Four structural limits, each with what is *currently false* because of it. |
| `knowledge/forward-log.md` | The monthly, git-committed, never-revised forward record. |
| `knowledge/exit-rules.md` | Three proposals, how each would be tested, none implemented. |
| `knowledge/TODO.md` | Presentation nits, deliberately deferred. |
| `knowledge/project-guide.html` | The rendered guide (→ `PROJECT_GUIDE.pdf`). |

### The corpus

`Books_TO_study/` holds **319 documents** with a knowledge graph — 1,519 nodes,
10,529 edges, 42,745 indexed chunks — and an offline query tool:

```bash
P=.venv/bin/python; A=Books_TO_study/_tools/ask.py
$P $A stats
$P $A search "average directional index" -k 8
$P $A verify "ADX above 25 indicates a trending market"
```

**It is gitignored.** Check it is present, and **say so if it is absent** rather
than answering a sourcing question from memory.

**The guardrail**, in `ask.py`'s own words: *"lexical match shows the corpus
discusses this, it does not by itself make the claim true."* A passage mentioning
a concept is not a passage endorsing a parameter. A contradiction is a finding,
not a failed search. Any status moving off Convention must name the chunk id.

---

## 17. File map

```
python/engine.py              5,521  source of truth: scoring, sizing, pipeline
python/backtest.py            3,272  measurement harness (NOT mirrored)
python/ab_compare.py            205  A/B two engine revisions
src/utils/screenerEngine.ts   3,821  bit-identical TypeScript mirror
src/utils/pythonEngineSource.ts      generated, 1 giant line (~269 KB)
src/data/nifty100Snapshot.ts         generated constituent snapshot
src/tests/                           6 vitest suites + helpers + fixtures
test_python.py                1,011  161 tests, loads the engine from the notebook
scripts/build_python_source.mjs      codegen and --check
scripts/check_doc_figures.py         CURRENT / RETIRED / SCORING passes
scripts/forward_log.py               monthly forward-log writer
scripts/venv-python.sh               interpreter shim
run_checks.sh                   469  the release gate
knowledge/                           the research record (§16)
data/nifty100_source.csv             NSE constituents, 100 rows, Industry column
data-store/                          GITIGNORED — artefacts, reports, logs
Books_TO_study/                      GITIGNORED — the 319-document corpus
Indian_Equity_Quantitative_Engine.ipynb   generated Colab notebook
```

### Data flow — backtest

`main` → `parse_price_history_csv` → `PriceBook` → `market_calendar` →
`month_end_sessions` → **per rebalance**: `rank_on` → (`technicals_on` →
`compute_technical_indicators` → `calculate_technical_score`) or
(`continuous_scores` → `neutralise`) → `buffered_selection` → `hold_return` →
`decile_study` → `_ic_statistics` / `_phase_averaged_statistics` → `performance`
→ `align_to` → `cagr_difference_ci` → `after_tax_performance` → `format_report`.

### Data flow — live

`main` → seed 42 → `setup_storage_paths` → `load_run_config` → **run 90 self-tests
and abort on failure** → `run_pipeline` → `FundamentalsAdapter.list_available` →
`read_fundamentals_csv` → `fundamentals_age_days` → score → rank → size → write
watchlist.

---

## 18. What is blocked

Full treatment in `knowledge/blocked.md`. Summary:

**1. The fundamental half has never been measured.** 60% of the composite, gates
admission, zero backtests. The Screener MCP route was **spiked on ten tickers and
ruled NOT VIABLE** on three independent grounds: quarterly history is exactly
8 quarters (Sep 2024 → Jun 2026, zero overlap with 2015–2023); **no filing date
exists anywhere**, and the one field that would carry it — a row named `Raw PDF` —
is returned empty; and **restatements are structurally invisible** (one value per
cell, no vintage axis — lagging cannot fix this).

**2. Survivorship.** Today's Nifty 100 applied to history. Every absolute figure,
including the benchmarks, is flattered. The *relative* comparison is largely
protected because both sides draw the same survivor set.

**3. Universe width and history depth — and they are not equal levers.**

| lever | floor | % of today |
|---|---|---|
| today (86 months, ~89 names) | 0.0581 | 100% |
| **250 months** | **0.0338** | **58%** |
| 500 names | 0.0498 | 86% |

**History is the lever; width is not.** Going from 100 to 500 names — a fivefold
collection effort — moves the floor 14%. The residual term (0.157) dominates the
sampling term (0.108), and widening the cross-section does not touch the residual.

**4. No real Screener export.** `data-store/fundamentals/` holds invented figures.

**What is not blocked:** the forward log, which accrues one clean observation a
month and is independent of the span every other figure was searched over.

---

## 19. Known documentation drift

Found during this handbook's fact-gathering and recorded rather than silently
fixed. These are in other documents, not this one.

1. **`knowledge/project-guide.html` carries stale line counts** — it says
   `backtest.py` 1,198 (actual 3,272), `rulebook.md` 961 (actual 1,632),
   `engine.py` 5,500 (actual 5,521). Its test inventory says `backtest --self-test`
   has 10 tests; the actual run reports **35**. The 234 vitest and 161 python
   figures are correct.

2. **`data-store/README.md` has two stale contracts** — it says networked runs
   download "18 months" of prices while `HISTORY_START = "2015-01-01"`, and
   describes the price CSV as `Date,Ticker,Close,Volume` while the real contract
   is seven columns.

3. **`format_report()` never prints the `after_tax` block.** The Tier 2 headline
   exists only in `results.json` and the rulebook; `report.md` for that run still
   carries "taxes are not modelled… These are pre-tax figures", which is false for
   that artefact.

4. **The rulebook's rank-buffering table is not re-derivable from a stored
   artefact.** Every stored artefact has `buffer_multiple` 1 or absent, and none
   is quarterly.

5. **Artefact schema drift.** `backtest_current_score` has no overlapping/
   non-overlapping split; `backtest_blocks` and `backtest_rsiflip` have the split
   but no HAC or bootstrap keys and a phase-0-only non-overlapping column. Only
   `backtest_preholdout`, `rung_c_neutral` and `tier2_reversal` carry the
   phase-averaged estimate. **Comparing a non-overlapping IC across artefacts
   compares two different estimators.**

6. **`rung_d_skipmonth` is bit-identical to `rung_c_neutral`** in its overlapping
   and portfolio figures, because rung C was regenerated on the post-skip-month
   engine after rung D was produced. The pair no longer isolates the skip month.

7. **`data-store/reports/backtest_hac/` is an empty directory.**

---

## 20. Quick reference

### Constants

```python
# scoring
TECHNICAL_BLOCK_MAX = {"trend":40, "momentum":30, "relStrength":20, "volume":10}
RSI_MOMENTUM_FLOOR = 50.0      RSI_EXHAUSTION = 80.0
MACD_FLAT_BAND = 0.05          ADX_TRENDING = 25.0
SESSIONS_FOR_TECHNICAL_SCORE = 200
RELATIVE_STRENGTH_SKIP_SESSIONS = 21

# sizing
DEFAULT_TARGET_VOLATILITY_PCT = 12.0   MAX_RISK_PER_POSITION_PCT = 5.0
STOP_ATR_MULTIPLE = 2.0                SESSIONS_FOR_PORTFOLIO_VOLATILITY = 60
DEFAULT_MAX_POSITION_WEIGHT_PCT = 10.0 DEFAULT_MAX_SECTOR_WEIGHT_PCT = 25.0

# backtest
DEFAULT_TOP_N = 20             DEFAULT_COST_BPS_PER_SIDE = 15.0
HOLDOUT_START = "2023-01-01"   OUT_OF_SAMPLE_START = "2022-01-01"
DECILE_HORIZONS = (1, 3, 6, 12)
BOOTSTRAP_DRAWS = 2000         BOOTSTRAP_SEED = 20260913
Z_FOR_80_PERCENT_POWER = 0.8416
WINSOR_TAIL = 0.025            MIN_SECTOR_BUCKET = 3

# tax
STCG_RATE = 0.20   LTCG_RATE = 0.125   LONG_TERM_MONTHS = 12
LTCG_EXEMPTION_RUPEES = 125000.0
```

### Common tasks

```bash
# screen offline with cached data
npm run screen:offline

# full backtest, pre-holdout, shipped points model
.venv/bin/python python/backtest.py \
  --prices data-store/market_data/<file>.csv \
  --out-dir data-store/reports/mine

# the four-rung ladder
#   A: (no flags)   B: --continuous
#   C: --continuous --neutral      D: C + (skip month is now the engine default)

# the pre-registered reversal, after tax, at retail size
.venv/bin/python python/backtest.py --prices <file> \
  --out-dir data-store/reports/tier2_reversal \
  --continuous --neutral --portfolio-block momentum --invert --capital 1000000

# record this month's forward-log entry, then COMMIT IT
scripts/venv-python.sh scripts/forward_log.py --prices <file>

# all five checks
npm run lint && npm run check:python && npm run check:docs && \
  .venv/bin/python test_python.py && npx vitest run
```

### Reading a result honestly

1. Is the figure above its **own detection floor**? If not, it is noise.
2. Does it clear **correction**? If not, it is not significant.
3. What is the **search count**? Every pre-holdout cell is one of 125+.
4. Are both sides of any comparison measured over the **same months**?
5. Is the standard error **HAC** where windows overlap — and remember it still
   understates by roughly a quarter.
6. If it looks good, **ask why it might be an artefact before asking why it might
   be real.** That is the habit this repository is built around.
