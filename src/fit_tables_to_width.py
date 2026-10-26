"""Wrap generated tabular environments so they shrink to the text width.

Longtable environments are left alone because adjustbox cannot split them across pages.
Run after any generator that writes tables/*.tex.
"""

from pathlib import Path

TABLE_DIR = Path(__file__).resolve().parent.parent / "tables"
WRAP_OPEN = "\\begin{adjustbox}{max width=\\textwidth}%\n"
WRAP_CLOSE = "%\n\\end{adjustbox}"


def fit_file(path):
    text = path.read_text()
    if "\\begin{longtable}" in text or "\\begin{tabular}" not in text or "adjustbox" in text:
        return False
    text = text.replace("\\begin{tabular}", WRAP_OPEN + "\\begin{tabular}", 1)
    text = text.replace("\\end{tabular}", "\\end{tabular}" + WRAP_CLOSE, 1)
    text = text.replace("\\begin{table*}", "\\begin{table}").replace("\\end{table*}", "\\end{table}")
    path.write_text(text)
    return True


def fit_all():
    return [path.name for path in sorted(TABLE_DIR.glob("tab*.tex")) if fit_file(path)]


if __name__ == "__main__":
    print("wrapped:", fit_all())
