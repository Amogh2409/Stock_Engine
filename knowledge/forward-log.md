# The forward log

**Started 2026-09-14. First entry: `knowledge/forward-log/2026-09-11.json`.**

Every figure elsewhere in this project comes from one span, 2015–2022, searched
125+ ways. This is the only record that will not.

## What it is

A dated file per month, written **before** the month it applies to, holding two
selections computed from data available at the time:

- the **shipped** top 20 by the composite technical score;
- the **reversal** selection — the 20 *lowest*-momentum names at rung C, which is
  what `knowledge/preregistration.md`'s hypothesis implies you would hold if you
  believed it.

Each entry is stamped with the engine's scoring hash, the git commit, and the
value of `RELATIVE_STRENGTH_SKIP_SESSIONS`, because the scoring has already
changed once during this project and will change again. An entry whose hash does
not match a later engine is still valid evidence about *that* engine.

Write it with:

```
scripts/venv-python.sh scripts/forward_log.py --prices <price-history.csv>
```

## What makes it evidence rather than a diary

1. **Committed to git before the month it covers.** The timestamp is what a
   sceptical reader checks. An uncommitted file, or one committed afterwards,
   proves nothing at all.
2. **Never revised.** The script refuses to overwrite an existing entry. A
   correction is a **new dated file** stating what was wrong and why — never an
   edit, because an edited entry is indistinguishable from a fabricated one.
3. **No returns are computed at write time.** Scoring an entry is a separate act
   at a later date. If the run that picks the names also reports how they did,
   nothing stops the picking being adjusted until the reporting looks better;
   that is the mechanism by which a forward log becomes a backtest.

## What it is not

It is **not** a backtest, and it is not a substitute for the reserved window. It
does not touch the holdout: it reads prices up to today to compute a score, which
is what the engine is for, and it measures no return and makes no comparison. The
returns that will eventually score these entries have not happened yet.

It is also **not** a live trading record. No orders exist, no slippage is
incurred, and the execution assumption is the backtest's — the open after the
signal date. A paper record and a traded record differ, and this is the former.

## When it could carry a conclusion

Against the effect the pre-registration names — momentum at 1 month,
|IC| 0.0407, ic_sd 0.1245 — starting from zero in October 2026:

| power | months needed | reached about |
| --- | --- | --- |
| 50% | 39 | Dec 2029 |
| 60% | 49 | Oct 2030 |
| 70% | 60 | Oct 2031 |
| **80%** | **76** | **Jan 2033** |

For scale, the reserved window already holds 44 periods and reaches 80% power in
**May 2029** by doing nothing.

**So the forward log is the slower route, and that is not its point.** Its value
is independence: it is the only evidence here not drawn from the span every other
figure was searched over, and it is the only route that produces new data rather
than spending a fixed stock of it. `knowledge/rulebook.md` names exactly two ways
past the feedback objection — "either a period held back and never examined, or
forward paper-trading from today". This is the second, and it had never been set
up.

The two are complements, not alternatives. Doing nothing until 2029 gets the
holdout at 80% power and nothing else. Starting the log now gets the holdout at
80% power **and** an independent 31-month record to read beside it — which is
worth more than either alone, because the failure mode of the holdout is that it
answers a question about a variant selected by a 125-cell search, and the forward
log's selections are fixed in advance and cannot be.

## How to score it later, when the time comes

Not yet, and not by extending this file. When there are enough entries:

- score each entry against the returns of the month it covered, computed the same
  way the backtest computes them;
- state the number of entries, the mean IC, and its standard error, with the same
  honest floor this project applies everywhere else;
- **report entries whose engine hash differs separately.** Pooling across scoring
  changes would measure an average of engines rather than an engine.

Do not score it early and repeatedly. Looking at a growing record until it says
something is the same error as searching a window until a cell clears, and it is
harder to see because each look feels like diligence.
