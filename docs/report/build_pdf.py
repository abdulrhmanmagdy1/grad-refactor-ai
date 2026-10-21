"""Render docs/report/report.md to docs/report/report.pdf.

Run from the repository root on Windows with Microsoft Edge (or set BROWSER to a Chrome or
Edge executable); the markdown package is not part of the locked environment:

    uv run --no-project --with markdown==3.7 python docs/report/build_pdf.py

Links to repository files become links to the file on GitHub, images are embedded, and the
browser prints the page with page numbers.
"""

from __future__ import annotations

import base64
import os
import re
import subprocess
import tempfile
from pathlib import Path

import markdown

REPORT = Path(__file__).with_name("report.md")
OUT = Path(__file__).with_name("report.pdf")
ROOT = Path(__file__).resolve().parents[2]
GITHUB = "https://github.com/abdulrhmanmagdy1/grad-refactor-ai/blob/main/"
BROWSERS = [
    os.environ.get("BROWSER", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]
IMAGE_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg"}

CSS = """
@page {
  size: A4;
  margin: 22mm 20mm 22mm 20mm;
  @bottom-center { content: counter(page); font: 9pt Calibri, sans-serif; color: #555; }
}
body { font: 11pt/1.5 Cambria, Georgia, serif; color: #111; }
h1 { font: 700 24pt Calibri, sans-serif; color: #1e2a78; margin: 0 0 8mm; }
h2 { font: 700 17pt Calibri, sans-serif; color: #1e2a78; break-before: page; margin-top: 0; }
h3 { font: 700 13pt Calibri, sans-serif; color: #1e2a78; margin: 7mm 0 2mm; break-after: avoid; }
h4 { font: 700 11.5pt Calibri, sans-serif; margin: 5mm 0 2mm; break-after: avoid; }
p, li { text-align: justify; hyphens: auto; }
a { color: #1f4fbf; text-decoration: none; }
code { font: 9.5pt Consolas, monospace; background: #f3f4f7; padding: 0 2px; }
pre { background: #f3f4f7; padding: 3mm; white-space: pre-wrap; break-inside: avoid; }
pre code { padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 3mm 0; font: 9pt/1.35 Calibri, sans-serif;
        break-inside: auto; }
tr { break-inside: avoid; }
th { background: #1e2a78; color: #fff; text-align: left; }
th, td { border: 0.5pt solid #c9cdd6; padding: 1.2mm 1.8mm; vertical-align: top; }
td { text-align: left; }
tbody tr:nth-child(even) td { background: #f5f7fb; }
img { display: block; max-width: 100%; max-height: 190mm; margin: 4mm auto; }
em { color: #333; }
.cover { break-after: page; }
"""


def repository_link(target: str) -> str:
    """Resolve a link relative to docs/report/ into a GitHub URL, keeping any anchor."""
    path, _, anchor = target.partition("#")
    resolved = (REPORT.parent / path).resolve()
    try:
        relative = resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return target
    url = GITHUB + relative
    return f"{url}#{anchor}" if anchor else url


def embed_image(target: str) -> str:
    """Embed an image of the repository; anything else stops the build."""
    path = (REPORT.parent / target).resolve()
    suffix = path.suffix.lower()
    if not path.is_relative_to(ROOT) or suffix not in IMAGE_TYPES or not path.is_file():
        raise SystemExit(f"Refusing image outside the repository or of another type: {target}")
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{IMAGE_TYPES[suffix]};base64,{data}"


def rewrite_links(text: str) -> str:
    def image(match: re.Match) -> str:
        return f"![{match.group(1)}]({embed_image(match.group(2))})"

    def link(match: re.Match) -> str:
        label, target = match.group(1), match.group(2)
        if re.match(r"^(https?:|mailto:|#)", target):
            return match.group(0)
        return f"[{label}]({repository_link(target)})"

    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", image, text)
    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)", link, text)


def to_html(text: str) -> str:
    body = markdown.markdown(
        rewrite_links(text),
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        output_format="html",
    )
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>Graduation project report</title><style>{CSS}</style></head>"
        f"<body>{body}</body></html>"
    )


def browser() -> str:
    for candidate in BROWSERS:
        if candidate and Path(candidate).exists():
            return candidate
    raise SystemExit("No Edge or Chrome executable found; set BROWSER to one.")


def main() -> None:
    html = to_html(REPORT.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "report.html"
        page.write_text(html, encoding="utf-8")
        subprocess.run(
            [
                browser(),
                "--headless=new",
                "--disable-gpu",
                f"--user-data-dir={Path(tmp) / 'profile'}",
                "--no-pdf-header-footer",
                f"--print-to-pdf={OUT}",
                page.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
    print(f"{OUT.relative_to(ROOT).as_posix()}: {OUT.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
