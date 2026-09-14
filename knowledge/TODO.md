# Deferred

Presentation inconsistencies go here as a line, not into a commit.

Eleven of the first sixteen commits on this work were documentation, and the
last four each fixed the presentation of the one before. That is a loop, and
this file exists to break it. A wrong *number* or a claim stated more strongly
than the data supports is still a bug and still gets fixed. A wording, layout
or labelling nit waits here until something substantive touches the same file.

## Open


- **The guide does not carry the full-span dilution figures** (relative strength
  +0.0784 pre-holdout against +0.0485 including reserved years, and 12 of 16
  block-horizon cells larger pre-holdout). They are in `rulebook.md` under
  "The one cell above its own floor". Only worth mirroring if the guide's
  treatment of that cell is ever expanded.

## Resolved

- ~~Audit finding 6: the non-overlapping IC series kept only phase 0 of h.~~
  Fixed 2026-09-14. All h phases are now averaged. The effect was larger than
  "free information" suggested: at 12 months the column went from 6 observations
  to 75, and the composite IC from +0.0725 to +0.0156 — the old figure was an
  artefact of which month the price file happened to begin in.
- ~~Audit finding 7: the bootstrap percentile index was off by one rank.~~
  Fixed 2026-09-14, nearest-rank. Sub-percentile, and it moved the
  pre-registration's published CI by one rank; recorded in its amendment log.
- ~~`PROJECT_GUIDE.pdf` is stale.~~ Regenerated 2026-09-14.

- ~~Guide and rulebook claimed "four flat blocks" without a horizon qualifier,
  and the guide's alert generalised a 1-month result across all horizons.~~
  Fixed 2026-09-14 in the same commit as this file, together with the related
  claim that all four 1-month floors sit "at or above" the plausible effect
  range — two of the four sit inside it.
