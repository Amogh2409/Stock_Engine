# Deferred

Presentation inconsistencies go here as a line, not into a commit.

Eleven of the first sixteen commits on this work were documentation, and the
last four each fixed the presentation of the one before. That is a loop, and
this file exists to break it. A wrong *number* or a claim stated more strongly
than the data supports is still a bug and still gets fixed. A wording, layout
or labelling nit waits here until something substantive touches the same file.

## Open

- **The non-overlapping IC series keeps only phase 0 of h.** `backtest.py`'s
  decile study appends to `non_overlapping` when `index % horizon == 0`, which
  retains one of the h valid non-overlapping series and discards the other h−1.
  Averaging all h phases is the efficient estimator and throws nothing away. Less
  urgent now that HAC carries the headline, but it is free information currently
  unused. (Audit finding 6.)
- **The bootstrap percentile index is off by one rank.** `means[int(0.025 * draws)]`
  is index 50 of 2000; the 2.5th percentile by nearest-rank is index 49.
  Sub-percentile effect on the reported interval. (Audit finding 7.)

- **`PROJECT_GUIDE.pdf` is stale** relative to `knowledge/project-guide.html`
  as of 2026-09-14. The HTML carries the horizon-qualified block claims and the
  relative-strength 6-month cell; the PDF predates them. Regenerate next time
  the guide is edited for a substantive reason, not on its own.
- **The guide does not carry the full-span dilution figures** (relative strength
  +0.0784 pre-holdout against +0.0485 including reserved years, and 12 of 16
  block-horizon cells larger pre-holdout). They are in `rulebook.md` under
  "The one cell above its own floor". Only worth mirroring if the guide's
  treatment of that cell is ever expanded.

## Resolved

- ~~Guide and rulebook claimed "four flat blocks" without a horizon qualifier,
  and the guide's alert generalised a 1-month result across all horizons.~~
  Fixed 2026-09-14 in the same commit as this file, together with the related
  claim that all four 1-month floors sit "at or above" the plausible effect
  range — two of the four sit inside it.
