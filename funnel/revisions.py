"""Description revision history and title history, used for events and snapshots.

GitHub's userContentEdits lists every saved version of the description: each node's
`diff` is the full text as of its `editedAt`. The oldest node is the original text
only when `includesCreatedEdit` is true.
"""

from dataclasses import dataclass

import pandas as pd

from funnel.roles import normalise_login


@dataclass(frozen=True)
class BodyRevision:
    """One saved version of a PR description."""

    edited_at: str
    editor: str
    text: str
    is_creation: bool


def body_revisions(node: dict) -> list[BodyRevision]:
    """Description versions in time order.

    Args:
        node: PR node with userContentEdits.

    How:
        Sorts by editedAt (the API returns newest first) and marks the oldest as
        the creation text only when includesCreatedEdit is set.

    Returns:
        Versions oldest first; empty when the description was never edited.
    """
    edits = sorted((edit for edit in node["userContentEdits"]["nodes"] if edit["diff"] is not None),
                   key=lambda edit: edit["editedAt"])
    return [BodyRevision(edit["editedAt"], normalise_login((edit["editor"] or {}).get("login")),
                         edit["diff"], is_creation=index == 0 and node["includesCreatedEdit"])
            for index, edit in enumerate(edits)]


def title_at(open_title: str, renames: pd.DataFrame, when: pd.Timestamp, inclusive: bool) -> str:
    """Title as of a time, replaying rename events.

    Args:
        open_title: Title at creation.
        renames: This PR's renamed_title events (details2 = new title), time-sorted.
        when: Reference time.
        inclusive: Whether a rename exactly at `when` already applies.

    How:
        Takes the new title of the last rename up to `when`, else the opening title.

    Returns:
        The title at that time.
    """
    done = renames[renames["ts"] <= when] if inclusive else renames[renames["ts"] < when]
    return done["details2"].iloc[-1] if len(done) else open_title


def body_at(open_body: str, revisions: list[BodyRevision], when: pd.Timestamp, inclusive: bool) -> str:
    """Replay description revisions to get the body at a time.

    Args:
        open_body: Body at creation.
        revisions: Description versions, oldest first.
        when: Reference time.
        inclusive: Whether a revision exactly at `when` already applies.

    How:
        Walks the revisions in order and keeps the text of the last one up to `when`.

    Returns:
        The latest revision's text at or before `when`, else the opening text.
    """
    text = open_body
    for revision in revisions:
        stamp = pd.Timestamp(revision.edited_at)
        if (stamp <= when) if inclusive else (stamp < when):
            text = revision.text
    return text
