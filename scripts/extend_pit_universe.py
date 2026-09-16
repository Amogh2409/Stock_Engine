#!/usr/bin/env python3
"""Extend PIT Nifty 100 membership past 2022-03 from NIFTY 50 + NIFTY Next 50.

The monthly archive stopped carrying a standalone Nifty 100 report after March
2022, but it still carries both sub-indices, and NSE's methodology defines the
Nifty 100 as their combined portfolio.

That identity was VALIDATED, not assumed: across all 87 months where all three
reports exist, the union reproduces Nifty 100 COMPANY membership exactly, 87 of
87. Security-level agreement is 54 of 87, and every one of the 33 differences is
the same single security -- TATAMTRDVR, the Tata Motors DVR class, which sits in
the Nifty 100 but in neither sub-index. Nothing ever appears in the union that
is absent from the Nifty 100.

So the deterministic rule is: the union reproduces the index at COMPANY level,
and omits alternate share classes. Records produced here are marked
OFFICIAL_COMPOSITE_RECONSTRUCTION rather than passed off as a standalone report.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from nse_index_history import months_between, FIRST, LAST, parse_constituents  # noqa: E402
from validate_union_identity import read_index  # noqa: E402

RAW = ROOT / "data-store" / "universe" / "raw"
OUT = ROOT / "data-store" / "universe" / "pit_nifty100_extended.csv"
MANIFEST = ROOT / "data-store" / "universe" / "extension_manifest.jsonl"
METHOD_VERSION = "union-v1.0.0"


def main():
    base = list(csv.DictReader(
        (ROOT / "data-store" / "universe" / "pit_nifty100.csv").open(encoding="utf-8")))
    for row in base:
        row["source_type"] = "OFFICIAL_STANDALONE_NIFTY100"
        row["reconstruction_method"] = ""
    have = {r["report_date"] for r in base}

    rows, manifest = list(base), []
    for label in months_between(FIRST, LAST):
        archive = RAW / ("indices_data%s.zip" % label)
        if not archive.exists():
            continue
        # Only months the standalone report does not already cover.
        fifty = read_index(archive, "nifty50")
        nxt = read_index(archive, "next50")
        if fifty is None or nxt is None:
            continue
        combined = {r["symbol"]: r for r in (fifty[1] + nxt[1])}
        # The report date comes from the sub-index reports themselves.
        import subprocess, re
        probe = ROOT / "data-store" / "universe" / ".probe" / "probe.pdf"
        date = None
        with zipfile.ZipFile(archive) as bundle:
            for name in sorted(bundle.namelist()):
                if not name.lower().endswith(".pdf"):
                    continue
                probe.parent.mkdir(parents=True, exist_ok=True)
                probe.write_bytes(bundle.read(name))
                text = subprocess.run(["pdftotext", "-raw", str(probe), "-"],
                                      capture_output=True, text=True).stdout
                found, _recs, _rej = parse_constituents(text)
                if found:
                    date = found.isoformat()
                    break
        if date is None or date in have:
            continue
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        for symbol, record in sorted(combined.items()):
            rows.append({
                "report_date": date, "index": "NIFTY 100",
                "symbol": symbol, "security_name": record["security_name"],
                "industry": record["industry"], "close_price": record["close_price"],
                "index_mcap_cr": record["index_mcap_cr"],
                "weight_pct": record["weight_pct"],
                "source_report": "indices_data%s.zip (NIFTY 50 + NIFTY Next 50)" % label,
                "source_sha256": digest, "parser_version": METHOD_VERSION,
                "retrieved_at": "held",
                "source_type": "OFFICIAL_COMPOSITE_RECONSTRUCTION",
                "reconstruction_method":
                    "union(NIFTY 50, NIFTY Next 50); company-level exact on 87/87 "
                    "validation months; omits alternate share classes",
            })
        manifest.append({"label": label, "report_date": date,
                         "constituents": len(combined),
                         "archive_sha256": digest,
                         "method": METHOD_VERSION,
                         "source_type": "OFFICIAL_COMPOSITE_RECONSTRUCTION"})
        print("  %-9s %s  %3d constituents (reconstructed)"
              % (label, date, len(combined)), flush=True)

    rows.sort(key=lambda r: (r["report_date"], r["symbol"]))
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with MANIFEST.open("w", encoding="utf-8") as handle:
        for entry in manifest:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    dates = sorted({r["report_date"] for r in rows})
    standalone = sorted({r["report_date"] for r in rows
                         if r["source_type"] == "OFFICIAL_STANDALONE_NIFTY100"})
    print("\nextended store: %d rows, %d monthly dates, %s .. %s"
          % (len(rows), len(dates), dates[0], dates[-1]))
    print("  standalone official reports    %d  (%s .. %s)"
          % (len(standalone), standalone[0], standalone[-1]))
    print("  composite reconstructions      %d" % (len(dates) - len(standalone)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
