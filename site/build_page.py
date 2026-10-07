"""Assemble the published page: the template with page.json, dots.json and the Omarchy themes inlined.

Writes docs/index.html, which GitHub Pages serves as the site's front page.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results"
TEMPLATE = ROOT / "site" / "page.template.html"
THEMES = ROOT / "site" / "themes.json"
OUT = ROOT / "docs" / "index.html"
PLACEHOLDER = "/*__DATA__*/{}"
THEME_CSS = "/*__THEME_CSS__*/"
THEME_LIST = "/*__THEME_LIST__*/[]"


def theme_css(themes: list[dict]) -> str:
    """One CSS rule per Omarchy theme, setting the colour tokens the page reads."""
    rules = []
    for t in themes:
        tokens = {"--bg": t["bg"], "--bar": t["bar"], "--ink": t["ink"], "--ink-2": t["ink2"],
                  "--ink-3": t["ink3"], "--accent": t["accent"]}
        body = " ".join(f"{k}: {v};" for k, v in tokens.items())
        rules.append(f':root[data-theme="{t["id"]}"] {{ {body} }}')
    return "\n".join(rules)


def main() -> None:
    """Inline the page data into the template and write docs/index.html.

    How:
        Escapes "</" in the JSON so the inlined data can never close the
        script element early.
    """
    data = {name: json.loads((RESULTS / f"{name}.json").read_text()) for name in ("page", "dots")}
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    themes = json.loads(THEMES.read_text())
    listing = [{k: t[k] for k in ("id", "name", "mode", "bg", "ink", "accent", "swatch")} for t in themes]
    page = (TEMPLATE.read_text()
            .replace(THEME_CSS, theme_css(themes))
            .replace(THEME_LIST, json.dumps(listing, separators=(",", ":"), ensure_ascii=False))
            .replace(PLACEHOLDER, blob))
    OUT.write_text(page)
    print(f"{OUT.relative_to(ROOT)} {OUT.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()
