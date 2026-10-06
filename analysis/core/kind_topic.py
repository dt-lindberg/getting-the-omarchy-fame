"""KIND and TOPIC as a main thread: attention, conversion and success rates per label and epoch group."""

import pandas as pd

from analysis.core.common import GROUP_NAMES, KINDS, in_group, rate

TOPIC_FILE_COLUMNS = ["topic", "kind"]


def _cell(part: pd.DataFrame) -> dict:
    """Counts and the three funnel rates for one group of PRs.

    How:
        engaged14: share engaged within 14 days among PRs with a known outcome;
        success_if_engaged: among engaged and decided; success_decided: among all decided.
    """
    dec = part[part["decided"]]
    return {"n": int(len(part)), "n_decided": int(len(dec)),
            "engaged14": rate(part["engaged14"]), "success_if_engaged": rate(part["success_if_eng"]),
            "success_decided": rate(dec["success"].astype(float)),
            "silent_merge_share_of_successes": rate(dec.loc[dec["success"], "eng"].map(lambda e: not e)).get("pp")}


def by_label(df: pd.DataFrame, column: str, labels: list[str]) -> list[dict]:
    """One row per label with a cell for every epoch group."""
    rows = []
    for label in labels:
        sub = df[df[column] == label]
        rows.append({"label": label, **{g: _cell(in_group(sub, g)) for g in GROUP_NAMES}})
    return rows


def matrix(df: pd.DataFrame, topics: list[str]) -> list[dict]:
    """Topic by kind: n, decided and success among decided (all epochs), for a dot matrix."""
    out = []
    for topic in topics:
        for kind in KINDS:
            part = df[(df["topic"] == topic) & (df["kind"] == kind)]
            dec = part[part["decided"]]
            out.append({"topic": topic, "kind": kind, "n": int(len(part)), "n_decided": int(len(dec)),
                        "success_pp": float(dec["success"].mean() * 100) if len(dec) else None})
    return out


def run(df: pd.DataFrame) -> dict:
    """Kind and topic tables for the JSON (topics sorted by size)."""
    d = df[~df["is_user_pr"]]
    topics = d["topic"].value_counts().index.tolist()
    return {"kinds": by_label(d, "kind", KINDS), "topics": by_label(d, "topic", topics),
            "matrix": matrix(d, topics), "groups": GROUP_NAMES,
            "note": "Labels come from a classifier reading title and first 600 characters of the body only."}
