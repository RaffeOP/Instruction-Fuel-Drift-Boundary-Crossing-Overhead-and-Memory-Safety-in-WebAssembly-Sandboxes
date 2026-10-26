#!/usr/bin/env python3
"""Adds screened peer-reviewed references to literature/peer_reviewed_papers.bib from Crossref.

Each entry is built from the Crossref record for its DOI (authors, title, venue, year, pages,
DOI). Entries already present in the bibliography are skipped, so the script is idempotent.
"""
import json
import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BIB_PATH = PROJECT_ROOT / "literature" / "peer_reviewed_papers.bib"
CROSSREF = "https://api.crossref.org/works"
USER_AGENT = "r3-screened-references/1.0 (mailto:research@localhost)"
SCREENED_DOIS = [
    "10.1109/giis59465.2024.10449907",
    "10.1145/3700875",
    "10.1109/mic.2024.3513035",
    "10.1145/3759426.3760985",
    "10.1109/noms57970.2025.11073737",
    "10.1145/3760387",
    "10.1145/3736731.3746150",
    "10.1016/j.cosrev.2024.100655",
    "10.1007/s10845-025-02672-8",
]


def fetch(doi: str) -> dict:
    completed = subprocess.run(["curl", "-sS", "--fail", "-m", "30", "-A", USER_AGENT,
                                f"{CROSSREF}/{doi}"], capture_output=True, text=True, check=True)
    return json.loads(completed.stdout)["message"]


def latex(text: str) -> str:
    return text.replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")


def year_of(record: dict) -> str:
    for field in ("published-print", "published-online", "issued"):
        parts = record.get(field, {}).get("date-parts", [[None]])[0]
        if parts and parts[0]:
            return str(parts[0])
    raise ValueError(f"no year for {record.get('DOI')}")


def entry_key(record: dict, year: str) -> str:
    family = re.sub(r"[^a-z]", "", record["author"][0]["family"].lower())
    first_word = re.sub(r"[^a-z]", "", record["title"][0].split()[0].lower())
    return f"{family}{year}{first_word}"


def venue_field(record: dict) -> tuple:
    kind = record.get("type", "")
    container = (record.get("container-title") or [""])[0]
    if kind in ("proceedings-article", "journal-article") and container:
        return ("journal" if kind == "journal-article" else "booktitle"), container
    return ("booktitle", container or record.get("publisher", ""))


def build_entry(record: dict) -> str:
    year = year_of(record)
    authors = " and ".join(f"{a.get('family', '')}, {a.get('given', '')}".strip(", ") for a in record["author"])
    title = latex(record["title"][0])
    field_name, venue = venue_field(record)
    lines = [f"@{'article' if field_name == 'journal' else 'inproceedings'}{{{entry_key(record, year)},",
             f"  author = {{{authors}}},",
             f"  title = {{{title}}},",
             f"  {field_name} = {{{latex(venue)}}},"]
    if record.get("volume"):
        lines.append(f"  volume = {{{record['volume']}}},")
    if record.get("page"):
        lines.append(f"  pages = {{{record['page'].replace('-', '--')}}},")
    lines += [f"  year = {{{year}}},", f"  doi = {{{record['DOI']}}}", "}"]
    return "\n".join(lines)


def main() -> None:
    text = BIB_PATH.read_text()
    additions = []
    for doi in SCREENED_DOIS:
        if doi in text:
            continue
        additions.append(build_entry(fetch(doi)))
    if additions:
        BIB_PATH.write_text(text.rstrip() + "\n\n" + "\n\n".join(additions) + "\n")
    print(f"added {len(additions)} entries")


if __name__ == "__main__":
    main()
