"""Reading PR numbers and the resumable JSONL output file.

Exists so the loop can skip finished PRs and survive a crash mid-write.
"""

import json
from pathlib import Path

from funnel.constants import PR_RAW_FILES as PR_FILES
from funnel.constants import PR_STATS as PR_STATS_RAW


def load_pr_numbers() -> list[int]:
    """Collect every PR number from the earlier pull.

    How:
        Reads only the `number` field of each line across the PR files and
        de-duplicates (prs_user overlaps the others).

    Returns:
        Sorted PR numbers, ascending.
    """
    numbers: set[int] = set()
    for name in PR_FILES:
        with open(PR_STATS_RAW / name) as handle:
            numbers.update(json.loads(line)["number"] for line in handle if line.strip())
    return sorted(numbers)


def load_done(path: Path) -> set[int]:
    """Read the numbers already written, repairing a half-written last line.

    Args:
        path: The output JSONL file (may not exist yet).

    How:
        Parses each line's number; if the final line is cut off by a crash,
        truncates the file just before it so the PR is fetched again.

    Returns:
        Set of PR numbers present in the file.
    """
    done: set[int] = set()
    if not path.exists():
        return done
    good_bytes = 0
    with open(path, "rb") as handle:
        for raw in handle:
            try:
                done.add(json.loads(raw)["number"])
            except (json.JSONDecodeError, KeyError):
                break
            good_bytes += len(raw)
    if good_bytes < path.stat().st_size:
        with open(path, "r+b") as handle:
            handle.truncate(good_bytes)
    return done


def append_records(path: Path, records: list[dict]) -> None:
    """Append records as JSONL lines and flush to disk.

    Args:
        path: The output JSONL file.
        records: Records to write.

    How:
        One write per batch; each line is complete JSON ending in a newline.
    """
    with open(path, "a") as handle:
        handle.write("".join(json.dumps(record, separators=(",", ":")) + "\n" for record in records))
        handle.flush()
