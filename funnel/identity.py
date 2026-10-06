"""Identity columns, epochs and resolution time/actor for every PR."""

import pandas as pd

from funnel.constants import EPOCH_STARTS, USER_LOGIN
from funnel.roles import actor_role, author_group, normalise_login


def epoch_of(created_at: pd.Timestamp) -> str:
    """Label the epoch (E0 pre-launch, E1..E4) a PR was created in.

    Args:
        created_at: PR creation time (UTC).

    How:
        Takes the last epoch in EPOCH_STARTS whose start is not after the time.

    Returns:
        The epoch name.
    """
    label = "E0"
    for name, start in EPOCH_STARTS:
        if created_at >= start:
            label = name
    return label


def _last_event(events: pd.DataFrame, kind: str) -> pd.Series | None:
    """Find the latest event of one type in a PR's events.

    Args:
        events: One PR's events, time-sorted.
        kind: Event type to look for.

    How:
        Filters by type and takes the last row.

    Returns:
        The event row, or None when there is none.
    """
    subset = events[events["type"] == kind]
    return subset.iloc[-1] if len(subset) else None


def resolver_of(node: dict, events: pd.DataFrame, author: str) -> dict:
    """Who closed or merged the PR, and when.

    Args:
        node: PR node (state, mergedAt, closedAt, mergedBy).
        events: This PR's events.
        author: Normalised PR author.

    How:
        Merged PRs use the MergedEvent actor, closed PRs the last ClosedEvent
        (a PR can be closed, reopened and closed again); a closed PR with no
        ClosedEvent gets closed_by `unknown`.

    Returns:
        Dict with resolved_at, closed_by, closed_by_role, closer_type, closer_ref.
    """
    state = node["state"]
    empty = {"resolved_at": pd.NaT, "closed_by": None, "closed_by_role": None,
             "closer_type": "", "closer_ref": pd.NA}
    if state == "OPEN":
        return empty
    event = _last_event(events, "merged" if state == "MERGED" else "closed")
    stamp = node["mergedAt"] if state == "MERGED" else node["closedAt"]
    if event is None:
        actor = normalise_login((node.get("mergedBy") or {}).get("login")) if state == "MERGED" else "unknown"
        role = "unknown" if actor == "unknown" else actor_role(actor, author)
        return {**empty, "resolved_at": pd.Timestamp(stamp), "closed_by": actor, "closed_by_role": role}
    return {"resolved_at": pd.Timestamp(stamp), "closed_by": event["actor"],
            "closed_by_role": event["actor_role"], "closer_type": event["details2"],
            "closer_ref": event["ref"]}


def build_identity(nodes: list[dict], events_by_pr: dict[int, pd.DataFrame]) -> pd.DataFrame:
    """One identity row per PR.

    Args:
        nodes: PR nodes.
        events_by_pr: Events grouped by PR number.

    How:
        Combines node scalars with resolver_of; times are UTC timestamps.

    Returns:
        DataFrame indexed by number.
    """
    rows = []
    empty = pd.DataFrame(columns=["type", "actor", "actor_role", "details2", "ref"])
    for node in nodes:
        author = normalise_login((node["author"] or {}).get("login"))
        created = pd.Timestamp(node["createdAt"])
        events = events_by_pr.get(node["number"], empty)
        rows.append({
            "number": node["number"], "author": author, "author_group": author_group(author),
            "created_at": created, "epoch": epoch_of(created), "is_user_pr": author == USER_LOGIN,
            "state": node["state"].lower(), "merged": node["state"] == "MERGED",
            "is_draft_now": node["isDraft"],
            **resolver_of(node, events, author),
        })
    table = pd.DataFrame(rows).set_index("number")
    table["resolved_at"] = pd.to_datetime(table["resolved_at"], utc=True)
    table["closer_ref"] = table["closer_ref"].astype("Int64")
    return table
