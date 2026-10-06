"""Assemble the published page: the template with page.json and dots.json inlined.

Writes docs/index.html, which GitHub Pages serves as the site's front page.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results"
TEMPLATE = ROOT / "site" / "page.template.html"
OUT = ROOT / "docs" / "index.html"
PLACEHOLDER = "/*__DATA__*/{}"


def main() -> None:
    """Inline the page data into the template and write docs/index.html.

    How:
        Escapes "</" in the JSON so the inlined data can never close the
        script element early.
    """
    data = {name: json.loads((RESULTS / f"{name}.json").read_text()) for name in ("page", "dots")}
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.read_text().replace(PLACEHOLDER, blob))
    print(f"{OUT.relative_to(ROOT)} {OUT.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()
