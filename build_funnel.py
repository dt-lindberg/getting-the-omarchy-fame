"""Build the funnel tables: events, prs, snapshots, close samples and the summary.

Run `uv run python build_funnel.py` once the timeline fetch is complete (>= 6,950 lines). `--partial` builds on whatever is fetched into data/derived/partial/.
Stages: `tables` (events/prs/snapshots), `topics` (join topic labels, re-runnable), `reports`.
"""

import argparse
import logging
from pathlib import Path

import pandas as pd

from funnel.assemble import build_tables
from funnel.constants import DERIVED, EXPECTED_PRS, RAW_TIMELINES
from funnel.events import build_events
from funnel.load import load_absorbed, load_base_prs, load_timeline_nodes
from funnel.topics import join_topics

LOG = logging.getLogger("funnel")


def fetch_is_done() -> bool:
    """True when the timelines file has all PRs (the README is optional)."""
    with open(RAW_TIMELINES, "rb") as handle:
        return sum(1 for _ in handle) >= EXPECTED_PRS


def run_tables(out_dir: Path, limit: int | None) -> None:
    """Build and write events, prs and snapshots parquet files."""
    nodes = load_timeline_nodes(limit)
    LOG.info("loaded %d timeline nodes", len(nodes))
    events = build_events(nodes)
    prs, snapshots = build_tables(nodes, events, load_base_prs(), load_absorbed())
    events.to_parquet(out_dir / "events.parquet", index=False)
    prs.to_parquet(out_dir / "prs.parquet", index=False)
    snapshots.to_parquet(out_dir / "snapshots.parquet", index=False)
    LOG.info("events %s, prs %s, snapshots %s", events.shape, prs.shape, snapshots.shape)


def run_reports(out_dir: Path) -> None:
    """Write close_samples.md and funnel_summary.md from the written tables."""
    from funnel.reports import write_reports
    write_reports(out_dir, pd.read_parquet(out_dir / "prs.parquet"), pd.read_parquet(out_dir / "events.parquet"),
                  pd.read_parquet(out_dir / "snapshots.parquet"))


def main() -> None:
    """Parse options and run the requested stages."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["all", "tables", "topics", "reports"], default="all")
    parser.add_argument("--partial", action="store_true", help="allow an unfinished fetch; writes to data/derived/partial")
    parser.add_argument("--limit", type=int, default=None, help="read only this many timeline records")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if args.stage in ("all", "tables") and not args.partial and not fetch_is_done():
        raise SystemExit("Timeline fetch is not finished; wait for it or pass --partial.")
    out_dir = DERIVED / "partial" if args.partial else DERIVED
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.stage in ("all", "tables"):
        run_tables(out_dir, args.limit)
    if args.stage in ("all", "tables", "topics"):
        LOG.info("%d PRs have topic labels", join_topics(out_dir))
    if args.stage in ("all", "tables", "reports"):
        run_reports(out_dir)


if __name__ == "__main__":
    main()
