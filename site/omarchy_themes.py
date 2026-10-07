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
MIN_CONTRAST = 4.5


def _rgb(hex_colour: str) -> list[int]:
    h = hex_colour.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _luminance(hex_colour: str) -> float:
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (x / 255 for x in _rgb(hex_colour))]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two hex colours."""
    lo, hi = sorted((_luminance(a), _luminance(b)))
    return (hi + 0.05) / (lo + 0.05)


def _mix(a: str, b: str, share_a: float) -> str:
    return "#" + "".join(f"{round(x * share_a + y * (1 - share_a)):02x}" for x, y in zip(_rgb(a), _rgb(b)))


def readable(colour: str, ink: str, grounds: list[str]) -> str:
    """Move colour towards ink until it reads at MIN_CONTRAST on every ground.

    Some themes' muted text colours sit too close to their backgrounds (White's
    equals its bar), so the page can't use them as they are.
    """
    for step in range(21):
        out = _mix(ink, colour, step / 20)
        if all(contrast(out, g) >= MIN_CONTRAST for g in grounds):
            return out
    return ink


def main() -> None:
    """Write one record per theme: name, light or dark, and the colours the page uses."""
    themes = []
    for path in sorted(SOURCE.glob("*/colors.toml")):
        c = tomllib.loads(path.read_text())
        slug = path.parent.name
        grounds = [c["background"], c["lighter_background"]]
        muted = _mix(c["foreground"], c["background"], 0.55)
        themes.append({
            "id": slug,
            "name": NAMES.get(slug, slug.replace("-", " ").title()),
            "mode": c["mode"],
            "bg": c["background"],
            "bar": c["lighter_background"],
            "ink": c["foreground"],
            "ink2": readable(c["light_foreground"], c["foreground"], grounds),
            "ink3": readable(muted, c["foreground"], grounds),
            "accent": c["accent"],
            "on_accent": max(("#000000", "#ffffff"), key=lambda x: contrast(x, c["accent"])),
            "swatch": [c[k] for k in ("red", "yellow", "green", "blue", "magenta")],
        })
    OUT.write_text(json.dumps(themes, indent=1) + "\n")
    print(f"{OUT.relative_to(ROOT)} {len(themes)} themes")


if __name__ == "__main__":
    main()
