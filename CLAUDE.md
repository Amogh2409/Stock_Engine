# TradeBot — working notes for agents

A deterministic Indian-equity screening engine. `python/engine.py` is the source
of truth; `src/utils/screenerEngine.ts` mirrors it bit-for-bit and a parity suite
pins them together.

**`docs/HANDBOOK.md` is the complete technical reference** — every formula, every
threshold, every command, every measured result, and every known limit. Read its
§1 before quoting any figure from this repository.

## There is a searchable book corpus, and it is almost never used

`Books_TO_study/` holds **319 documents** with a built knowledge graph —
**1,519 nodes** (319 documents, 1,200 concepts), **10,529 edges**, and
**42,745 indexed chunks** — plus a working offline query tool. Nothing in the
rest of this repository referenced it until 2026-09-14, and it had never been
queried in anger. `knowledge/rulebook.md` carries **15 Convention-tagged sections** — 10 engine
parameters and 5 policies or facts, not the 23 a `grep -c` returns — meaning "no
book in this repo justifies it", a claim that was, until that sweep, mostly
untested against this corpus rather than tested and failed.

**Check it is present before relying on it.** `Books_TO_study/` is **gitignored**,
so a fresh clone, a clean-room worktree and most CI checkouts will not have it:

```bash
ls Books_TO_study/_tools/ask.py            # present?
.venv/bin/python Books_TO_study/_tools/ask.py stats
```

**If it is absent, say so.** Do not answer a sourcing question from memory and do
not let an unavailable corpus quietly become "no source found" — those are
different claims and the rulebook's status tags depend on the difference.

### How to query it

```bash
P=.venv/bin/python; A=Books_TO_study/_tools/ask.py
$P $A stats                              # corpus and graph summary
$P $A search "average directional index" -k 8
$P $A concept "mean reversion"           # graph: related concepts, documents, evidence
$P $A verify "ADX above 25 indicates a trending market"
```

Everything is offline and deterministic — no API calls, no embeddings. Every
result carries a document, a licence and a **chunk id** such as `TSaM.pdf#626`.

### Cite the chunk id, always

Any rulebook status that moves off **Convention** must name the chunk id that
moved it. "Verified against the books" without an id is not verifiable by the
next reader, and this project has already published three claims built on a
top-level directory listing while 128 more files sat in a subdirectory.

### The guardrail — this search is confirmation-seeking by construction

You will usually be searching for support for a rule the engine **already uses**.
`ask.py` says the important part itself, in its own verdict text:

> lexical match shows the corpus discusses this, it does not by itself make the
> claim true.

So:

- **A passage mentioning a concept is not a passage endorsing a parameter.**
  "The corpus discusses RSI" does not source `RSI > 50`. Read the span.
- **A contradiction is a finding, not a failed search.** Record it with the same
  weight as support — the rulebook has a `Contradicted` tag for exactly this, and
  its most valuable entry is one.
- **A rule searched and not found stays Convention**, with the query recorded so
  nobody re-runs it.

## Non-negotiable working rules

- **Never tune a threshold to improve a result.** Measuring is fine; adopting a
  parameter because it improved a number, on any window, is fitting.
- **Do not touch the reserved window.** `knowledge/holdout.md` reserves
  2023-01-01 onward; `backtest.py` truncates there by default.
  `--no-respect-holdout` spends it. `knowledge/preregistration.md` holds the one
  pre-registered test and it has not been run.
- **Every pre-holdout figure is exploratory.** Nothing measured there is called
  significant whatever its p, and the search count (80+ cells, a lower bound) is
  stated wherever such a figure appears. See rulebook.md, "Everything measured on
  the pre-holdout window is exploratory".
- **`engine.py` is the source of truth.** After any change to it run
  `npm run build:python` and `npm run generate:notebook`, or `npm run check:python`
  fails. Measurement variants belong in `python/backtest.py`, never in the engine
  — see `--rsi-flip`, `--continuous`, `--neutral`, `--no-skip-month` for the pattern.
- **Update `knowledge/rulebook.md` in the same commit as any rule change**, with
  its status: Sourced / Adapted / Convention / Contradicted.
- **A scoring change trips `npm run check:docs`.** It hashes `engine.py`'s two
  scoring functions and all 106 module constants. When it fails, re-read
  `knowledge/holdout.md` and `knowledge/preregistration.md` — both make claims
  about what has and has not changed — then re-record `SCORING_HASH` **in the
  same commit**. Never re-record it separately; that is how the claim goes false
  without anyone noticing.
- **Stage explicit paths.** Never `git add -A`. Read `git diff --cached --stat`
  before every commit and abort on an unexpected file.
- Presentation nits go to `knowledge/TODO.md` as a line, not into a commit.

## The five checks before any commit

```bash
npm run lint            # tsc --noEmit               → expect exit 0
npm run check:python    # generated files in sync    → expect exit 0
npm run check:docs      # figures match the artefact → expect exit 0
.venv/bin/python test_python.py          # 161 tests → expect exit 0
npx vitest run                           # 234 tests → expect exit 0
.venv/bin/python python/backtest.py --self-test      → expect exit 0
```

**Read each exit code from the command that produced it.** `cmd | tail` returns
*tail's* exit code — this has already caused one false "passed" report here.

## Habits this repository was built by

- **Before trusting a passing test, ask what it would print if the thing under
  test were broken.** If the answer is "the same", it carries no information.
  Verify red **in place**, not from a copy in `/tmp` — a copy has resolved its
  paths wrongly and "failed" for the wrong reason here.
- **A grep count is not evidence until you have read the matching lines.** Zero
  counts are often shell mangling; in zsh an unquoted `--include=*.py` is
  glob-eaten and an unquoted `$VAR` holding two flags is passed as one argument.
  A fixed-width context pattern cannot match near a line boundary, so a zero from
  a windowed search is weaker than a zero from a plain one.
- **Check the artefact against itself**, not only its figures against their
  source. A correct number under a wrong heading passes every data check.
- **Do not verify your own freshly computed numbers** when another session can.
  That is the weakest check either one runs.
