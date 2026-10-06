"""Feedback episode: the first substantive maintainer feedback and how the author reacted."""

import numpy as np
import pandas as pd

from funnel.constants import HOURS_PER_DAY, ONE_HOUR, RESPONSE_WINDOW_DAYS


def _author_response_events(events: pd.DataFrame, feedback_at: pd.Timestamp) -> pd.DataFrame:
    """Select the author's actions after the feedback, labelled by kind.

    Args:
        events: One PR's events.
        feedback_at: Time of the first substantive maintainer feedback.

    How:
        Keeps author events (and commits by unlinked `ghost` authors, who are
        counted as the author) of a response type, mapped to commit, comment,
        force_push, body_edit or title_edit.

    Returns:
        The matching events with an added `kind` column.
    """
    after = events[events["ts"] > feedback_at]
    is_author = after["actor_role"] == "author"
    ghost_commit = (after["actor"] == "ghost") & (after["type"] == "commit")
    kinds = after["type"].map({"commit": "commit", "comment": "comment", "review": "comment",
                               "force_push": "force_push", "body_edit": "body_edit",
                               "renamed_title": "title_edit"})
    keep = (is_author | ghost_commit) & kinds.notna()
    return after[keep].assign(kind=kinds[keep])


def feedback_row(events: pd.DataFrame, feedback_at: pd.Timestamp, resolved_at: pd.Timestamp,
                 data_end: pd.Timestamp, disposition: str) -> dict:
    """Feedback-episode columns for one PR.

    Args:
        events: One PR's events.
        feedback_at: First substantive maintainer feedback time (NaT if none).
        resolved_at: Close/merge time or NaT.
        data_end: Latest timestamp in the data, the end of observation for open PRs.
        disposition: Final disposition name.

    How:
        Author actions between feedback and min(resolution, feedback + RESPONSE_WINDOW_DAYS) count as a
        response; commits after feedback are counted up to resolution.

    Returns:
        Column dictionary (None/NaN when there was no feedback).
    """
    empty = {"has_feedback": False, "feedback_at": pd.NaT, "feedback_type": None, "feedback_by": None,
             "author_responded": None, "response_hours": np.nan, "response_kinds": [],
             "feedback_window_h": np.nan, "pushed_commits_after_feedback": 0, "feedback_outcome": None}
    if pd.isna(feedback_at):
        return empty
    source = events[(events["ts"] == feedback_at) & (events["actor_role"] == "maintainer")
                    & events["type"].isin(["comment", "review"]) & events["substantive"]].iloc[0]
    kind = "changes_requested" if source["details"] == "CHANGES_REQUESTED" else source["type"]
    stop = data_end if pd.isna(resolved_at) else resolved_at
    responses = _author_response_events(events, feedback_at)
    responses = responses[responses["ts"] < stop]
    window = responses[responses["ts"] <= feedback_at + pd.Timedelta(days=RESPONSE_WINDOW_DAYS)]
    return {
        "has_feedback": True, "feedback_at": feedback_at, "feedback_type": kind,
        "feedback_by": source["actor"], "author_responded": len(window) > 0,
        "response_hours": (window["ts"].min() - feedback_at) / ONE_HOUR if len(window) else np.nan,
        "response_kinds": sorted(window["kind"].unique()),
        "feedback_window_h": min(RESPONSE_WINDOW_DAYS * HOURS_PER_DAY, (stop - feedback_at) / ONE_HOUR),
        "pushed_commits_after_feedback": int((responses["kind"] == "commit").sum()),
        "feedback_outcome": disposition,
    }
