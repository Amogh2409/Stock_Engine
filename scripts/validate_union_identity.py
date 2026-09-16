#!/usr/bin/env python3
"""Does NIFTY 50 + NIFTY Next 50 reproduce the official NIFTY 100?

NSE's methodology says the Nifty 100 is the combined portfolio of the Nifty 50
and the Nifty Next 50. If that holds exactly, the union of two reports that ARE
still published is an authoritative substitute for the standalone Nifty 100
report, which the monthly archive stopped carrying after March 2022.

It is not taken on faith. There are 87 months where all three reports exist, so
the identity is checked on every one of them, at two levels:

  SECURITY level  every listed line, including alternate share classes
  COMPANY level   securities collapsed to their issuer

The distinction is the whole question. A dual-class listing puts two SECURITIES
in the index for one COMPANY, and the sub-indices may not carry both.

No forward returns are read. This is a membership comparison.
"""
from __future__ import annotations

import collections
import csv
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from nse_index_history import (parse_constituents, INDEX_TITLE, _normalise_title,  # noqa: E402
                               months_between, FIRST, LAST)

RAW = ROOT / "data-store" / "universe" / "raw"
SCRATCH = ROOT / "data-store" / "universe" / ".probe"

TITLES = {
    "nifty100": {"nifty100", "cnx100"},
    "nifty50": {"nifty50", "cnxnifty", "sandpcnxnifty"},
    "next50": {"niftynext50", "cnxniftyjunior", "cnxniftyjr", "niftyjunior"},
}
CANDIDATES = {
    "nifty100": re.compile(r"^(nifty|cnx)[_ ]?100[_ ].*\.pdf$", re.I),
    "nifty50": re.compile(r"^(nifty[_ ]?50|cnxnifty)[_ ].*\.pdf$", re.I),
    "next50": re.compile(r"^(nifty[_ ]?next[_ ]?50|cnxniftyjr|cnxniftyjunior)[_ ].*\.pdf$", re.I),
}

# A company identity from its security name: drop the share-class marker and
# the corporate suffix, so "Tata Motors Ltd DVR" and "Tata Motors Ltd." are one
# issuer. Deliberately conservative -- it only strips markers that denote a
# share CLASS, never anything that could distinguish two real companies.
CLASS_MARKERS = re.compile(
    r"\b(dvr|dvr\s*shares?|differential\s+voting\s+rights?|"
    r"class\s+[ab]|partly\s+paid|pp\b|rights?\s+entitlement)\b", re.I)
SUFFIX = re.compile(r"[\s.,-]*\b(ltd|limited|corporation|corp|co|inc|plc)\b[\s.]*$", re.I)


def company_key(name):
    text = CLASS_MARKERS.sub(" ", name or "")
    text = re.sub(r"\s+", " ", text).strip()
    for _ in range(3):
        text = SUFFIX.sub("", text).strip()
    return re.sub(r"[^a-z0-9]", "", text.lower())


def read_index(archive, which):
    """(symbols, records) for one index inside one monthly archive, or None."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    pattern, wanted = CANDIDATES[which], TITLES[which]
    try:
        bundle = zipfile.ZipFile(archive)
    except Exception:
        return None
    with bundle:
        names = [n for n in sorted(bundle.namelist())
                 if pattern.match(Path(n).name)]
        for name in names:
            probe = SCRATCH / "probe.pdf"
            probe.write_bytes(bundle.read(name))
            try:
                text = subprocess.run(["pdftotext", "-raw", str(probe), "-"],
                                      capture_output=True, text=True,
                                      check=True).stdout
            except Exception:
                continue
            title = INDEX_TITLE.search(text)
            if not title or _normalise_title(title.group(1)) not in wanted:
                continue
            _date, records, _rejected = parse_constituents(text)
            if records:
                return {r["symbol"] for r in records}, records
    return None


def main():
    labels = months_between(FIRST, LAST)
    rows = []
    security_exact = company_exact = 0
    compared = 0
    only_100 = collections.Counter()
    only_union = collections.Counter()
    per_month = []

    for label in labels:
        archive = RAW / ("indices_data%s.zip" % label)
        if not archive.exists():
            continue
        hundred = read_index(archive, "nifty100")
        if hundred is None:
            continue                      # post-2022: nothing to validate against
        fifty = read_index(archive, "nifty50")
        nxt = read_index(archive, "next50")
        if fifty is None or nxt is None:
            per_month.append((label, None, None, "sub-index missing"))
            continue

        compared += 1
        h_syms, h_recs = hundred
        union = fifty[0] | nxt[0]
        union_recs = {r["symbol"]: r for r in (fifty[1] + nxt[1])}

        sec_only_100 = sorted(h_syms - union)
        sec_only_union = sorted(union - h_syms)
        if not sec_only_100 and not sec_only_union:
            security_exact += 1

        h_companies = {company_key(r["security_name"]) for r in h_recs}
        u_companies = {company_key(r["security_name"]) for r in union_recs.values()}
        co_only_100 = sorted(h_companies - u_companies)
        co_only_union = sorted(u_companies - h_companies)
        if not co_only_100 and not co_only_union:
            company_exact += 1

        for s in sec_only_100:
            only_100[s] += 1
        for s in sec_only_union:
            only_union[s] += 1
        per_month.append((label, sec_only_100, sec_only_union,
                          "company-exact" if not (co_only_100 or co_only_union)
                          else "COMPANY MISMATCH %s|%s" % (co_only_100, co_only_union)))
        rows.append({"label": label, "n100": len(h_syms), "union": len(union),
                     "security_diff": len(sec_only_100) + len(sec_only_union),
                     "company_exact": not (co_only_100 or co_only_union)})

    out = []
    add = out.append
    add("=" * 68)
    add("UNION IDENTITY VALIDATION  --  NIFTY 50 + NIFTY Next 50 vs NIFTY 100")
    add("=" * 68)
    add("")
    add("months compared                      %d" % compared)
    add("exact SECURITY-level matches         %d" % security_exact)
    add("exact COMPANY-level matches          %d" % company_exact)
    add("months with security differences     %d" % (compared - security_exact))
    add("months with company differences      %d" % (compared - company_exact))
    add("")
    add("Securities in NIFTY 100 but NOT in the union:")
    for symbol, count in only_100.most_common():
        add("   %-14s in %d month(s)" % (symbol, count))
    if not only_100:
        add("   (none)")
    add("")
    add("Securities in the union but NOT in NIFTY 100:")
    for symbol, count in only_union.most_common():
        add("   %-14s in %d month(s)" % (symbol, count))
    if not only_union:
        add("   (none)")
    add("")
    mismatches = [m for m in per_month if m[3].startswith("COMPANY MISMATCH")]
    add("UNEXPLAINED COMPANY-LEVEL MISMATCHES: %d" % len(mismatches))
    for label, _a, _b, why in mismatches[:10]:
        add("   %-9s %s" % (label, why))
    add("")
    if company_exact == compared and compared > 0:
        verdict = ("VALID WITH DOCUMENTED SECURITY-CLASS RULE"
                   if security_exact < compared else "VALID")
    else:
        verdict = "INVALID"
    add("POST-2022 UNION RECONSTRUCTION: %s" % verdict)
    report = "\n".join(out)
    (ROOT / "data-store" / "universe" / "union_validation.txt").write_text(
        report + "\n", encoding="utf-8")
    json.dump(rows, (ROOT / "data-store" / "universe" / "union_validation.json").open("w"),
              indent=1)
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
