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
import ast
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARTEFACT = ROOT / "data-store/reports/backtest_preholdout/results.json"
DOCS = ("knowledge/rulebook.md", "knowledge/project-guide.html",
        "knowledge/preregistration.md")

# The two functions that decide what the engine SCORES. Their source is hashed so
# that a scoring change cannot land without someone being told that
# knowledge/holdout.md and knowledge/preregistration.md make claims about what
# has and has not changed.
#
# This exists because a figure check could not catch it and did not. holdout.md
# said the scoring rules were "byte-identical" for a day after
# RELATIVE_STRENGTH_SKIP_SESSIONS changed them. Nothing failed, because the claim
# was prose and every figure still matched its artefact.
SCORING_SOURCE = "python/engine.py"
SCORING_FUNCTIONS = ("compute_technical_indicators", "calculate_technical_score")
# Re-record in the SAME commit that changes the scoring, never separately.
SCORING_HASH = "8ed6a95febeac1326c2fb8b6b70d7eeb7bb9eef9f9191ced23e1dee083b0e98f"

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
    # Superseded 2026-09-14 when the skip-month window changed what relative
    # strength measures. The cell no longer clears its floor.
    "0.0774": ("relStrength 6m floor, pre-skip-month engine", "0.0880"),
    "+0.0784": ("relStrength 6m IC, pre-skip-month engine", "+0.0781"),
    "0.198": ("relStrength 6m Bonferroni p, pre-skip-month engine", "0.402"),
    "−0.0060": ("composite 1m IC, pre-skip-month engine", "−0.0033"),
    "19.41%": ("strategy CAGR, pre-skip-month engine", "22.52%"),
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


def _paragraphs(body):
    """(line number, line, enclosing paragraph) for every line.

    Paragraphs are blank-line separated, which is the unit a retraction is
    actually written in. HTML gets the same treatment: its blocks are separated
    by blank lines too, and a tag-aware parse would buy nothing here.
    """
    lines = body.splitlines()
    out, start = [], 0
    for index, line in enumerate(lines):
        if line.strip():
            continue
        block = "\n".join(lines[start:index])
        for offset in range(start, index):
            out.append((offset + 1, lines[offset], block))
        start = index + 1
    block = "\n".join(lines[start:])
    for offset in range(start, len(lines)):
        out.append((offset + 1, lines[offset], block))
    return out


def scoring_digest():
    """(sha256 of the scoring functions' source, names found).

    Hashes the function SOURCE rather than a list of named constants, because the
    awards are integer literals inside calculate_technical_score -- 12.0 for the
    200-day test, the bare -15 for the 52-week proximity -- and a constants-only
    hash would miss every one of them.
    """
    tree = ast.parse((ROOT / SCORING_SOURCE).read_text())
    wanted = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in SCORING_FUNCTIONS:
            wanted[node.name] = ast.unparse(node)
    missing = [name for name in SCORING_FUNCTIONS if name not in wanted]
    if missing:
        # Renamed or removed is itself a scoring change, and must not hash to
        # something stable by accident.
        return "missing:" + ",".join(missing), missing

    # EVERY module-level ALL_CAPS constant, not a hand-listed subset.
    #
    # The first version of this guard hashed only the two function bodies and was
    # verified red by editing RSI_MOMENTUM_FLOOR -- which it did NOT catch,
    # because the constant is defined at module level and the functions only
    # reference the name. It was blind to RSI_MOMENTUM_FLOOR, MACD_FLAT_BAND,
    # ADX_TRENDING, TECHNICAL_BLOCK_MAX and to the value of
    # RELATIVE_STRENGTH_SKIP_SESSIONS, the very change that motivated it.
    #
    # Collected automatically rather than from a list, so a constant added later
    # is covered without anyone remembering to add it. The cost is that a
    # non-scoring constant also trips the guard; that is the conservative
    # direction and far cheaper than the miss.
    constants = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                constants[target.id] = ast.unparse(node.value)
    blob = "\n".join(wanted[name] for name in SCORING_FUNCTIONS)
    blob += "\n" + "\n".join("%s=%s" % (k, constants[k]) for k in sorted(constants))
    return (hashlib.sha256(blob.encode("utf-8")).hexdigest(),
            list(SCORING_FUNCTIONS) + ["%d module constants" % len(constants)])


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
            for number, line, block in _paragraphs(text[name]):
                if value not in line:
                    continue
                # Scoped to the PARAGRAPH, not the line. A retraction is prose and
                # routinely puts the marker a line or two from the figure it is
                # retracting; a line-scoped check forced the two onto one line and
                # distorted the writing to satisfy the tool.
                lowered = block.lower()
                if any(marker in lowered for marker in RETRACTION_MARKERS):
                    print("  ok (retraction)  %s:%d  %s" % (name, number, value))
                    continue
                failures.append("%s:%d carries retired %s (%s; now %s)"
                                % (name, number, value, was, now))
                print("  STALE            %s:%d  %s -- %s" % (name, number, value, was))

    print()
    print("SCORING -- engine.py's scoring functions must match the recorded hash")
    digest, seen = scoring_digest()
    print("  hashed: %s" % ", ".join(seen))
    if digest == SCORING_HASH:
        print("  hash unchanged: %s" % digest[:16])
    else:
        print("  CHANGED: recorded %s, actual %s" % (SCORING_HASH[:16], digest[:16]))
        failures.append(
            "engine.py scoring changed (hash %s). knowledge/holdout.md and "
            "knowledge/preregistration.md both make claims about what has and has "
            "not changed -- re-read them, then re-record SCORING_HASH in THIS "
            "commit." % digest[:16])

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
