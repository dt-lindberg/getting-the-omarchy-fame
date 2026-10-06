"""KIND and TOPIC as a main thread: attention, conversion and success rates per label and epoch group."""

import pandas as pd

from analysis.common import GROUP_NAMES, KINDS, in_group, rate

TOPIC_FILE_COLUMNS = ["topic", "kind"]


def _cell(part: pd.DataFrame) -> dict:
    """Count PRs and compute the three funnel rates for one group.

    Args:
        part: The group's rows.

    How:
        engaged14: share engaged within 14 days among PRs with a known outcome;
        success_if_engaged: among engaged and decided; success_decided: among all decided.

    Returns:
        Counts, rates, and the share of successes that were silent merges (no engagement).
    """
    decided = part[part["decided"]]
    return {"n": int(len(part)), "n_decided": int(len(decided)),
            "engaged14": rate(part["engaged14"]), "success_if_engaged": rate(part["success_if_eng"]),
            "success_decided": rate(decided["success"].astype(float)),
            "silent_merge_share_of_successes": rate(decided.loc[decided["success"], "eng"].map(lambda engaged: not engaged)).get("pp")}


def by_label(df: pd.DataFrame, column: str, labels: list[str]) -> list[dict]:
    """Tabulate one row per label with a cell for every epoch group.

    Args:
        df: Community PRs.
        column: Column holding the label (kind or topic).
        labels: Labels to report.

    How:
        Applies _cell to each label's rows within each epoch group.

    Returns:
        One dictionary per label.
    """
    rows = []
    for label in labels:
        subset = df[df[column] == label]
        rows.append({"label": label, **{group: _cell(in_group(subset, group)) for group in GROUP_NAMES}})
    return rows


def matrix(df: pd.DataFrame, topics: list[str]) -> list[dict]:
    """Tabulate topic by kind for a dot matrix.

    Args:
        df: Community PRs.
        topics: Topics to report.

    How:
        For every topic and kind pair over all epochs, counts PRs and decided PRs and takes the success rate among decided.

    Returns:
        One dictionary per topic and kind pair.
    """
    cells = []
    for topic in topics:
        for kind in KINDS:
            part = df[(df["topic"] == topic) & (df["kind"] == kind)]
            decided = part[part["decided"]]
            cells.append({"topic": topic, "kind": kind, "n": int(len(part)), "n_decided": int(len(decided)),
                          "success_pp": float(decided["success"].mean() * 100) if len(decided) else None})
    return cells


def run(df: pd.DataFrame) -> dict:
    """Collect the kind and topic tables for the JSON.

    Args:
        df: Community PRs from load_core.

    How:
        Drops the user's own PRs and orders topics by size.

    Returns:
        Dict with kinds, topics, the topic-by-kind matrix and the epoch group names.
    """
    community = df[~df["is_user_pr"]]
    topics = community["topic"].value_counts().index.tolist()
    return {"kinds": by_label(community, "kind", KINDS), "topics": by_label(community, "topic", topics),
            "matrix": matrix(community, topics), "groups": GROUP_NAMES,
            "note": "Labels come from a classifier reading title and first 600 characters of the body only."}
