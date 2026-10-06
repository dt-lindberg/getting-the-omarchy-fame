"""Assemble the published page: template + analysis results inlined as JSON."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
RESULTS = ROOT / "data" / "results"


def load(name: str) -> dict:
    path = RESULTS / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else {}


def main() -> None:
    data = {
        "dots": json.loads((SITE / "dots.json").read_text()),
        "attention": load("attention"),
        "feedback": load("feedback"),
        "context": load("context"),
        "page": load("page"),
        "analysis": load("analysis"),
    }
    # Escape "</" so inlined JSON can never close the script element early.
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    template = (SITE / "page.template.html").read_text()
    html = template.replace("/*__DATA__*/{}", blob)
    out = SITE / "omarchy-triage.html"
    out.write_text(html)
    print(f"{out} {out.stat().st_size // 1024} KiB")
    # GitHub Pages serves docs/ as-is, so that copy gets its own document skeleton.
    pages = ROOT / "docs" / "index.html"
    pages.parent.mkdir(exist_ok=True)
    head = ('<!doctype html>\n<html lang="en-GB">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '<meta name="description" content="How 6,336 community pull requests to Omarchy were triaged, and what gets them merged.">\n')
    title_end = html.index("</title>") + len("</title>")
    pages.write_text(head + html[:title_end] + "\n" + "</head>\n<body>\n" + html[title_end:] + "\n</body>\n</html>\n")
    print(f"{pages} {pages.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()
