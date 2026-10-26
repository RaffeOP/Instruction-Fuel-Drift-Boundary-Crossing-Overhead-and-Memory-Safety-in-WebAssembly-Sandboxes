#!/usr/bin/env python3
"""Checks each bibliography entry against Crossref metadata (title, year, pages, DOI).

Entries that carry a DOI are fetched by DOI. Entries without one are searched by title and
first author, and the best match is printed for manual confirmation. Output is a CSV report.
"""
import csv
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BIB_PATH = PROJECT_ROOT / "literature" / "peer_reviewed_papers.bib"
REPORT_PATH = PROJECT_ROOT / "results" / "metrics" / "bibliography_check.csv"
CROSSREF = "https://api.crossref.org/works"
USER_AGENT = "r3-bibliography-check/1.0 (mailto:research@localhost)"
REQUEST_TIMEOUT_SECONDS = 30


def parse_entries(text: str) -> list:
    entries = []
    for match in re.finditer(r"@(\w+)\{([^,]+),(.*?)\n\}", text, re.S):
        body = match.group(3)
        fields = dict(re.findall(r"(\w+)\s*=\s*\{(.*?)\},?\s*\n", body + "\n", re.S))
        entries.append({"key": match.group(2).strip(), "type": match.group(1), "fields": fields})
    return entries


def fetch_json(url: str) -> dict:
    """Fetches JSON through curl, which uses the system certificate store."""
    completed = subprocess.run(
        ["curl", "-sS", "--fail", "-m", str(REQUEST_TIMEOUT_SECONDS), "-A", USER_AGENT, url],
        capture_output=True, text=True, check=True,
    )
    return json.loads(completed.stdout)


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.replace("{", "").replace("}", "").lower()).strip()


def title_overlap(a: str, b: str) -> float:
    words_a, words_b = set(normalize(a).split()), set(normalize(b).split())
    return len(words_a & words_b) / max(1, len(words_a))


def crossref_by_doi(doi: str) -> dict:
    return fetch_json(f"{CROSSREF}/{urllib.parse.quote(doi)}")["message"]


def crossref_by_title(title: str, author: str) -> dict | None:
    query = urllib.parse.urlencode({"query.bibliographic": f"{title} {author}", "rows": 1})
    items = fetch_json(f"{CROSSREF}?{query}")["message"]["items"]
    return items[0] if items else None


def record_row(entry: dict, record: dict | None, source: str) -> dict:
    title = (record or {}).get("title", [""])[0]
    year = ""
    for field in ("published-print", "published-online", "issued"):
        parts = (record or {}).get(field, {}).get("date-parts", [[None]])[0]
        if parts and parts[0]:
            year = str(parts[0])
            break
    return {
        "key": entry["key"],
        "source": source,
        "doi": (record or {}).get("DOI", ""),
        "crossref_title": title,
        "crossref_year": year,
        "crossref_pages": (record or {}).get("page", ""),
        "title_overlap": f"{title_overlap(entry['fields'].get('title', ''), title):.2f}" if record else "0.00",
        "bib_year": entry["fields"].get("year", ""),
        "bib_pages": entry["fields"].get("pages", ""),
        "bib_doi": entry["fields"].get("doi", ""),
    }


def check_entry(entry: dict) -> dict:
    doi = entry["fields"].get("doi", "").strip()
    if doi:
        return record_row(entry, crossref_by_doi(doi), "doi")
    author_field = entry["fields"].get("author", "")
    first_author = author_field.split(" and ")[0].split(",")[0]
    return record_row(entry, crossref_by_title(entry["fields"].get("title", ""), first_author), "search")


def main() -> int:
    entries = parse_entries(BIB_PATH.read_text())
    rows = []
    for entry in entries:
        try:
            rows.append(check_entry(entry))
        except (OSError, KeyError, ValueError) as error:
            rows.append(record_row(entry, None, f"error: {error}"))
        print(entry["key"], rows[-1]["source"], rows[-1]["title_overlap"], rows[-1]["doi"] or "-", file=sys.stderr)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REPORT_PATH.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
