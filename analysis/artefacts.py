"""Triage artefacts (labels, bot comments, review requests, reactions) and maintainer rewrites."""

import numpy as np
import pandas as pd

from analysis.common import DERIVED, EPOCH_ORDER, GROUP_NAMES, in_group, median_quartiles, rate
from funnel.constants import SECONDS_PER_HOUR

LABELS_OF_INTEREST = ["verified", "ready", "bug", "enhancement", "duplicate", "compatibility", "documentation"]
MAX_LISTED_NUMBERS = 40
EVENT_COLUMNS = ["number", "ts", "type", "actor", "actor_role", "details", "bulk"]
# Artefact name -> predicate over the event table.
ARTEFACTS = {
    **{f"label: {name}": (lambda events, label=name: (events["type"] == "labeled") & (events["details"] == label)) for name in LABELS_OF_INTEREST},
    "omarchybot comment": lambda events: (events["type"] == "comment") & (events["actor"] == "omarchybot"),
    "AI code review (copilot, greptile)": lambda events: (events["type"] == "review") & events["actor"].str.contains("copilot|greptile", regex=True),
    "maintainer review request (individual)": lambda events: (events["type"] == "review_requested") & (events["actor_role"] == "maintainer") & ~events["bulk"],
    "maintainer review request (bulk)": lambda events: (events["type"] == "review_requested") & (events["actor_role"] == "maintainer") & events["bulk"],
    "maintainer reaction": lambda events: (events["type"] == "reaction") & (events["actor_role"] == "maintainer"),
    "assignment": lambda events: events["type"] == "assigned",
}


def first_times(df: pd.DataFrame) -> pd.DataFrame:
    """Find the first timestamp of each artefact per PR.

    Args:
        df: Community PRs with a `number` column.

    How:
        Applies each ARTEFACTS predicate to the events of those PRs and takes the earliest time per PR.

    Returns:
        Wide table indexed by PR number, one column per artefact.
    """
    events = pd.read_parquet(DERIVED / "events.parquet", columns=EVENT_COLUMNS)
    events = events[events["number"].isin(df["number"])]
    first_by_artefact = {}
    for name, predicate in ARTEFACTS.items():
        hit = events[predicate(events)]
        first_by_artefact[name] = hit.groupby("number")["ts"].min()
    return pd.DataFrame(first_by_artefact).reindex(df["number"])


def artefact_table(df: pd.DataFrame) -> list[dict]:
    """Tabulate success with and without each artefact, and hours before the decision.

    Args:
        df: Community PRs from load_core.

    How:
        Only decided PRs. An artefact counts when its first occurrence is on or
        before the decision time; later ones (bot labels on closed PRs) are ignored.
        Hours-before-decision is shown for successes and non-successes separately.

    Returns:
        One dictionary per artefact.
    """
    decided = df[df["decided"] & ~df["is_user_pr"]]
    first = first_times(decided).set_axis(decided.index)
    rows = []
    for name in ARTEFACTS:
        has = first[name].notna() & (first[name] <= decided["resolved_at"])
        gap = (decided["resolved_at"] - first[name]).dt.total_seconds() / SECONDS_PER_HOUR
        row = {"artefact": name, "n_with": int(has.sum()), "share_of_decided_pp": float(has.mean() * 100),
               "hours_before_decision": {"success": median_quartiles(gap[has & decided["success"]]),
                                         "not_success": median_quartiles(gap[has & ~decided["success"]])}}
        for group in GROUP_NAMES:
            sel = decided.index.isin(in_group(decided, group).index)
            row[group] = {"with": rate(decided.loc[has & sel, "success"].astype(float)),
                          "without": rate(decided.loc[~has & sel, "success"].astype(float))}
        rows.append(row)
    return rows


def rewrites(df: pd.DataFrame) -> dict:
    """Count how often maintainers renamed or edited the body of community PRs.

    Args:
        df: Community PRs from load_core.

    How:
        Counts over accepted PRs and over all community PRs (the user's own excluded), per epoch,
        and lists every renamed PR as an example.

    Returns:
        Counts, per-epoch counts, title examples and up to MAX_LISTED_NUMBERS accepted PRs with body edits.
    """
    community = df[~df["is_user_pr"]]
    accepted = community[community["success"]]
    renamed = community[community["maintainer_renamed_title"]]
    by_epoch = {epoch: {"accepted": int((accepted["epoch"] == epoch).sum()),
                        "title_rewritten": int(((accepted["epoch"] == epoch) & accepted["maintainer_renamed_title"]).sum()),
                        "body_edited": int(((accepted["epoch"] == epoch) & accepted["maintainer_edited_body"]).sum())}
                for epoch in EPOCH_ORDER}
    examples = [{"number": int(pr.number), "epoch": str(pr.epoch), "accepted": bool(pr.success), "disposition": pr.disp,
                 "before": pr.title_before_rename, "after": pr.title_after_rename}
                for pr in renamed.sort_values("number").itertuples()]
    return {"accepted": int(len(accepted)), "accepted_title_rewritten": int(accepted["maintainer_renamed_title"].sum()),
            "accepted_body_edited": int(accepted["maintainer_edited_body"].sum()),
            "all_community_title_rewritten": int(len(renamed)), "all_community_body_edited": int(community["maintainer_edited_body"].sum()),
            "by_epoch": by_epoch, "examples": examples,
            "body_edited_numbers_accepted": [int(number) for number in accepted.loc[accepted["maintainer_edited_body"], "number"]][:MAX_LISTED_NUMBERS]}


def run(df: pd.DataFrame) -> dict:
    """Collect the artefact and rewrite results for the JSON.

    Args:
        df: Community PRs from load_core.

    How:
        Runs artefact_table and rewrites.

    Returns:
        Dict with `artefacts` and `rewrites`.
    """
    return {"artefacts": artefact_table(df), "rewrites": rewrites(df)}
