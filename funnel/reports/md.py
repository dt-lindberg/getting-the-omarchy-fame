"""Tiny markdown table writer (avoids a tabulate dependency)."""

import pandas as pd


def md_table(table: pd.DataFrame, index: bool = True, floatfmt: str = "{:.1f}") -> list[str]:
    """Render a DataFrame as markdown table lines.

    Args:
        table: Table to render.
        index: Include the index as the first column.
        floatfmt: Format for float cells.
    """
    frame = table.reset_index() if index else table
    header = "| " + " | ".join(str(c) for c in frame.columns) + " |"
    rule = "|" + "|".join("---" for _ in frame.columns) + "|"
    lines = [header, rule]
    for row in frame.itertuples(index=False):
        cells = [floatfmt.format(v) if isinstance(v, float) else str(v) for v in row]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return lines
