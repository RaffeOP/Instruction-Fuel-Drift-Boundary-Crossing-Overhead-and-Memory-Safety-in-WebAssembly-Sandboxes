#!/usr/bin/env python3
"""Fetches Crossref abstracts for bibliography entries that carry a DOI, for claim checking."""
import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = PROJECT_ROOT / "results" / "metrics" / "bibliography_check.csv"
OUT_PATH = PROJECT_ROOT / "literature" / "abstracts_crossref.md"
CROSSREF = "https://api.crossref.org/works"
USER_AGENT = "r3-abstract-fetch/1.0 (mailto:research@localhost)"
TAG_PATTERN = re.compile(r"<[^>]+>")


def fetch(doi: str) -> dict:
    completed = subprocess.run(["curl", "-sS", "--fail", "-m", "30", "-A", USER_AGENT,
                                f"{CROSSREF}/{doi}"], capture_output=True, text=True, check=True)
    return json.loads(completed.stdout)["message"]


def main() -> int:
    import csv
    with REPORT_PATH.open() as handle:
        rows = list(csv.DictReader(handle))
    lines = ["# Crossref abstracts for verified entries", ""]
    missing = []
    for row in rows:
        doi = row["doi"]
        if not doi or row["title_overlap"] in ("", "0.00"):
            continue
        record = fetch(doi)
        abstract = TAG_PATTERN.sub("", record.get("abstract", "")).strip()
        lines.append(f"## {row['key']}")
        lines.append(f"DOI: {doi}")
        lines.append(f"Title: {record.get('title', [''])[0]}")
        lines.append("")
        lines.append(abstract if abstract else "[no abstract in Crossref]")
        lines.append("")
        if not abstract:
            missing.append(row["key"])
    OUT_PATH.write_text("\n".join(lines))
    print("entries without Crossref abstract:", missing, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
