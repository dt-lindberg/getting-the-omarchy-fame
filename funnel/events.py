"""Turn raw timeline nodes into one flat row per event (the events table).

Each GraphQL item type has its own small converter; all return rows with the same keys.
"""

import pandas as pd

from funnel.constants import BULK_MIN_PRS, TEXT_CAP_BOT, TEXT_CAP_HUMAN
from funnel.revisions import body_revisions
from funnel.roles import actor_role, normalise_login
from funnel.text_rules import is_substantive_text

EVENT_COLUMNS = ["number", "ts", "type", "actor", "actor_role", "substantive", "details", "details2",
                 "ref", "reaction_count", "inline_comments", "text_chars", "text", "bulk"]


def _login(node: dict | None) -> str:
    """Read the normalised login from a `{login}` sub-object.

    Args:
        node: GraphQL actor/user object, or None for deleted accounts.

    How:
        Delegates to normalise_login, so None becomes `ghost`.

    Returns:
        The normalised login.
    """
    return normalise_login((node or {}).get("login"))


def _row(number: int, ts: str, kind: str, actor: str, author: str, **extra) -> dict:
    """Build one event row with defaults for every column.

    Args:
        number: PR number.
        ts: Event timestamp (ISO string).
        kind: Event type.
        actor: Normalised actor login.
        author: Normalised PR author login.
        **extra: Column values overriding the defaults.

    How:
        Starts from neutral defaults, adds the actor's role relative to the PR, then applies `extra`.

    Returns:
        Row dictionary keyed by EVENT_COLUMNS.
    """
    row = {"number": number, "ts": ts, "type": kind, "actor": actor,
           "actor_role": actor_role(actor, author), "substantive": False, "details": "",
           "details2": "", "ref": None, "reaction_count": 0, "inline_comments": 0,
           "text_chars": 0, "text": "", "bulk": False}
    row.update(extra)
    return row


def _text_fields(text: str, role: str) -> dict:
    """Measure a text and cap how much of it is stored.

    Args:
        text: Comment or review body.
        role: Actor role; bots keep less because their comments are huge.

    How:
        Applies TEXT_CAP_BOT or TEXT_CAP_HUMAN.

    Returns:
        Dict with text_chars (full length) and the truncated text.
    """
    cap = TEXT_CAP_BOT if role == "bot" else TEXT_CAP_HUMAN
    return {"text_chars": len(text), "text": text[:cap]}


def _comment(number: int, item: dict, author: str) -> dict:
    """Convert an issue comment into an event row.

    Args:
        number: PR number.
        item: Timeline item of type IssueComment.
        author: Normalised PR author login.

    How:
        Records substantive-ness, author association and the total reaction count.

    Returns:
        Row dictionary.
    """
    actor = _login(item["author"])
    body = item["body"] or ""
    row = _row(number, item["createdAt"], "comment", actor, author,
               substantive=is_substantive_text(body), details=item["authorAssociation"] or "",
               reaction_count=sum(group["reactors"]["totalCount"] for group in item["reactionGroups"]))
    row.update(_text_fields(body, row["actor_role"]))
    return row


def _review(number: int, item: dict, author: str) -> dict:
    """Convert a review into an event row.

    Args:
        number: PR number.
        item: Timeline item of type PullRequestReview.
        author: Normalised PR author login.

    How:
        Substantive if it requests changes, has inline comments or has content text.

    Returns:
        Row dictionary.
    """
    actor = _login(item["author"])
    body = item["body"] or ""
    inline = item["comments"]["totalCount"]
    state = item["state"]
    row = _row(number, item["submittedAt"] or item["createdAt"], "review", actor, author,
               substantive=state == "CHANGES_REQUESTED" or inline > 0 or is_substantive_text(body),
               details=state, inline_comments=inline)
    row.update(_text_fields(body, row["actor_role"]))
    return row


def _commit(number: int, item: dict, author: str, created_at: str) -> dict:
    """Convert a commit on the PR branch into an event row.

    Args:
        number: PR number.
        item: Timeline item of type PullRequestCommit.
        author: Normalised PR author login.
        created_at: PR creation time, to mark commits made before it.

    How:
        Unlinked git authors become actor `ghost`; earlier commits get details `pre_creation`.

    Returns:
        Row dictionary.
    """
    commit = item["commit"]
    user = ((commit["author"] or {}).get("user"))
    ts = commit["committedDate"]
    return _row(number, ts, "commit", _login(user), author,
                details="pre_creation" if ts <= created_at else "", details2=commit["messageHeadline"] or "")


def _closed(number: int, item: dict, author: str) -> dict:
    """Convert a closed event into an event row.

    Args:
        number: PR number.
        item: Timeline item of type ClosedEvent.
        author: Normalised PR author login.

    How:
        `ref` is the PR number of a closing PR when there is one.

    Returns:
        Row dictionary.
    """
    closer = item.get("closer") or {}
    ref = closer.get("number") if closer.get("__typename") == "PullRequest" else None
    return _row(number, item["createdAt"], "closed", _login(item["actor"]), author,
                details=item.get("stateReason") or "", details2=closer.get("__typename", ""), ref=ref)


def _cross_reference(number: int, item: dict, author: str) -> dict:
    """Convert a cross-reference from another issue or PR into an event row.

    Args:
        number: PR number.
        item: Timeline item of type CrossReferencedEvent.
        author: Normalised PR author login.

    How:
        Details says which kind of source it is and whether it closes the PR;
        references from other repositories carry no ref.

    Returns:
        Row dictionary.
    """
    source = item["source"] or {}
    foreign = item["isCrossRepository"]
    kind = ("foreign_" if foreign else "") + source.get("__typename", "").lower()
    return _row(number, item["createdAt"], "cross_referenced", _login(item["actor"]), author,
                details=kind, details2="closes" if item["willCloseTarget"] else "",
                ref=None if foreign else source.get("number"))


def timeline_row(number: int, item: dict, author: str, created_at: str) -> dict | None:
    """Convert one timeline item to an event row.

    Args:
        number: PR number.
        item: Raw timeline item.
        author: Normalised PR author login.
        created_at: PR creation time.

    How:
        Dispatches on the item's GraphQL type to a converter or a simple row.

    Returns:
        Row dictionary, or None for unknown item types.
    """
    kind = item["__typename"]
    actor = _login(item.get("actor"))
    simple = {"ReopenedEvent": "reopened", "ConvertToDraftEvent": "draft",
              "ReadyForReviewEvent": "ready_for_review", "MergedEvent": "merged",
              "HeadRefForcePushedEvent": "force_push", "ReferencedEvent": "referenced"}
    if kind == "IssueComment":
        return _comment(number, item, author)
    if kind == "PullRequestReview":
        return _review(number, item, author)
    if kind == "PullRequestCommit":
        return _commit(number, item, author, created_at)
    if kind == "ClosedEvent":
        return _closed(number, item, author)
    if kind == "CrossReferencedEvent":
        return _cross_reference(number, item, author)
    if kind in simple:
        return _row(number, item["createdAt"], simple[kind], actor, author)
    if kind in ("LabeledEvent", "UnlabeledEvent"):
        name = "labeled" if kind == "LabeledEvent" else "unlabeled"
        return _row(number, item["createdAt"], name, actor, author, details=item["label"]["name"])
    if kind == "RenamedTitleEvent":
        return _row(number, item["createdAt"], "renamed_title", actor, author,
                    details=item["previousTitle"], details2=item["currentTitle"])
    if kind == "ReviewRequestedEvent":
        who = item["requestedReviewer"] or {}
        return _row(number, item["createdAt"], "review_requested", actor, author,
                    details=who.get("login") or who.get("teamSlug") or "")
    if kind == "AssignedEvent":
        return _row(number, item["createdAt"], "assigned", actor, author, details=_login(item["assignee"]))
    if kind == "MarkedAsDuplicateEvent":
        canonical = item["canonical"] or {}
        return _row(number, item["createdAt"], "marked_duplicate", actor, author,
                    details=canonical.get("__typename", ""), ref=canonical.get("number"))
    if kind == "ConnectedEvent":
        subject = item["subject"] or {}
        return _row(number, item["createdAt"], "connected", actor, author,
                    details=subject.get("__typename", ""), ref=subject.get("number"))
    return None


def side_rows(node: dict, author: str) -> list[dict]:
    """Build rows for body edits and reactions on the PR body.

    Args:
        node: PR node.
        author: Normalised PR author login.

    How:
        Body edits exclude the creation revision.

    Returns:
        Row dictionaries.
    """
    number = node["number"]
    rows = [_row(number, revision.edited_at, "body_edit", revision.editor, author)
            for revision in body_revisions(node) if not revision.is_creation]
    for reaction in node["reactions"]["nodes"]:
        rows.append(_row(number, reaction["createdAt"], "reaction", _login(reaction["user"]), author,
                         details=reaction["content"]))
    return rows


def node_events(node: dict) -> list[dict]:
    """Build all event rows for one PR node.

    Args:
        node: PR node.

    How:
        Converts timeline items, drops unknown types, and appends the body edits and reactions.

    Returns:
        Row dictionaries.
    """
    number = node["number"]
    author = _login(node["author"])
    rows = [timeline_row(number, item, author, node["createdAt"])
            for item in node["timelineItems"]["nodes"] if item]
    return [row for row in rows if row] + side_rows(node, author)


# Event types whose content is unique per PR, so identical timing is not a bulk action.
NEVER_BULK = {"comment", "review", "commit", "force_push", "body_edit", "cross_referenced", "referenced", "connected"}


def flag_bulk(events: pd.DataFrame) -> pd.Series:
    """Mark events done in bulk: same actor, type and detail on many PRs in one minute.

    Args:
        events: Events table with parsed `ts`.

    How:
        Counts distinct PRs per (actor, type, details, minute); the 2026-09-08 review
        requests and the 2026-09-21 mass close both show up this way.

    Returns:
        Boolean Series aligned with events.
    """
    minute = events["ts"].dt.floor("min")
    keys = [events["actor"], events["type"], events["details"], minute]
    prs_per_key = events.groupby(keys)["number"].transform("nunique")
    return (prs_per_key >= BULK_MIN_PRS) & ~events["type"].isin(NEVER_BULK)


def build_events(nodes: list[dict]) -> pd.DataFrame:
    """Events table for all PR nodes, sorted by PR and time.

    Args:
        nodes: PR nodes from load_timeline_nodes.

    How:
        Converts every item, parses timestamps to UTC and sorts stably so
        events sharing a second keep API order.

    Returns:
        DataFrame with EVENT_COLUMNS.
    """
    rows = [row for node in nodes for row in node_events(node)]
    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    events["ts"] = pd.to_datetime(events["ts"], utc=True)
    events["ref"] = events["ref"].astype("Int64")
    events["bulk"] = flag_bulk(events)
    return events.sort_values(["number", "ts"], kind="stable").reset_index(drop=True)
