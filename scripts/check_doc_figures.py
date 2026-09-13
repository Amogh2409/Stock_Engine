#!/usr/bin/env python3
"""Check the knowledge documents against the measurement artefact.

WHY THIS EXISTS, AND WHY IT SWEEPS PROSE AS WELL AS TABLES.

On 2026-09-14 a commit verified "20 of 20" restated figures against
results.json and still shipped a superseded number, because the check
enumerated TABULATED figures and the survivor sat inside a sentence. This
project deliberately puts figures in prose so they carry their basis -- the
RSI-flip portfolio numbers were moved out of a table for exactly that reason --
so a table-only check is structurally blind to the place we most often put a
number on purpose.

Two passes, and the second is the one that was missing:

  CURRENT  every figure in KEY_FIGURES is recomputed from the artefact and must
           appear in the document that claims it.
  RETIRED  every superseded value in RETIRED must appear NOWHERE, in a table or
           a sentence, except on a line that explicitly retracts it.

The discipline this encodes: when you supersede a figure, add its old value to
RETIRED in the same commit. That is what makes the sweep self-maintaining
rather than a snapshot that rots.

Usage:  .venv/bin/python scripts/check_doc_figures.py
Exit 0 if the documents agree with the artefact, 1 otherwise.
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTEFACT = ROOT / "data-store/reports/backtest_preholdout/results.json"
DOCS = ("knowledge/rulebook.md", "knowledge/project-guide.html")

# A line carrying any of these is retracting a number on purpose, not asserting
# it. Retired values are allowed there and nowhere else.
RETRACTION_MARKERS = (
    "previously", "superseded", "was wrong", "that was wrong", "retract",
    "withdrawn", "earlier version", "first draft", "gave p", "no longer",
    "used to read", "instead of the", "not the", "rather than the",
)

# value -> (what it was, what replaced it). Add to this in the SAME commit that
# supersedes a figure.
RETIRED = {
    "0.0725": ("relStrength 6m detection floor", "0.0774, after the HAC df fix"),
    "0.0587": ("relStrength 3m detection floor", "0.0601"),
    "0.0688": ("relStrength 12m detection floor", "0.0828"),
    "0.706": ("composite 6m Bonferroni p", "1.000"),
    "5.9%": ("family-wise chance at 20 tests", "18%"),
    "within 2% at every horizon": (
        "claim that the bootstrap agreed with HAC",
        "withdrawn; the bootstrap is smaller in 10 of 15 cells"),
}


def key_figures(results):
    """Figures the documents quote, recomputed from the artefact."""
    out = {}
    for horizon in ("1", "3", "6", "12"):
        block = results["deciles"][horizon]["overlapping"]
        out["composite %sm floor" % horizon] = round(block["detectable_ic_80pct"], 3)
        out["composite %sm p*" % horizon] = round(block["hac_p_bonferroni"], 3)
    rel = results["block_deciles"]["relStrength"]
    for horizon in ("1", "3", "6", "12"):
        block = rel[horizon]["overlapping"]
        out["relStrength %sm IC" % horizon] = round(block["mean_ic"], 4)
        out["relStrength %sm floor" % horizon] = round(block["detectable_ic_80pct"], 4)
        out["relStrength %sm p*" % horizon] = round(block["hac_p_bonferroni"], 3)
        out["relStrength %sm df" % horizon] = block["hac_df"]
    return out


def main():
    if not ARTEFACT.exists():
        # Returns 1, deliberately. Do NOT convert this to a skip to make a
        # clean-room checkout pass: data-store/** is gitignored, so the artefact
        # is legitimately absent there, and a skip would turn a loud failure into
        # a silent pass -- which is the same defect as counting a missing figure
        # without failing on it. This script belongs in the pre-commit list, not
        # in run_checks.sh.
        print("no artefact at %s -- run the backtest first" % ARTEFACT)
        return 1
    results = json.loads(ARTEFACT.read_text())
    figures = key_figures(results)
    text = {name: (ROOT / name).read_text() for name in DOCS}
    combined = "\n".join(text.values()).replace("−", "-")

    failures = []

    print("CURRENT -- every key figure must appear somewhere in the documents")
    missing = 0
    for label, value in sorted(figures.items()):
        rendered = ("%g" % value) if isinstance(value, int) else str(value)
        present = rendered in combined
        if not present and isinstance(value, float):
            present = ("%.4f" % value) in combined or ("%.3f" % value) in combined
        if not present:
            missing += 1
            # Appended to `failures`, not merely printed. An earlier revision
            # counted these and printed them and never let them reach the exit
            # code, so a figure that vanished from both documents printed
            # MISSING and the script still exited 0 -- a green signal that looks
            # the same when the thing is broken, inside the tool written to stop
            # exactly that.
            failures.append("%s (%s) appears in neither document" % (label, rendered))
            print("  MISSING  %-28s %s" % (label, rendered))
    print("  %d of %d key figures present" % (len(figures) - missing, len(figures)))

    print()
    print("RETIRED -- superseded values must appear only on a retraction line")
    for value, (was, now) in sorted(RETIRED.items()):
        for name in DOCS:
            for number, line in enumerate(text[name].splitlines(), start=1):
                if value not in line:
                    continue
                lowered = line.lower()
                if any(marker in lowered for marker in RETRACTION_MARKERS):
                    print("  ok (retraction)  %s:%d  %s" % (name, number, value))
                    continue
                failures.append("%s:%d carries retired %s (%s; now %s)"
                                % (name, number, value, was, now))
                print("  STALE            %s:%d  %s -- %s" % (name, number, value, was))

    print()
    if failures:
        print("FAILED: %d stale figure(s)" % len(failures))
        for failure in failures:
            print("   " + failure)
        return 1
    print("PASSED: no retired figure survives outside a retraction")
    return 0


if __name__ == "__main__":
    sys.exit(main())
