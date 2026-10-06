"""close_samples.md: ten examples per disposition so a human can check the rules."""

from pathlib import Path

import pandas as pd

from funnel.constants import SAMPLE_SEED

SAMPLES_PER_DISPOSITION = 10
EXCERPT = 220
TITLE_EXCERPT = 80


def _clean(text: object, limit: int) -> str:
    """Shorten text to a one-line, pipe-safe excerpt.

    Args:
        text: Raw text; None or empty gives an empty string.
        limit: Maximum characters to keep.

    How:
        Collapses whitespace, truncates, then escapes pipes so table cells stay intact.

    Returns:
        The excerpt.
    """
    return " ".join(str(text or "").split())[:limit].replace("|", "\\|")


def write_close_samples(path: Path, prs: pd.DataFrame) -> None:
    """Write random examples (fixed seed) per disposition with the closing comment.

    Args:
        path: Output markdown file.
        prs: PR table with disposition, title, closed_by, closing_comment.

    How:
        Samples across all authors; mass-close and ambiguous flags are shown so
        uncertain rules are visible.
    """
    lines = ["# Close samples", "",
             f"Up to {SAMPLES_PER_DISPOSITION} random PRs per disposition (seed {SAMPLE_SEED}). "
             "Columns: number, epoch, author, closed by, flags, title, closing comment excerpt "
             "(maintainer/bot comment within one hour of the close).", ""]
    for name, group in prs.groupby("disposition"):
        lines += [f"## {name} ({len(group)} PRs)", "",
                  "| # | epoch | author | closed by | flags | title | closing comment |", "|---|---|---|---|---|---|---|"]
        for row in group.sample(min(SAMPLES_PER_DISPOSITION, len(group)), random_state=SAMPLE_SEED).itertuples():
            flags = ",".join(flag for flag, on in [("ambiguous", row.ambiguous_close), ("mass_day", row.mass_close_day),
                                             ("silent", row.silent_no_comment)] if on)
            lines.append(f"| {row.number} | {row.epoch} | {row.author} | {row.closed_by or ''} | {flags} | "
                         f"{_clean(row.title, TITLE_EXCERPT)} | {_clean(row.closing_comment, EXCERPT)} |")
        lines.append("")
    path.write_text("\n".join(lines))
