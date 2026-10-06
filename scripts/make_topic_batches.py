"""Split all community PRs into ~250-PR batch files for the topic classifier."""
import json
import math
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "data" / "raw" / "base" / "community_for_topics.jsonl"
OUT = Path(__file__).resolve().parents[1] / "data/labels/topic_batches"
TARGET = 250
BODY_MAX_CHARS = 600


def collapse(text, limit=None):
    """Flatten text to a single line of single-spaced words.

    Args:
        text: Raw title or body; None becomes an empty string.
        limit: Maximum characters to keep, or None for no cut.

    How:
        Splits on any whitespace and rejoins with single spaces, then truncates.

    Returns:
        The collapsed, optionally truncated text.
    """
    text = " ".join(str(text or "").split())
    return text[:limit] if limit else text


def main() -> None:
    """Write data/labels/topic_batches/batch_NN.jsonl from the community PR export.

    How:
        Sorts PRs by number, splits them into equal batches of about TARGET,
        and replaces any batch files from an earlier run.
    """
    rows = [json.loads(line) for line in SRC.open()]
    rows.sort(key=lambda row: row["number"])
    n_batches = math.ceil(len(rows) / TARGET)
    size = math.ceil(len(rows) / n_batches)
    for old in OUT.glob("batch_*.jsonl"):
        old.unlink()
    for batch_index in range(n_batches):
        chunk = rows[batch_index * size:(batch_index + 1) * size]
        with (OUT / f"batch_{batch_index + 1:02d}.jsonl").open("w") as handle:
            for row in chunk:
                record = {"number": row["number"], "title": collapse(row["title"]),
                          "body": collapse(row["body"], BODY_MAX_CHARS)}
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"{len(rows)} PRs, {n_batches} batches of {size} (last {len(rows) - size * (n_batches - 1)})")


if __name__ == "__main__":
    main()
