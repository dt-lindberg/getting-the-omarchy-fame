"""Attention timestamps and interaction counts per PR (first-touch, engagement, substance).

Definitions
- interaction: any non-author event of an INTERACTION type (commits, force pushes, pure
  mentions by commits are not interactions).
- maintainer touch: any maintainer interaction up to and including the close or merge.
- maintainer engagement: maintainer comment, review, review request, label, unlabel, rename,
  reaction or assignment strictly before the close/merge, excluding the terminal comment.
- substantive maintainer: engagement that is a comment/review with content.
- nobulk engagement: engagement ignoring bulk actions (same action on 20+ PRs in a minute).
"""

import numpy as np
import pandas as pd

from funnel.terminal import terminal_comment_rows

INTERACTION_TYPES = {"comment", "review", "review_requested", "labeled", "unlabeled", "renamed_title",
                     "reaction", "assigned", "closed", "merged", "marked_duplicate",
                     "cross_referenced", "draft", "ready_for_review", "reopened"}
TOUCH_TYPES = INTERACTION_TYPES | {"referenced", "connected"}
ENGAGEMENT_TYPES = {"comment", "review", "review_requested", "labeled", "unlabeled", "renamed_title",
                    "reaction", "assigned"}
TERMINAL_TYPES = {"closed", "merged"}
HOURS = pd.Timedelta(hours=1)
FAR_FUTURE = pd.Timestamp.max.tz_localize("UTC")


def _first(events: pd.DataFrame, mask: pd.Series) -> pd.Timestamp:
    """Earliest timestamp among masked events, or NaT."""
    subset = events.loc[mask, "ts"]
    return subset.min() if len(subset) else pd.NaT


def attention_times(events: pd.DataFrame, resolved_at: pd.Timestamp, terminal_rows: pd.Index) -> dict:
    """Absolute timestamps of the six attention stages for one PR.

    Args:
        events: One PR's events, time-sorted.
        resolved_at: Close/merge time, NaT while open.
        terminal_rows: Index labels of terminal comments to exclude from engagement.

    How:
        Applies the definitions in the module docstring with boolean masks.

    Returns:
        Dict of Timestamps (NaT where the stage never happened).
    """
    end = FAR_FUTURE if pd.isna(resolved_at) else resolved_at
    role, kind, ts = events["actor_role"], events["type"], events["ts"]
    others = (role != "author") & kind.isin(INTERACTION_TYPES) & (ts <= end)
    maintainer = role == "maintainer"
    engaged = (maintainer & kind.isin(ENGAGEMENT_TYPES) & (ts < end) & ~events.index.isin(terminal_rows))
    unique = engaged & ~events["bulk"]
    content = engaged & kind.isin(["comment", "review"]) & events["substantive"]
    return {
        "first_any_interaction": _first(events, others),
        "first_community_interaction": _first(events, others & (role == "community")),
        "first_bot_interaction": _first(events, others & (role == "bot")),
        "first_maintainer_touch": _first(events, maintainer & kind.isin(TOUCH_TYPES) & (ts <= end)),
        "first_maintainer_engagement": _first(events, engaged),
        "first_maintainer_engagement_nobulk": _first(events, unique),
        "first_substantive_maintainer": _first(events, content),
    }


def interaction_counts(events: pd.DataFrame, created_at: pd.Timestamp, cutoff: pd.Timestamp,
                       suffix: str) -> dict:
    """Interaction counts strictly before `cutoff` (terminal close/merge events excluded).

    Args:
        events: One PR's events.
        created_at: PR creation time (follow-up commits are after this).
        cutoff: Counting stops before this time.
        suffix: Appended to every column name.

    How:
        Non-author interactions are split by role; author actions counted separately.

    Returns:
        Column dictionary.
    """
    ev = events[events["ts"] < cutoff]
    role, kind = ev["actor_role"], ev["type"]
    inter = ev[(role != "author") & kind.isin(INTERACTION_TYPES - TERMINAL_TYPES)]
    maint = inter[inter["actor_role"] == "maintainer"]
    author_edits = ev[role == "author"]
    unknown_author_commit = (role != "author") & (ev["actor"] == "ghost") & (kind == "commit")
    commits = ev[(kind == "commit") & (ev["ts"] > created_at) & ((role == "author") | unknown_author_commit)]
    values = {
        "n_interactions": len(inter),
        "n_community_participants": inter.loc[inter["actor_role"] == "community", "actor"].nunique(),
        "n_maintainers": maint["actor"].nunique(),
        "n_bot_events": int((inter["actor_role"] == "bot").sum()),
        "n_reactions": int((inter["type"] == "reaction").sum()),
        "n_comment_reactions": int(ev.loc[kind == "comment", "reaction_count"].sum()),
        "n_substantive_maintainer": int((maint["type"].isin(["comment", "review"]) & maint["substantive"]).sum()),
        "n_changes_requested": int(((inter["type"] == "review") & (inter["details"] == "CHANGES_REQUESTED")).sum()),
        "n_author_commits": len(commits),
        "n_author_comments": int(author_edits["type"].isin(["comment", "review"]).sum()),
        "title_edits_author": int((author_edits["type"] == "renamed_title").sum()),
        "body_edits_author": int((author_edits["type"] == "body_edit").sum()),
        "title_edits_maintainer": int((ev["type"].eq("renamed_title") & (role == "maintainer")).sum()),
        "body_edits_maintainer": int((ev["type"].eq("body_edit") & (role == "maintainer")).sum()),
    }
    return {f"{name}{suffix}": value for name, value in values.items()}


def attention_row(events: pd.DataFrame, created_at: pd.Timestamp, resolved_at: pd.Timestamp,
                  closed_by: str | None, closed_by_role: str | None) -> dict:
    """All attention columns for one PR.

    Args:
        events: One PR's events.
        created_at: Creation time.
        resolved_at: Close/merge time or NaT.
        closed_by: Closer login.
        closed_by_role: Role of the closer relative to the PR.

    How:
        Times, hours-from-creation, silent_decision, then counts to resolution and
        to the first maintainer engagement (or resolution if there is none).

    Returns:
        Column dictionary.
    """
    terminal = terminal_comment_rows(events, resolved_at, closed_by)
    times = attention_times(events, resolved_at, terminal)
    row = dict(times)
    for name, stamp in times.items():
        row["h_" + name.removeprefix("first_")] = (stamp - created_at) / HOURS if pd.notna(stamp) else np.nan
    row["silent_decision"] = bool(pd.notna(resolved_at) and closed_by_role == "maintainer"
                                  and pd.isna(times["first_maintainer_engagement"]))
    end = FAR_FUTURE if pd.isna(resolved_at) else resolved_at
    pre_cut = times["first_maintainer_engagement"] if pd.notna(times["first_maintainer_engagement"]) else end
    row.update(interaction_counts(events, created_at, end, ""))
    row.update(interaction_counts(events, created_at, pre_cut, "_pre_eng"))
    return row
