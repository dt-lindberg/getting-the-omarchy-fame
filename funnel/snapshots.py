"""Title and body snapshots at four stages: open, pre_attention, post_feedback, final.

Open is reconstructed from the earliest description revision and the earliest rename's
previous title; later stages replay the revision and rename history up to a cutoff.
"""

import pandas as pd

from funnel.revisions import body_at, body_revisions, title_at

EDIT_TYPES = ["body_edit", "renamed_title"]
SNAPSHOT_COLUMNS = ["number", "stage", "stage_ts", "title", "body",
                    "edited_by_author_before_stage", "edited_by_maintainer_before_stage"]


def open_texts(node: dict, final_title: str, final_body: str, events: pd.DataFrame) -> tuple[str, str, bool]:
    """Title and body as first submitted.

    Args:
        node: PR node.
        final_title: Current title.
        final_body: Current body.
        events: This PR's events.

    How:
        Title from the earliest rename's previous title; body from the oldest
        revision (exact only if the API recorded the creation revision).

    Returns:
        (title, body, body_is_exact).
    """
    renames = events[events["type"] == "renamed_title"]
    title = renames["details"].iloc[0] if len(renames) else final_title
    revisions = body_revisions(node)
    if not revisions:
        return title, final_body, True
    return title, revisions[0].text, revisions[0].is_creation


def _edit_flags(events: pd.DataFrame, cutoff: pd.Timestamp, inclusive: bool) -> tuple[bool, bool]:
    """Whether the author / a maintainer edited title or body before the cutoff."""
    edits = events[events["type"].isin(EDIT_TYPES)]
    edits = edits[edits["ts"] <= cutoff] if inclusive else edits[edits["ts"] < cutoff]
    return bool((edits["actor_role"] == "author").any()), bool((edits["actor_role"] == "maintainer").any())


def snapshot_rows(node: dict, final_title: str, final_body: str, events: pd.DataFrame,
                  attention: dict, resolved_at: pd.Timestamp) -> tuple[list[dict], bool]:
    """Snapshot rows for one PR.

    Args:
        node: PR node.
        final_title: Current title.
        final_body: Current body.
        events: This PR's events.
        attention: Row from attention_row (needs first_maintainer_engagement,
            first_substantive_maintainer).
        resolved_at: Close/merge time or NaT.

    How:
        pre_attention cuts just before first maintainer engagement (or the end);
        post_feedback exists only when the author edited after the first substantive
        maintainer feedback and before resolution.

    Returns:
        (rows, open_body_exact).
    """
    number = node["number"]
    created = pd.Timestamp(node["createdAt"])
    open_title, open_body, exact = open_texts(node, final_title, final_body, events)
    revisions = body_revisions(node)
    renames = events[events["type"] == "renamed_title"]
    end = pd.Timestamp.max.tz_localize("UTC") if pd.isna(resolved_at) else resolved_at
    rows = [dict(number=number, stage="open", stage_ts=created, title=open_title, body=open_body,
                 edited_by_author_before_stage=False, edited_by_maintainer_before_stage=False)]
    engaged = attention["first_maintainer_engagement"]
    cut = engaged if pd.notna(engaged) else end
    author_flag, maint_flag = _edit_flags(events, cut, inclusive=False)
    rows.append(dict(number=number, stage="pre_attention", stage_ts=engaged if pd.notna(engaged) else resolved_at,
                     title=title_at(open_title, renames, cut, False), body=body_at(open_body, revisions, cut, False),
                     edited_by_author_before_stage=author_flag, edited_by_maintainer_before_stage=maint_flag))
    feedback = attention["first_substantive_maintainer"]
    if pd.notna(feedback):
        authored = events[events["type"].isin(EDIT_TYPES) & (events["actor_role"] == "author")
                          & (events["ts"] > feedback) & (events["ts"] < end)]
        if len(authored):
            stamp = authored["ts"].max()
            a_flag, m_flag = _edit_flags(events, stamp, inclusive=True)
            rows.append(dict(number=number, stage="post_feedback", stage_ts=stamp,
                             title=title_at(open_title, renames, stamp, True),
                             body=body_at(open_body, revisions, stamp, True),
                             edited_by_author_before_stage=a_flag, edited_by_maintainer_before_stage=m_flag))
    a_flag, m_flag = _edit_flags(events, end, inclusive=True)
    rows.append(dict(number=number, stage="final", stage_ts=resolved_at, title=final_title, body=final_body,
                     edited_by_author_before_stage=a_flag, edited_by_maintainer_before_stage=m_flag))
    return rows, exact
