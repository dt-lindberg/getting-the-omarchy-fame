"""Readers for the three inputs: base PR dumps, the earlier absorbed table and timeline records."""

import json
import logging
from collections.abc import Iterator

import pandas as pd

from funnel.constants import PR_RAW_FILES, PR_STATS, RAW_TIMELINES
from funnel.roles import normalise_login

LOG = logging.getLogger("funnel")


def load_timeline_nodes(limit: int | None = None) -> list[dict]:
    """Read the timeline JSONL, skipping PRs the API could not find.

    Args:
        limit: Optional cap on records read, for quick trials.

    How:
        Records without a node (not_found) are dropped with a warning.

    Returns:
        List of PR nodes, each the `node` of one JSONL record.
    """
    nodes = []
    with open(RAW_TIMELINES) as handle:
        for line in handle:
            record = json.loads(line)
            if record["node"] is None:
                LOG.warning("PR %s not found in timelines", record["number"])
                continue
            nodes.append(record["node"])
            if limit and len(nodes) >= limit:
                break
    return nodes


def iter_base_prs() -> Iterator[dict]:
    """Yield flat base records (current title/body, size, labels, first 100 files).

    How:
        Reads each raw JSONL file in PR_RAW_FILES order and keeps the first
        record per PR number, so earlier files win.

    Returns:
        An iterator of one flat dict per PR.
    """
    seen = set()
    for name in PR_RAW_FILES:
        with open(PR_STATS / name) as handle:
            for line in handle:
                raw = json.loads(line)
                if raw["number"] in seen:
                    continue
                seen.add(raw["number"])
                yield {
                    "number": raw["number"],
                    "title": raw["title"] or "",
                    "body": raw["body"] or "",
                    "additions": raw["additions"],
                    "deletions": raw["deletions"],
                    "changed_files": raw["changedFiles"],
                    "labels": [n["name"] for n in raw["labels"]["nodes"]],
                    "paths": [n["path"] for n in raw["files"]["nodes"]],
                    "files_total": raw["files"]["totalCount"],
                    "comments_total": raw["comments"]["totalCount"],
                    "reviews_total": raw["reviews"]["totalCount"],
                    "commits_total": raw["commits"]["totalCount"],
                    "created_at_raw": raw["createdAt"],
                    "closed_at_raw": raw["closedAt"],
                    "state_raw": raw["state"],
                    "review_authors": [normalise_login((n["author"] or {}).get("login"))
                                       for n in raw["reviews"]["nodes"]],
                }


def load_base_prs() -> pd.DataFrame:
    """Load the base PR table.

    How:
        Collects iter_base_prs into a DataFrame.

    Returns:
        DataFrame indexed by number.
    """
    return pd.DataFrame(iter_base_prs()).set_index("number")


def load_absorbed() -> pd.DataFrame:
    """Strict and loose absorbed flags from the earlier study's prs.csv.

    How:
        `absorbed` is the strict outcome; `absorbed_loose` is the weaker
        'landed in / superseded' wording and only feeds superseded_duplicate.

    Returns:
        DataFrame indexed by number with absorbed, absorbed_by, absorbed_via, absorbed_loose.
    """
    table = pd.read_csv(PR_STATS / "prs.csv",
                        usecols=["number", "outcome", "absorbed_by", "absorbed_via", "absorbed_loose"])
    table["absorbed"] = table["outcome"] == "absorbed"
    table["absorbed_loose"] = table["absorbed_loose"].astype(bool)
    table["absorbed_by"] = table["absorbed_by"].astype("Int64")
    return table.drop(columns="outcome").set_index("number")
