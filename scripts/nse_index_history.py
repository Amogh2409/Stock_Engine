#!/usr/bin/env python3
"""Acquire and parse NSE Indices' official monthly Nifty 100 constituent reports.

WHY THIS EXISTS. Every backtest in this repository applies TODAY's Nifty 100 to
history. Companies that fell out of the index over the period are absent, and
those are disproportionately the ones that did badly, so every figure the
research produced is an upper bound rather than an estimate. Fixing that needs
the membership that was actually published at each historical date.

THE SOURCE IS THE INDEX PROVIDER ITSELF. NSE Indices publishes a monthly
"Indices - Market Capitalisation and Weightage" archive containing, per index, a
dated PDF of constituents with close price, index market capitalisation and
index weight. That is a primary record rather than a reconstruction: it is what
the index provider said the index contained on that date.

    https://www.niftyindices.com/Indices_-_Market_Capitalisation_and_Weightage/
        indices_data<Mon><Year>.zip   ->   nifty100_<Mon><Year>.pdf

WHAT IS PRESERVED. The original ZIP, the original PDF, the source URL, the
retrieval timestamp, the SHA-256 of both, the report's own effective date and
the parser version. Nothing is derived without its provenance, because a
membership table with no audit trail cannot be told apart from a guess.

ON COUNTING. The obvious assertion -- exactly 100 constituents -- is WRONG, and
believing it would have rejected correct official data. The Nifty 100 holds 100
COMPANIES, and a company with two listed share classes contributes two
SECURITIES: February 2017 carries both TATAMOTORS and TATAMTRDVR, for 101 rows.
So the parser asserts a narrow expected BAND, records the exact count for every
report, and fails loudly outside it. A silently short universe is itself a
survivorship bias pointing the same way as the one this file exists to remove.

Usage:
    scripts/venv-python.sh scripts/nse_index_history.py --download
    scripts/venv-python.sh scripts/nse_index_history.py --parse-only
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data-store" / "universe"
RAW = STORE / "raw"
PDFS = STORE / "pdf"
PIT_CSV = STORE / "pit_nifty100.csv"
MANIFEST = STORE / "manifest.jsonl"

PARSER_VERSION = "1.0.0"
BASE = ("https://www.niftyindices.com/Indices_-_Market_Capitalisation_and_Weightage/"
        "indices_data%s.zip")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

# The window the price history covers.
FIRST = (2015, 1)
LAST = (2026, 9)

# A band, not an equality -- see the module docstring.
EXPECTED_MIN, EXPECTED_MAX = 99, 103

# In the RAW text stream a record's three trailing numbers are close price,
# index weight and index market capitalisation, in that order.
TRIPLE = re.compile(r"^(.*?)\s+([\d,]+\.\d{1,2})\s+([\d,]+\.\d{1,2})\s+([\d,]+)\s*$")
SYMBOL = re.compile(r"^[A-Z][A-Z0-9&]([A-Z0-9&.\-]{0,18})$")
FURNITURE = re.compile(
    r"^(Symbol\b|Constituents of|\(Rs\.|Weightage|\(%\)|\d{1,3}$|Disclaimer|"
    r"endeavors\.|and all liability|information contained|"
    r"[A-Z][a-z]+ \d{1,2}, \d{4}$)")
REPORT_DATE = re.compile(r"^([A-Z][a-z]+ \d{1,2}, \d{4})$", re.M)
INDUSTRY = re.compile(r"((?:[A-Z][A-Z0-9&/,'\-]*(?:\s+|$)){1,6})$")


def months_between(first, last):
    year, month = first
    out = []
    while (year, month) <= last:
        out.append("%s%d" % (MONTHS[month - 1], year))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def download_month(label, force=False):
    """Fetch one monthly archive, preserving the original bytes untouched."""
    RAW.mkdir(parents=True, exist_ok=True)
    target = RAW / ("indices_data%s.zip" % label)
    if target.exists() and not force:
        return target, False
    request = urllib.request.Request(BASE % label,
                                     headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read()
    if len(body) < 1000 or not body.startswith(b"PK"):
        raise ValueError("not a zip archive (%d bytes)" % len(body))
    target.write_bytes(body)
    return target, True


# Filename is a HINT, never the decision. Naming drifted across the decade --
# "cnx100_Sep2015.pdf", "nifty100_Feb2017.pdf", "NIFTY_100_Aug2018.pdf" -- and
# the lookalikes are worse than the variation: "NIFTY100_Liquid_15_Aug2018.pdf"
# matches any reasonable filename pattern for the Nifty 100 and is a DIFFERENT
# INDEX of fifteen stocks. Selecting it parsed 15 constituents and, but for the
# count guard, would have silently produced a fifteen-name universe.
CANDIDATE_NAME = re.compile(r"^(nifty|cnx)[_ ]?100[_ ].*\.pdf$", re.I)
INDEX_TITLE = re.compile(r"Constituents of\s+(.+)")
# Normalised titles that ARE this index. Anything else -- Liquid 15, Equal
# Weight, Midcap, Smallcap, Low Volatility 30 -- is not.
WANTED_TITLES = {"nifty100", "cnx100"}


def _normalise_title(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def extract_pdf(archive, label):
    """Pull the Nifty 100 PDF out of the monthly archive, preserving it.

    Selection is by the document's OWN TITLE, not by its filename. Returns
    (path, original_name) or (None, reason).
    """
    PDFS.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        candidates = [n for n in bundle.namelist()
                      if CANDIDATE_NAME.match(Path(n).name)]
        if not candidates:
            return None, "no nifty100-like filename in the archive"
        confirmed = []
        for name in sorted(candidates):
            data = bundle.read(name)
            scratch = PDFS / ("_probe_%s.pdf" % label)
            scratch.write_bytes(data)
            try:
                title = INDEX_TITLE.search(pdf_text(scratch))
            except Exception:
                title = None
            finally:
                scratch.unlink(missing_ok=True)
            if title and _normalise_title(title.group(1)) in WANTED_TITLES:
                confirmed.append((name, data, title.group(1).strip()))
        if not confirmed:
            return None, ("no candidate titled Nifty 100 (saw: %s)"
                          % ", ".join(Path(c).name for c in candidates[:4]))
        if len(confirmed) > 1:
            return None, ("ambiguous: %d candidates claim to be Nifty 100"
                          % len(confirmed))
    name, data, title = confirmed[0]
    target = PDFS / ("nifty100_%s.pdf" % label)
    target.write_bytes(data)
    return target, Path(name).name


def pdf_text(path):
    """Raw-order text.

    `-raw` keeps reading order. `-layout` splits a wrapped row across columns
    and loses the symbol for every constituent whose security name wraps -- 18
    of 101 in February 2017, which is exactly how a parser produces a short
    universe while looking like it worked.
    """
    done = subprocess.run(["pdftotext", "-raw", str(path), "-"],
                          capture_output=True, text=True, check=True)
    return done.stdout


def parse_constituents(text):
    """(report_date, records, rejected) from one report's raw text.

    A record is assembled by accumulating lines until one ends with the numeric
    triple. That handles a wrapped security name without needing to know how
    many lines it wrapped over, which is what makes the parse survive ten years
    of slightly different typesetting.
    """
    stamp = REPORT_DATE.search(text)
    report_date = (dt.datetime.strptime(stamp.group(1), "%B %d, %Y").date()
                   if stamp else None)

    records, buffer, rejected = [], [], []
    for line in text.splitlines():
        line = line.strip()
        if not line or FURNITURE.match(line):
            continue
        buffer.append(line)
        if not TRIPLE.match(line):
            continue
        whole = " ".join(buffer)
        buffer = []
        matched = TRIPLE.match(whole)
        if matched is None:
            continue
        head = matched.group(1).split()
        if not head:
            continue
        symbol = head[0]
        if not SYMBOL.match(symbol):
            rejected.append(symbol)
            continue
        description = " ".join(head[1:])
        found = INDUSTRY.search(description)
        industry = found.group(1).strip() if found else ""
        name = (description[:len(description) - len(industry)].strip()
                if industry else description)
        records.append({
            "symbol": symbol, "security_name": name, "industry": industry,
            "close_price": matched.group(2).replace(",", ""),
            "weight_pct": matched.group(3).replace(",", ""),
            "index_mcap_cr": matched.group(4).replace(",", ""),
        })
    return report_date, records, rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--parse-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sleep", type=float, default=0.4)
    args = parser.parse_args()

    STORE.mkdir(parents=True, exist_ok=True)
    labels = months_between(FIRST, LAST)
    rows, manifest, failures = [], [], []
    stamp = dt.datetime.now().isoformat(timespec="seconds")

    for index, label in enumerate(labels, start=1):
        fetched = False
        try:
            if args.parse_only:
                archive = RAW / ("indices_data%s.zip" % label)
                if not archive.exists():
                    raise FileNotFoundError("archive not held")
            else:
                archive, fetched = download_month(label, force=args.force)
                if fetched:
                    time.sleep(args.sleep)
        except Exception as error:
            failures.append((label, "download: %s" % error))
            print("  %3d/%d  %-9s DOWNLOAD FAILED  %s"
                  % (index, len(labels), label, error), flush=True)
            continue
        try:
            pdf, origin = extract_pdf(archive, label)
            if pdf is None:
                raise ValueError(origin)
            report_date, records, rejected = parse_constituents(pdf_text(pdf))
        except Exception as error:
            failures.append((label, "parse: %s" % error))
            print("  %3d/%d  %-9s PARSE FAILED  %s"
                  % (index, len(labels), label, error), flush=True)
            continue

        count = len(records)
        ok = (EXPECTED_MIN <= count <= EXPECTED_MAX) and report_date is not None
        if not ok:
            failures.append((label, "count %d outside [%d,%d] or missing date"
                             % (count, EXPECTED_MIN, EXPECTED_MAX)))
        print("  %3d/%d  %-9s %s  %3d constituents%s"
              % (index, len(labels), label,
                 report_date.isoformat() if report_date else "NO-DATE",
                 count, "" if ok else "   <-- REJECTED"), flush=True)

        entry = {
            "label": label, "source_url": BASE % label,
            "retrieved_at": stamp if fetched else "held",
            "archive_sha256": sha256(archive), "pdf_sha256": sha256(pdf),
            "report_date": report_date.isoformat() if report_date else None,
            "original_filename": origin,
            "constituents": count, "rejected_tokens": rejected,
            "parser_version": PARSER_VERSION, "accepted": ok,
        }
        manifest.append(entry)
        if not ok:
            continue
        for record in records:
            rows.append({
                "report_date": report_date.isoformat(), "index": "NIFTY 100",
                "symbol": record["symbol"],
                "security_name": record["security_name"],
                "industry": record["industry"],
                "close_price": record["close_price"],
                "index_mcap_cr": record["index_mcap_cr"],
                "weight_pct": record["weight_pct"],
                "source_report": "nifty100_%s.pdf" % label,
                "source_sha256": entry["pdf_sha256"],
                "parser_version": PARSER_VERSION,
                "retrieved_at": entry["retrieved_at"],
            })

    if rows:
        with PIT_CSV.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    with MANIFEST.open("w", encoding="utf-8") as handle:
        for entry in manifest:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")

    accepted = [e for e in manifest if e["accepted"]]
    from collections import Counter
    spread = Counter(e["constituents"] for e in accepted)
    lines = [
        "NSE INDICES MONTHLY NIFTY 100 -- PARSER COVERAGE",
        "=" * 58,
        "Parser version      %s" % PARSER_VERSION,
        "Months requested    %d  (%s .. %s)" % (len(labels), labels[0], labels[-1]),
        "Reports retrieved   %d" % len(manifest),
        "Reports accepted    %d" % len(accepted),
        "Reports rejected    %d" % len(failures),
        "Constituent counts  %s" % ", ".join(
            "%d x%d" % (c, n) for c, n in sorted(spread.items())),
        "Rows written        %d" % len(rows),
        "",
    ]
    if failures:
        lines.append("REJECTED / FAILED:")
        lines += ["   %-9s %s" % (label, why) for label, why in failures]
    report = "\n".join(lines)
    (STORE / "parse_report.txt").write_text(report + "\n", encoding="utf-8")
    print()
    print(report)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
