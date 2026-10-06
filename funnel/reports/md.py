"""Tiny markdown table writer (avoids a tabulate dependency)."""

import pandas as pd


def md_table(table: pd.DataFrame, index: bool = True, floatfmt: str = "{:.1f}") -> list[str]:
    """Render a DataFrame as markdown table lines.

    Args:
        table: Table to render.
        index: Include the index as the first column.
        floatfmt: Format for float cells.

    How:
        Writes a header and separator row, then one row per record; pipes in
        cells are escaped so they cannot split a column.

    Returns:
        The table's lines, without trailing newlines.
    """
    frame = table.reset_index() if index else table
    header = "| " + " | ".join(str(column) for column in frame.columns) + " |"
    rule = "|" + "|".join("---" for _ in frame.columns) + "|"
    lines = [header, rule]
    for row in frame.itertuples(index=False):
        cells = [floatfmt.format(value) if isinstance(value, float) else str(value) for value in row]
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    return lines
