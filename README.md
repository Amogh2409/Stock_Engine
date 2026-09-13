# Indian Equity Quantitative Screening Engine (v6)

Explainable, rule-based screening and scoring for Indian equities from
**Screener.in CSV exports**. Ships as two engines that are held to exact
agreement by test:

| | Where | What it is |
|---|---|---|
| Browser | `src/` | React app: upload a CSV (and optionally daily prices), screen, inspect, export |
| Notebook | `python/engine.py` → `Indian_Equity_Quantitative_Engine.ipynb` | One-cell Colab pipeline with Drive persistence, saved settings and downloaded price history |

**Research signals only.** Nothing here places orders, and none of it is
investment advice.

---

## Quick start

Requires Node `^22.22.2`, `^24.15.0` or `>=26` (the floor set by jsdom and
vitest; Node 25 installs with warnings but is not supported by them).

```bash
npm ci
npm run dev            # http://localhost:3000
```

The app opens on a bundled sample so every tab is populated immediately. It is
**illustrative data**: the company names are real, the figures are invented, and
the app labels it as such. Only some of its rows are Nifty 100 constituents, so
the default universe shows a short list — the status bar says how many rows fell
outside the index and offers **Screen all rows**. Upload your own Screener.in
**CSV** to replace the sample, and **Upload prices** to add technical
confirmation.

### Run the engine over your own data

The engine needs pandas and numpy, which the system `python3` usually lacks, so
everything runs through the project's virtualenv. Create it once:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-network.txt   # or requirements-test.txt for offline only
```

Then drop your Screener.in CSV export into `data-store/fundamentals/` and run:

```bash
npm run screen            # refreshes the universe, downloads prices
npm run screen:offline    # cached universe, cached prices only
.venv/bin/python python/engine.py --help
```

The npm scripts use `.venv/bin/python` and say how to create it if it is
missing; set `PARITY_PYTHON` to use a different interpreter.

Every run writes into `data-store/` and nowhere else:

```
data-store/
  fundamentals/   <- your Screener.in CSV exports go here
  config/         config.json (optional saved settings, see below)
  reports/        watchlist_<stamp>.csv, rejected_<stamp>.csv, ranking_changes.csv
                  (the watchlist carries WeightPct, StopPrice, StopDistancePct
                   and SizingBasis; weights sum to less than 100 whenever the
                   volatility target holds part of the account in cash)
  watchlists/     latest_watchlist.json  (what the next run compares against)
  logs/           run_<stamp>.log  + run_<stamp>.json
  cache/          cached NSE constituent list
  market_data/    price_history_<date>_<key>.csv  (daily prices, one file per day)
```

`data-store/README.md` documents the layout in full. To put the data somewhere
else, in precedence order:

```bash
python3 python/engine.py --data-dir /path/to/store   # 1. flag
TRADEBOT_DATA_DIR=/path/to/store npm run screen      # 2. environment
                                                     # 3. Google Drive, in Colab
                                                     # 4. <project>/data-store
```

### Logging

Each run produces two files in `data-store/logs/`:

- **`run_<stamp>.log`** — the complete console transcript. `stdout` and
  `stderr` are teed into it, so the self-verification output and any traceback
  are captured too, not just the tidy progress lines.
- **`run_<stamp>.json`** — a machine-readable summary: exit code, status, the
  effective configuration and where it came from, rows loaded,
  evaluated/passed/rejected counts, duplicates removed, rows outside the
  universe, whether it was a first run, the universe source, where the price
  history came from, and the absolute path of every artefact written.

The summary is written in a `finally` block, so an aborted or failed run still
leaves a record saying why. Streams are always restored afterwards.

Convenience scripts:

```bash
npm run screen            # full run (live NSE universe refresh + price download)
npm run screen:offline    # full run, cached universe and cached prices only
npm run screen:selftest   # offline unit tests only, no pipeline
npm run test:python       # the standalone Python suite
```

### Verify the whole thing

```bash
bash run_checks.sh
```

That is the release gate. It builds an isolated copy, creates a throwaway
virtualenv from pinned requirements, runs lint, the full test suite, the
production build, a notebook byte-comparison, a Python compile of every
notebook cell, the offline Python suite, the cross-engine parity suite and a
production server smoke test — then packages the archive, extracts it
somewhere else and repeats the mandatory checks before emitting any hashes.
No required step is allowed to fail.

---

## Price history and technical confirmation

Technical confirmation is a separate 0–100 score from daily closing prices. It
never affects pass/fail or the fundamental score.

- **Python / Colab** downloads daily history from **2015-01-01** for every
  ticker in the active universe — not merely the ones this export happens to
  contain — plus the `^NSEI` benchmark, with `yfinance`, and
  saves it as `data-store/market_data/price_history_<date>_<key>.csv`. A second
  run the same day reuses that file when it prices every ticker. A download
  that prices only some tickers (Yahoo rate-limits) is retried on the next run
  and never hides a more complete file: an `--offline` run, a failed download
  or a partial one uses the newest earlier file whenever it covers more
  tickers, and the run log says which file was used and why. A file with no
  prices for any screened ticker (only the benchmark) is never used.
- **Browser** has no price source of its own. **Upload prices** accepts the
  same file — so uploading the one the Python run saved reproduces its
  technical scores exactly.

The file format is plain CSV, easy to produce from any source:

```
Date,Ticker,Open,High,Low,Close,Volume
2026-09-10,TCS,4162.0,4195.8,4150.1,4180.5,1834200
2026-09-10,^NSEI,24280.0,24330.4,24255.9,24310.2,
```

Fields are separated by commas and any line ending works. `Date` is a real
calendar date written `YYYY-MM-DD`, `Ticker` is the screener ticker (`Symbol`
is accepted as a header), and `Open`, `High`, `Low` and `Volume` are all
optional. A four-column `Date,Ticker,Close,Volume` file written by an earlier
version still loads unchanged; the indicators that need a high and a low then
report themselves unavailable rather than substituting the close. A session
missing only its high and low keeps its close instead of being discarded.
Rows with a malformed or
impossible date, a blank ticker or a non-numeric close are skipped and counted;
a later row for the same ticker and date wins. The benchmark is matched to each
stock by date, so relative strength compares sessions where both actually
traded. The 20-day volume ratio needs a volume on the latest session.

Two different situations are reported differently:

| Situation | Technical score | Per-stock warning |
|---|---|---|
| Technical confirmation turned off | N/A — "Technical screening disabled" | none |
| The run has **no price history at all** | N/A — "No price history loaded" (said once, in the status bar or run log) | none |
| History loaded, but **this ticker is not in it** | N/A — "Technical data unavailable" | `Technical Data Missing` |
| History loaded, but **under 50 sessions** for this ticker | N/A — "Only N sessions of price history…" | `Technical Data Missing` |
| Some indicators lack enough sessions | scored from what exists | `Technical Data Partial (...)` |

---

## Saved configuration

The browser's **Universe & config** tab can **Export** its settings as
`config.json` and **Import** one back. The Python engine reads the same file:

1. `--config FILE`, if given;
2. otherwise `<data root>/config/config.json`, if present;
3. otherwise the built-in defaults.

```json
{
  "schema_version": "v6",
  "app": { "universe_mode": "custom", "custom_symbols": ["TCS", "INFY"], "top_n": 20 },
  "screening": { "minRocePct": 18 }
}
```

Every key is optional; an omitted key keeps its default. Unknown keys, wrong
types and out-of-range values are **errors, never clamped**: the run stops with
exit code 2 and the log lists every problem, and the browser applies nothing
from a file with a problem. Both engines validate against the same ranges
(`CONFIG_LIMITS`), which the parity suite asserts are identical.

Three `app` keys control position sizing:

| Key | Default | What it does |
| --- | --- | --- |
| `target_volatility_pct` | `12` | Annualised volatility the sized basket aims at. Since the engine is long-only and never leveraged, this only ever *reduces* exposure: the shortfall stays in cash. TSaM p.53 offers 12% and calls it modest; p.1048 offers "typically about 15%" and then calls 15% aggressive. |
| `max_position_weight_pct` | `10` | Most of the account any one company may take. |
| `max_sector_weight_pct` | `25` | Most of the account any one sector group may take. Capped weight is **not** redistributed — it stays in cash. |

`max_position_weight_pct` above `max_sector_weight_pct` is a config error, since
the group cap is applied second and the larger number could never bind.

The run summary reports two percentages that are easy to confuse:
`deploymentPct` is the scale factor the volatility target applies **before** the
caps, and `investedPct` is what actually survives them. The gap between them is
weight the caps removed, and like the volatility shortfall it stays in cash
rather than being redistributed. Portfolio volatility is measured over the most
recent 252 sessions, not over the whole price file — an eleven-year average
could never rise, so deployment could never fall when it should.

The 5% per-position **risk** ceiling (TSaM p.1032) is deliberately not
configurable: a setting that let a config file exceed the book's hard limit
would make the limit decorative. Note it is a ceiling on risk, not on position
size — at a 6% stop it permits 83% of capital in one name, so concentration is
governed by the two caps above, not by it. `knowledge/rulebook.md` records which
of these numbers a book actually supports; most of them it does not.

---

## The two-engine contract

The browser and the notebook must agree exactly. `src/tests/parity.test.ts`
runs both over all 31 bundled companies — with and without price history, with
custom filters, and under the Nifty 100 universe — and asserts identical
ticker, pass/fail, score, coverage, rejection reasons, warning flags, technical
indicators and scores, watchlist rank and ordering, plus byte-identical
watchlist, rejected and ranking-changes CSVs. These conventions make that
possible:

**Score precision.** One decimal, half-up. `round1()` is
`Math.round(x*10)/10` in TypeScript and `floor(x*10 + 0.5)/10` in Python,
which are bit-identical on the same IEEE-754 double. Scores drive rank order,
so a rounding difference is a *ranking* difference — never treat it as
cosmetic. Python's built-in `round()` is banker's rounding and must not be
used for scores.

**Ordering.** Watchlists sort by score descending, then ticker ascending by
Unicode code point. TypeScript uses `compareCodePoints`, never `localeCompare`,
whose collation is locale-dependent (`A_B` sorts before `AB` under ICU).
Ranks are contiguous and 1-based over that sorted, truncated list.

**Accepted number shapes.** `cleanNumeric` / `clean_numeric` and
`parseStrictDecimal` / `parse_strict_decimal` accept only a plain ASCII decimal
body. Hex (`0x10`), binary (`0b101`), octal (`0o17`), underscore separators
(`1_0`), `inf`, `nan` and non-ASCII digits are rejected, because JavaScript's
`Number()` and Python's `float()` disagree about them.

**Whitespace and word characters.** Python's `\s`, `\w`, `\d` and `str.strip()`
are Unicode-aware in ways JavaScript's are not, so the Python side spells out
JavaScript's whitespace set (`_WS_CHARS`, used by `js_trim`) and the ASCII word
and digit classes.

**Numbers inside text.** Where a number appears in a message both engines emit
(custom-filter rejection reasons), Python formats it with
`js_number_to_string`, which reproduces JavaScript's `String(number)`: `30`,
not `30.0`.

**Indicator arithmetic.** Moving averages, volume ratios and volatility use a
plain left-to-right sum in both engines. Python's built-in `sum()` is avoided:
since Python 3.12 it compensates rounding, and a last-bit difference can flip a
price-versus-SMA comparison on a flat price series.

### Unit-aware parsing

Screener.in denominates monetary columns in **rupee crore**. Every field
declares its unit, and an unexpected suffix is a rejection rather than a
silent strip:

| Input | Unit | Result |
|---|---|---|
| `1 CRORE` | crore | `1` |
| `100 LAKH` | crore | `1` |
| `10 LAKH` | crore | `0.1` |
| `15.5%` | percent | `15.5` |
| `15 CR` | percent | `null` — monetary suffix on a percentage |
| `0.5%` | ratio | `null` — percent on a dimensionless ratio |

### Identifier mapping

Column resolution is order-independent and never lets one identifier consume
another:

| Headers present | `ticker` | `bseCode` |
|---|---|---|
| `NSE Code` + `BSE Code` | `NSE Code` | `BSE Code` |
| `BSE Code` only | `BSE Code` | `BSE Code` (shared fallback) |
| `NSE Code` only | `NSE Code` | — |

Deduplication then runs on ticker, then BSE code, then normalised company
name, identically in both engines.

### Technical history

Indicator availability is explicit, and points are awarded only for
indicators that genuinely exist:

| Indicator | Minimum sessions |
|---|---|
| SMA50 | 50 |
| SMA200 | 200 |
| 50/200 cross | both SMAs |
| 6-month relative strength | 126 sessions where stock and `^NSEI` both traded |
| **52-week high** | **252** |

A 200-session maximum is *not* a 52-week high. With fewer than 252 valid
sessions the 52-week high is unavailable and scores **zero** — it is never
approximated. History is downloaded from 2015-01-01, so every indicator window
is comfortably covered and the same file can feed a backtest.

### Delta tracking

Both engines emit the same schema:

```
Ticker,Name,ChangeType,PreviousRank,CurrentRank,RankDelta,PreviousScore,CurrentScore,ScoreDelta,NewWarnings
```

`ChangeType` ∈ `NEW_ENTRY | RANK_UP | RANK_DOWN | REMOVED_ENTRY | STABLE`, and
`RankDelta = PreviousRank − CurrentRank` (positive means it moved up). Deltas
are blank where an entry or removal makes the comparison undefined. A removed
entry keeps the name recorded in the previous snapshot.

### CSV export safety

Every user-derived **string** cell whose first non-whitespace character is
`=`, `+`, `-` or `@` is prefixed with an apostrophe before export, covering the
watchlist, rejected-stock and ranking-changes files (each downloadable from its
tab in the browser). Genuinely numeric columns stay numeric — a negative score
delta does not become text.

---

## Scoring

100 points across five factors: financial quality 30, growth 25,
balance-sheet safety 20, valuation 15, governance 10. **Every company is scored
and ranked, including the ones a red flag disqualifies.** Each awarded point carries
its own one-line reason (`scoreLines`), and every candidate also carries a
generated rationale naming its strongest and weakest factors, its key input
metrics, and any rejection reasons or warnings.

### Three outcomes, decided in this order

| Outcome | When | Result |
|---|---|---|
| **Not scored** | A financial company whose export lacks the metrics its model needs | `Not scored: missing bank metrics (…)`, naming each absent column |
| **Rejected** | A hard red flag fired — the numbers cannot be trusted | Scored and explained, but never selectable |
| **Scored** | Everything else | Graded sub-scores, each point explained |

A rejected company is still scored, so a comparison across the whole index can
show its fundamentals beside the reason it is disqualified: "Vedanta scores 43.1
but its promoters have pledged" says more than a bare 0.0. The score is built
only from the fields that remain trustworthy — negative net worth earns nothing
for D/E, and a negative P/B is reported as "not meaningful".

**A score is not a licence to buy.** Whether a company may be held is carried by
`passed` and `redFlags`, never by the score alone. Anything that selects
companies — the watchlist today, and any future signal or backtest code — must
filter on those fields first. Sorting on score alone walks a pledged promoter
stake and an unusable balance sheet straight back in at rank 20.

### Hard red flags

These reject outright. They are not "unattractive" findings — an expensive
company still gets a score — they mean *this row is not usable as evidence*:

1. Negative net worth (a negative P/B or D/E changes sign, not magnitude, so a
   "cheap" P/B of −0.3 is insolvency rather than a bargain)
2. Promoter pledge above the configured limit
3. Negative operating cash flow — **non-financial companies only**, because a
   growing loan book consumes cash and the rule would reject healthy lenders
4. Fundamental coverage below the configured minimum
5. Revenue of zero or less, when the export carries a revenue column
6. Impossible promoter holding or pledge (outside 0–100)
7. Market capitalisation of zero or less
8. A pledge recorded against a promoter holding of zero — internally contradictory
9. Two rows for the same company disagreeing on their numbers

### The composite: it gates on one number and ranks on another

The **fundamental total** decides whether a company qualifies, against
`minimum_total_score`. The **composite** — the fundamental and technical halves
combined, the technical one carrying `technical_weight_pct` of it, 40% by
default — decides where a qualifying company sits in the ranking. Two numbers
doing two jobs reads like an inconsistency until the jobs are named:

- The technical half is *confirmation*. Fundamentals qualify a company; the
  chart orders what already qualified. Gating on the composite would let a
  weak-fundamental, strong-momentum company through on the strength of its
  chart, which inverts the design rather than refining it.
- Gating on the composite would also let `technical_weight_pct` silently
  redefine what passes: raising it to 80 would change the qualifying set without
  anyone touching the threshold.

A company the run could not price has no technical half, so its composite is
just its fundamental score. Those companies are **ranked in a list of their
own**, not mixed in. At the default weights, fundamentals of 90 with no price
data scores 90, while fundamentals of 90 with technicals of 50 scores 74 — so
interleaving them would make absence from the price file worth sixteen points,
and worth most to recent listings, illiquid names and whatever the download was
rate-limited out of. When *no* company in the run has a technical score, the
whole list is on one scale and there is no split.

Verdict bands (Strong / Good / Average / Weak) are descriptive labels over the
composite, chosen to spread the current scale so a long list can be read
quickly. Nothing tests that a "Strong" goes on to outperform a "Good".

### The strict screen

The old pass/fail hurdles — minimum ROCE, growth, leverage, interest cover,
valuation ceilings, promoter holding — are *preferences*, not data-integrity
problems. By default they **cost points rather than rejecting**, so a mediocre
company is ranked low instead of vanishing. Setting `app.strict_screen` to
`true` re-applies them as a filter over the ranked list. The strict screen
never changes what a company scores; it only changes what passes.

### Financial companies

Banks and NBFCs are scored by their own model rather than excluded. Quality is
return on assets and return on equity; safety is capital adequacy (scored above
the 9% regulatory floor) and net NPA (scored down from a clean book to 2%).
Growth, valuation and governance are shared with the general model, so the
30/25/20/15/10 caps hold and totals stay comparable.

That model needs four extra Screener.in columns — **Return on assets**,
**Gross NPA %**, **Net NPA %** and **Capital adequacy ratio**. Without them a
lender is reported as `not scored: missing bank metrics`, naming exactly which
are absent, rather than being scored on ratios that do not describe it. CASA
and financing margin are *reported but never scored*: an NBFC has no CASA at
all, so paying points for it would penalise every NBFC for being one.

Insurers need a third model (solvency ratio rather than NPAs) and are not yet
covered; they currently land in "not scored".

### Sector-relative valuation

Valuation is judged against the loaded file's own sectors, because a P/E of 30
is dear for a bank and cheap for a fast-growing software company. Half the
yardstick earns full marks, the yardstick itself earns half, and half again
above it earns nothing.

Screener.in's industry labels are fine-grained ("FMCG - Food" and "FMCG -
Household Products" are separate), so a 100-row export splits into roughly 25
industries, most holding one or two companies. The yardstick therefore falls
back in order, and **the reason line always names which basis was used**, so a
fallback can never be mistaken for a true sector comparison:

1. The fine industry median, when at least 5 companies in it report the metric
2. otherwise a coarse sector group median, on the same threshold
3. otherwise the whole-universe median

Only positive ratios feed a median: a negative P/E is a loss and a negative P/B
is negative net worth, and neither is a cheap valuation.

All fifteen thresholds, plus top-N, minimum score and staleness, are editable
in **Universe & config**, and every input is clamped to a documented range.
Custom filters are built from a fixed field list and a fixed operator list —
free text is never evaluated as an expression.

---

## Layout

```
python/engine.py            Python engine - THE source of truth for the notebook
data-store/                 All runtime data and logs (see data-store/README.md)
scripts/build_python_source.mjs
                            engine.py -> src/utils/pythonEngineSource.ts codegen
data/nifty100_snapshot.json Pinned universe + provenance (feeds BOTH engines)
data/nifty100_source.csv    The NSE CSV the snapshot was built from
src/utils/screenerEngine.ts TypeScript engine
src/utils/testRunner.ts     In-app validation suite ("Unit tests" tab)
src/tests/                  Vitest suites, including cross-engine parity
test_python.py              Standalone Python suite (loads the shipped notebook)
run_checks.sh               Strict release gate
```

### Why the Python lives in a `.py` file

It used to be embedded in a JavaScript template literal, which silently ate
every backslash: `\w` became `w`, `\s` became `s`, and `\b` became a literal
backspace. That quietly destroyed three regexes and left column detection
matching nothing. The Python is now a real file, embedded via `JSON.stringify`
codegen, so escaping is done by a serialiser rather than by hand. `npm run
check:python` fails if `engine.py` and the generated module drift apart, and
`src/tests/notebook.test.ts` asserts the escapes survived.

Regenerate after editing `python/engine.py`:

```bash
npm run build:python && npm run generate:notebook
```

---

## Universe provenance

`data/nifty100_snapshot.json` records the source URL, retrieval timestamp,
as-of date, SHA-256 of the source CSV and the 100 symbols. Both engines derive
their fallback list from that one file.

It is a **cached snapshot, not a live feed**, and the UI and notebook both say
so with its as-of date. The notebook refreshes it from NSE when the network is
reachable; when that fails it falls back and reports the fallback explicitly.
Tests assert actual symbol membership, not merely the count — a count-only
check once passed while a quarter of the constituents were wrong.

---

## Testing

```bash
PARITY_PYTHON=.venv/bin/python npm test              # frontend + cross-engine parity
npm run test:python                                  # notebook engine, offline
RUN_NETWORK_TESTS=1 npm run test:python              # adds the optional network tests
bash run_checks.sh                                   # full release gate
```

The parity suite spawns Python, so it needs an interpreter with `pandas` and
`numpy`: `PARITY_PYTHON` points at one, defaulting to `python3`. With the
virtualenv above, `PARITY_PYTHON=.venv/bin/python` is the whole setup.

**The suite fails closed.** There is no fallback result and no hard-coded
expected value substituting for a real run. It fails if the notebook cannot be
generated or loaded, if Python or its dependencies are missing, if the
subprocess exits non-zero, if the JSON is invalid or incomplete, if rows are
missing, or if the two engines' row counts differ. Network tests are separate
and opt-in; they never gate a release.

---

## Known limitations

1. On-demand only — no continuous monitoring or scheduling.
2. Fundamentals are refreshed manually via Screener.in CSV export. CSV is the
   only supported format; XLSX is rejected by design.
3. Price history comes from `yfinance`, an unofficial source, and feeds only
   the separate technical-confirmation score. The browser cannot download it;
   upload a price-history CSV there (the Python run saves one).
4. The Nifty 100 list is a cached, dated snapshot (see above).
5. Financial companies are scored by a separate model that needs four extra
   Screener.in columns; without them they are reported as "not scored:
   missing bank metrics" rather than scored wrongly. Insurers need a different
   model again and are not yet covered.
6. Scores are deterministic research signals, not price predictions.
7. Technical indicators need sufficient history; missing ones score zero
   rather than being approximated.
