"""Join topic/kind labels onto prs.parquet. Separate step so it can be re-run as labels change."""

from pathlib import Path

import pandas as pd

from funnel.constants import DERIVED, TOPICS_FILE

LABEL_COLUMNS = ["topic", "kind", "topic_confidence"]


def load_topic_labels() -> pd.DataFrame:
    """Read the final topic table (data/labels/topics.parquet).

    How:
        The file supersedes the earlier JSONL batches; its `confidence` column is
        renamed to `topic_confidence`. A missing file gives an empty table so the
        join leaves the columns null.

    Returns:
        DataFrame indexed by number with topic, kind, topic_confidence.
    """
    if not TOPICS_FILE.exists():
        return pd.DataFrame(columns=LABEL_COLUMNS, index=pd.Index([], name="number"))
    table = pd.read_parquet(TOPICS_FILE).rename(columns={"confidence": "topic_confidence"})
    return table.drop_duplicates("number", keep="last").set_index("number")[LABEL_COLUMNS]


def join_topics(out_dir: Path = DERIVED) -> int:
    """Replace the topic columns of prs.parquet with the current labels.

    Args:
        out_dir: Directory holding prs.parquet.

    How:
        Drops existing label columns first so the step is idempotent.

    Returns:
        Number of PRs that now have a topic.
    """
    path = out_dir / "prs.parquet"
    prs = pd.read_parquet(path).drop(columns=LABEL_COLUMNS, errors="ignore")
    prs = prs.join(load_topic_labels(), on="number")
    prs.to_parquet(path, index=False)
    return int(prs["topic"].notna().sum())
