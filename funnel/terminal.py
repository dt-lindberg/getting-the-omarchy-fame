"""Detect the terminal comment: a closer's note that is part of the close itself."""

import pandas as pd

from funnel.constants import TERMINAL_COMMENT_MINUTES

AUTHOR_ACTIVITY = {"comment", "review", "commit", "force_push", "body_edit", "renamed_title"}


def terminal_comment_rows(events: pd.DataFrame, resolved_at: pd.Timestamp, closer: str | None) -> pd.Index:
    """Index labels of comments/reviews by the closer that belong to the close.

    Args:
        events: One PR's events.
        resolved_at: Close or merge time (NaT for open PRs).
        closer: Login that closed or merged the PR.

    How:
        A comment or review by the closer within TERMINAL_COMMENT_MINUTES of the
        resolution counts, unless the author acted between that comment and a
        resolution that came after it (then it was feedback, not part of the close).

    Returns:
        Index labels of the terminal comments (possibly empty).
    """
    if pd.isna(resolved_at) or not closer:
        return events.index[:0]
    window = pd.Timedelta(minutes=TERMINAL_COMMENT_MINUTES)
    by_closer = events[events["type"].isin(["comment", "review"]) & (events["actor"] == closer)
                       & ((events["ts"] - resolved_at).abs() <= window)]
    author_acts = events[(events["actor_role"] == "author") & events["type"].isin(AUTHOR_ACTIVITY)]
    keep = []
    for label, row in by_closer.iterrows():
        between = author_acts[(author_acts["ts"] > row["ts"]) & (author_acts["ts"] < resolved_at)]
        if between.empty:
            keep.append(label)
    return pd.Index(keep)
