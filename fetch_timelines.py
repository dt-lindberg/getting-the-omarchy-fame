"""Command-line entry: fetch timelines for every PR into data/raw/timelines.jsonl.

Resumable: PRs already in the output file are skipped. Run in the background:
    uv run python fetch_timelines.py >> data/raw/fetch.log 2>&1 &
"""

import argparse
import logging
import time
from pathlib import Path

from timelines.client import GitHubClient
from timelines.fetch import fetch_records
from timelines.store import append_records, load_done, load_pr_numbers

OUTPUT = Path(__file__).parent / "data" / "raw" / "timelines.jsonl"
DEFAULT_BATCH_SIZE = 15


def parse_args() -> argparse.Namespace:
    """Read command-line options.

    How:
        Batch size and an optional cap on PRs, for trial runs.

    Returns:
        Parsed namespace.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--limit", type=int, default=None, help="stop after this many PRs")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    return parser.parse_args()


def main() -> None:
    """Fetch all pending PRs, newest first, in batches.

    How:
        Newest first so a time-limited run covers the current regime; writes
        each batch immediately so progress survives any interruption.
    """
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("timelines")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    done = load_done(args.output)
    pending = [n for n in reversed(load_pr_numbers()) if n not in done]
    if args.limit:
        pending = pending[: args.limit]
    log.info("%d done, %d pending", len(done), len(pending))
    client = GitHubClient()
    started = time.time()
    for start in range(0, len(pending), args.batch_size):
        batch = pending[start : start + args.batch_size]
        append_records(args.output, fetch_records(client, batch))
        finished = start + len(batch)
        log.info("%d/%d fetched; points spent %d, remaining %s; %.0fs elapsed",
                 finished, len(pending), client.points_spent, client.remaining,
                 time.time() - started)
    log.info("finished")


if __name__ == "__main__":
    main()
