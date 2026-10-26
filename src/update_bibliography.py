#!/usr/bin/env python3
"""Applies verified bibliographic corrections to literature/peer_reviewed_papers.bib.

Each correction was checked against Crossref (DOI records) or the USENIX presentation
page metadata (USENIX papers, which Crossref does not index). Idempotent: rerunning it
leaves the file unchanged.
"""
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BIB_PATH = PROJECT_ROOT / "literature" / "peer_reviewed_papers.bib"
USENIX = "https://www.usenix.org/conference/"

# key -> fields to set (overwrite if present, append if absent)
CORRECTIONS = {
    "clopper1934use": {"doi": "10.1093/biomet/26.4.404", "pages": "404--413"},
    "welch1951comparison": {"doi": "10.2307/2332579", "pages": "330"},
    "hoerl1970ridge": {"doi": "10.1080/00401706.1970.10488634", "pages": "55--67"},
    "davison1990exceedances": {"doi": "10.1111/j.2517-6161.1990.tb01796.x", "pages": "393--425"},
    "georges2007java": {"doi": "10.1145/1297105.1297033", "pages": "57--76"},
    "mytkowicz2009wrong": {"doi": "10.1145/1508284.1508275", "pages": "265--276"},
    "jangda2019not": {"pages": "107--120", "url": USENIX + "atc19/presentation/jangda"},
    "narayan2020firefox": {"pages": "699--716", "url": USENIX + "usenixsecurity20/presentation/narayan"},
    "lehmann2020binary": {"pages": "217--234", "url": USENIX + "usenixsecurity20/presentation/lehmann"},
    "shillaker2020faasm": {"pages": "419--433", "url": USENIX + "atc20/presentation/shillaker"},
    "agache2020firecracker": {"pages": "419--434", "url": USENIX + "nsdi20/presentation/agache"},
    "yu2025resource": {"pages": "1111--1128", "url": USENIX + "usenixsecurity25/presentation/yu-zhaofeng"},
    "haas2017bringing": {"pages": "185--200", "doi": "10.1145/3062341.3062363"},
    "khan2026taxonomy": {"doi": "10.1109/access.2026.3733354", "pages": "146359--146379"},
    "kakati2025multiplatform": {"pages": "15--25", "doi": "10.5220/0013203200003950"},
}


def set_field(body: str, name: str, value: str) -> str:
    pattern = re.compile(rf"(\b{name}\s*=\s*)\{{[^}}]*\}}")
    if pattern.search(body):
        return pattern.sub(lambda m: f"{m.group(1)}{{{value}}}", body, count=1)
    return body.rstrip().rstrip(",") + f",\n  {name} = {{{value}}}" + "\n"


def apply(text: str) -> str:
    for key, fields in CORRECTIONS.items():
        match = re.search(rf"(@\w+\{{{key},)(.*?)(\n\}})", text, re.S)
        if match is None:
            raise KeyError(f"entry not found: {key}")
        body = match.group(2)
        for name, value in fields.items():
            body = set_field(body, name, value)
        text = text[:match.start(2)] + body + text[match.end(2):]
    return text


if __name__ == "__main__":
    BIB_PATH.write_text(apply(BIB_PATH.read_text()))
    print("corrections applied to", BIB_PATH)
