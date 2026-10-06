"""Markdown reports written next to the tables: close samples, funnel summary, spot checks."""

from pathlib import Path

import pandas as pd

from funnel.reports.samples import write_close_samples
from funnel.reports.summary import write_summary


def write_reports(out_dir: Path, prs: pd.DataFrame, events: pd.DataFrame, snapshots: pd.DataFrame) -> None:
    """Write close_samples.md and funnel_summary.md into out_dir.

    Args:
        out_dir: Destination directory.
        prs: PR table.
        events: Events table.
        snapshots: Snapshots table.
    """
    write_close_samples(out_dir / "close_samples.md", prs)
    write_summary(out_dir / "funnel_summary.md", prs, events, snapshots)
