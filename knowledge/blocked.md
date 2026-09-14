# What is blocked, and what it would take

Four structural limits. Each carries what it needs, what it would cost, what it
would buy, and — the part that matters most — **what is currently false because
of it**. A limitation that has not been written down as a falsehood tends to get
quoted as a finding.

Everything measured in this project is **exploratory**: one window, 2015–2022,
searched 125+ ways, and that count is a lower bound.

---

## 1. The fundamental half has never been measured

**It is 60% of the composite score and it gates admission at
`minimum_total_score`.** It has not been backtested once. This is the largest
unexplored thing in the project by a wide margin — every result here, every null,
every detection floor, describes the *technical* 40%.

### What it needs

Point-in-time fundamentals: for each rebalance date, the figures a person could
actually have known **then**. Not today's figures applied to 2016.

### What it would cost — and the route was spiked, not assumed

A Screener MCP server exposing quarterly results was the obvious candidate. It
was spiked on ten tickers (RELIANCE, TCS, HDFCBANK, INFY, ITC, LT, SBIN,
BHARTIARTL, ASIANPAINT, MARUTI) on 2026-09-14. **Verdict: NOT VIABLE**, on three
independent grounds, any one of which is sufficient.

**(a) Quarterly history does not reach the backtest window at all.**
`get_quarterly_results` returns exactly **8 quarters**, and the window is
identical for all ten tickers: **Sep 2024 → Jun 2026**. The tool's only
parameters are `symbol` and `financial_type` — there is no `from`, `to`, `as_of`
or period argument. The backtest window 2015–2023 has **zero** quarterly
observations. Not sparse. Zero. Confirmed directly.

**(b) No filing date exists anywhere.** Every period is a bare month-year label.
No tool in the server accepts or returns a filing date, result date,
announcement date or `as_of` stamp. The one field that would carry it — a row
literally named `Raw PDF`, which on Screener.in links to the filed document — is
returned **empty for every ticker**. Confirmed directly.

**(c) Restatements are structurally invisible, and this is unworkaroundable.**
The API returns exactly one value per (symbol, period, metric). No version field,
no vintage, no amendment flag, no "as originally reported" marker. Today's Mar
2016 column is today's re-presented figure. **Lagging cannot fix this**: a lag
changes *when* you read a cell, not *which vintage* the cell holds.

Two unflagged entity breaks make it concrete. HDFCBANK Revenue goes
Mar 2023 = 170,754 → Mar 2024 = 283,649 across the HDFC Ltd merger, presented as
one continuous row. ITC's Mar 2025 Net Profit of 35,052 cr sits between 20,751
and 21,018, inflated by the hotels demerger with no marker. A mechanical score
reads both as fundamental signal.

Annual statements *do* reach Mar 2015 — but as a single current-vintage snapshot,
which is exactly the look-ahead being avoided, and at roughly 60 stock-year
observations across ten names it is too thin to measure a rank IC even if the
vintages were right.

Smaller problems, recorded so nobody rediscovers them: pledge data is promised by
the tool description and returned for **none** of the ten; ROCE is present only
for non-banks and ROE only for banks, so no ticker has both historically;
`Financing Margin %` is negative for both banks across every year (a broken
derivation); percentages arrive **pre-rounded to integers**, which would cause
heavy tie-clustering in any cross-sectional rank; and responses are a rendered
ASCII table in one JSON string whose row schema changes by sector.

**So the honest cost is not "some engineering". It is a different data source** —
a commercial point-in-time database (Capitaline, CMIE Prowess, Refinitiv PIT) or
a forward archive built by scraping from today onward, which yields usable
history starting 2026 and nothing before.

### What it would buy

The ability to say anything at all about 60% of the score. Possibly the discovery
that the fundamental half carries the edge the technical half does not — it is
the one place left where an untested hypothesis could still be true.

### What is currently false because of it

- Any statement that "the engine has been measured" — only 40% of it has.
- The project guide's framing of the null as being about *the engine*. It is
  about the technical score.
- Any inference from `minimum_total_score` gating: the gate has never been shown
  to admit better companies than it rejects.

---

## 2. Survivorship: today's Nifty 100 applied to history

**Every absolute figure in this project is flattered, including the benchmarks.**

### What it needs

Historical index constituents with their join and leave dates — the Nifty 100 as
it stood at each rebalance, not as it stands now.

### What it would cost

NSE publishes index reconstitution announcements, but not as a machine-readable
historical membership series; assembling one means parsing years of circulars, or
buying it. Moderate effort, and it is a data-acquisition problem rather than a
research one.

### What it would buy

Absolute figures that mean something. The *relative* comparison — strategy versus
equal weight — is largely protected, because both sides draw from the same
survivor set, which is why this project leans on the gap rather than the level.

### What is currently false because of it

- Equal weight's 23.29% and the strategy's 22.52% are both overstated by an
  unknown amount. Neither is a return anyone could have earned.
- The index comparison (^NSEI at 12.05%) is the *only* line not survivorship-
  selected, which is part of why the strategy beats it and loses to equal weight.
- Any statement of the form "this strategy would have returned X".

---

## 3. Universe width and history depth — and they are not equal levers

**100 names, 86 months.** The detection floor is what this buys, and the two
levers were computed separately so they can be compared rather than bundled.

Current: composite 1-month floor **0.058**, against a plausible cross-sectional
effect of 0.02–0.05. The measurement cannot see the effect it is looking for.

The floor decomposes as `ic_sd = sqrt(residual² + sampling²)` where the residual
is genuine month-to-month variation (**0.157**) and sampling is cross-sectional
noise (**0.108**). More names shrinks only the second term.

| lever | floor | % of today |
| --- | --- | --- |
| today: 86 months, ~89 names | 0.0581 | 100% |
| **250 months**, ~89 names | **0.0338** | **58%** |
| 500 months, ~89 names | 0.0239 | 41% |
| 86 months, **200 names** | 0.0525 | 90% |
| 86 months, **500 names** | 0.0498 | 86% |
| 86 months, 1000 names | 0.0488 | 84% |
| 250 months **and** 500 names | 0.0290 | 50% |

**History is the lever. Width is not.** Going from 100 names to 500 — a fivefold
data-collection effort — moves the floor 14%. Going from 86 months to 250 moves
it 42%. The reason is arithmetic: the residual term dominates and widening the
cross-section does not touch it.

### What each would cost

More history: price data before 2015 for Indian equities, plus the survivorship
work in §2, because a longer window makes constituent drift worse rather than
better. More names: widening to the Nifty 500 is mostly a download, and the
spike above suggests fundamentals coverage degrades on smaller names.

### What it would buy

At 250 months the floor reaches **most** of the plausible effect band. At 86
months and 500 names it reaches only the top of it. Neither reaches all of it.

### What is currently false because of it

- Any reading of a null here as "there is no effect". Every null in this project
  is *absence of evidence* and the documents now say so.
- The implicit assumption that widening the universe is the obvious next step. It
  is the expensive lever with the small return.

---

## 4. There is no real Screener export

`data-store/fundamentals/sample_screener_export.csv` holds **31 rows of invented
figures**, of which 11 overlap the 101 priced tickers. It is a fixture.

### What it needs

A real export from a Screener.in account, or the MCP route ruled out in §1.

### What it would cost

Minutes, for the *current* snapshot. The current snapshot is not the blocker —
§1 is. A current export cannot be applied to history without the look-ahead this
project refuses.

### What it would buy

The ability to run the shipped engine end to end on real inputs and produce a
watchlist anyone could act on **today**. That is a product capability, not a
research one, and it is worth separating: the engine's *live* path has never run
on real fundamentals either.

### What is currently false because of it

- Any figure in the repository that appears to describe fundamental scoring.
  `sample_screener_export.csv` is named "sample" but its numbers look like data.
- The sector map is the exception and should not be confused with it:
  `data/nifty100_source.csv` is the real NSE constituents file and covers 100 of
  100 names.

---

## What is not blocked

Worth stating, because a document like this reads as though nothing can be done.

The **forward log** (`knowledge/forward-log.md`) requires none of the above. It
accrues one clean observation a month, is independent of the 2015–2022 span every
other figure was searched over, and started on 2026-09-14. It is the only route
here that produces new data rather than spending a fixed stock of it.
