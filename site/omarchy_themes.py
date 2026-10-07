"""Collect the colours of every installed Omarchy theme into site/themes.json.

The page offers each theme as a choice; build_page.py turns this file into CSS.
Reads OMARCHY_THEMES, default /usr/share/omarchy/themes.
"""
import json
import os
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(os.environ.get("OMARCHY_THEMES", "/usr/share/omarchy/themes"))
OUT = ROOT / "site" / "themes.json"
NAMES = {"rose-pine": "Rosé Pine", "retro-82": "Retro-82"}


def main() -> None:
    """Write one record per theme: name, light or dark, and the colours the page uses."""
    themes = []
    for path in sorted(SOURCE.glob("*/colors.toml")):
        c = tomllib.loads(path.read_text())
        slug = path.parent.name
        themes.append({
            "id": slug,
            "name": NAMES.get(slug, slug.replace("-", " ").title()),
            "mode": c["mode"],
            "bg": c["background"],
            "bar": c["lighter_background"],
            "ink": c["foreground"],
            "ink2": c["light_foreground"],
            "ink3": c["dark_foreground"],
            "accent": c["accent"],
            "swatch": [c[k] for k in ("red", "yellow", "green", "blue", "magenta")],
        })
    OUT.write_text(json.dumps(themes, indent=1) + "\n")
    print(f"{OUT.relative_to(ROOT)} {len(themes)} themes")


if __name__ == "__main__":
    main()
