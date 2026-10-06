"""Disposition of each PR: merged, absorbed, self-closed, duplicate, mass-closed, ...

Precedence (first match wins): merged > absorbed > self_closed > superseded_duplicate >
mass_closed > bot_admin_closed > maintainer_rejected, with `open` for unresolved PRs and
`other_closed` when a non-author community member closed the PR.
"""

import re

import pandas as pd

from funnel.constants import (CLOSING_BOTS, CLOSING_COMMENT_WINDOW_HOURS, MASS_CLOSE_EVENT_DAY,
                              MASS_CLOSE_MIN)
from funnel.terminal import terminal_comment_rows

SUPERSEDED_RE = re.compile(
    r"\bdupl\w*|\bdupe\b|supersed\w*|superceded|\bfixed (?:in|by|via)\b|\blanded (?:in|as|via|with)\b|"
    r"\balready (?:done|fix\w*|implemented|merged|handled|exists?|covered|in|landed|addressed|included|"
    r"supported|there|works?|possible|available|resolved)\b|in favou?r of|replaced (?:by|with)|"
    r"covered (?:by|in)|handled (?:in|by)|taken care of|folded (?:in|into)|rolled (?:in|into)|"
    r"(?:merged|included|implemented) (?:in|into|via|as part of) #\d+|"
    r"brought in|cherry[- ]?pick\w*|with your authorship|authorship|gave you (?:commit )?credit|credited you|"
    r"commit credit",
    re.I,
)
EXCERPT_CHARS = 400
DATE_FORMAT = "%Y-%m-%d"


def mass_close_keys(identity: pd.DataFrame) -> set[tuple[str, str]]:
    """Find the (closer, UTC date) pairs where one actor closed at least MASS_CLOSE_MIN PRs.

    Args:
        identity: Identity table with state, closed_by, resolved_at, author.

    How:
        Counts unmerged closures per actor and day, ignoring authors closing their own PRs.

    Returns:
        Set of (closer login, "YYYY-MM-DD") pairs.
    """
    closed = identity[(identity["state"] == "closed") & (identity["closed_by"] != identity["author"])]
    days = closed["resolved_at"].dt.strftime(DATE_FORMAT)
    counts = closed.groupby([closed["closed_by"], days]).size()
    return set(counts[counts >= MASS_CLOSE_MIN].index)


def closing_comment(events: pd.DataFrame, resolved_at: pd.Timestamp) -> tuple[str, str]:
    """Find the maintainer or closing-bot comment nearest the close, within the window.

    Args:
        events: One PR's events.
        resolved_at: Close/merge time (NaT for open PRs).

    How:
        Keeps non-empty comments and reviews by maintainers or CLOSING_BOTS within
        CLOSING_COMMENT_WINDOW_HOURS of the close and picks the closest in time.

    Returns:
        (actor, text); empty strings when there is none.
    """
    if pd.isna(resolved_at):
        return "", ""
    window = pd.Timedelta(hours=CLOSING_COMMENT_WINDOW_HOURS)
    mask = events["type"].isin(["comment", "review"]) & (events["text_chars"] > 0)
    mask &= (events["actor_role"] == "maintainer") | events["actor"].isin(CLOSING_BOTS)
    near = events[mask & ((events["ts"] - resolved_at).abs() <= window)]
    if near.empty:
        return "", ""
    row = near.loc[(near["ts"] - resolved_at).abs().idxmin()]
    return row["actor"], " ".join(row["text"].split())[:EXCERPT_CHARS]


def classify(row: pd.Series, flags: dict) -> str:
    """Apply the precedence rules to one PR.

    Args:
        row: Identity row (state, merged, closed_by_role).
        flags: absorbed, duplicate_evidence, mass_closed booleans.

    How:
        Returns the first matching rule in the module's precedence order.

    Returns:
        Disposition name.
    """
    if row["merged"]:
        return "merged"
    if row["state"] == "open":
        return "open"
    if flags["absorbed"]:
        return "absorbed"
    if row["closed_by_role"] == "author":
        return "self_closed"
    if flags["duplicate_evidence"]:
        return "superseded_duplicate"
    if flags["mass_closed"]:
        return "mass_closed"
    if row["closed_by_role"] in ("bot", "unknown"):
        return "bot_admin_closed"
    if row["closed_by_role"] == "community":
        return "other_closed"
    return "maintainer_rejected"


def disposition_row(row: pd.Series, events: pd.DataFrame, extra: dict, mass_keys: set) -> dict:
    """Disposition columns for one PR.

    Args:
        row: Identity row.
        events: This PR's events.
        extra: Absorbed columns and current labels for the PR.
        mass_keys: Output of mass_close_keys.

    How:
        Gathers evidence (duplicate marks/labels, closing comment, mass day) then classifies.

    Returns:
        Column dictionary.
    """
    day = row["resolved_at"].strftime(DATE_FORMAT) if pd.notna(row["resolved_at"]) else ""
    is_closed = row["state"] == "closed"
    mass = is_closed and row["closed_by"] != row["author"] and (row["closed_by"], day) in mass_keys
    actor, text = closing_comment(events, row["resolved_at"]) if is_closed else ("", "")
    label_events = events[(events["type"] == "labeled") & (events["details"].str.lower() == "duplicate")]
    has_duplicate_evidence = (bool((events["type"] == "marked_duplicate").any()) or len(label_events) > 0
                              or "duplicate" in [label.lower() for label in extra["labels"]]
                              or bool(extra["absorbed_loose"]) or bool(SUPERSEDED_RE.search(text)))
    flags = {"absorbed": bool(extra["absorbed"]), "duplicate_evidence": has_duplicate_evidence, "mass_closed": mass}
    disposition = classify(row, flags)
    maintainer_text = events[events["type"].isin(["comment", "review"]) & (events["actor_role"] == "maintainer")]
    terminal = terminal_comment_rows(events, row["resolved_at"], row["closed_by"])
    ambiguous = (is_closed and row["closed_by_role"] == "maintainer" and maintainer_text.empty
                 and disposition not in ("absorbed", "self_closed", "merged")
                 and not (events["type"] == "marked_duplicate").any())
    return {
        "disposition": disposition, "absorbed": flags["absorbed"], "absorbed_by": extra["absorbed_by"],
        "absorbed_via": extra["absorbed_via"], "success": disposition in ("merged", "absorbed"),
        "superseded_duplicate": disposition == "superseded_duplicate", "duplicate_evidence": has_duplicate_evidence,
        "mass_close_day": bool(mass), "mass_close_event": MASS_CLOSE_EVENT_DAY if mass and day == MASS_CLOSE_EVENT_DAY else "",
        "ambiguous_close": bool(ambiguous), "has_terminal_comment": len(terminal) > 0,
        "closing_comment_actor": actor, "closing_comment": text,
    }


def build_disposition(identity: pd.DataFrame, events_by_pr: dict, base: pd.DataFrame,
                      absorbed: pd.DataFrame) -> pd.DataFrame:
    """Disposition table for all PRs in `identity`.

    Args:
        identity: Output of build_identity.
        events_by_pr: Events grouped by number.
        base: Base table with current labels.
        absorbed: Table from load_absorbed.

    How:
        Looks up per-PR extras then calls disposition_row; PRs missing from the
        earlier absorbed table are treated as not absorbed.

    Returns:
        DataFrame indexed by number.
    """
    mass_keys = mass_close_keys(identity)
    empty_events = next(iter(events_by_pr.values())).iloc[:0]
    absorbed = absorbed.reindex(identity.index)
    rows = {}
    for number, row in identity.iterrows():
        absorbed_row = absorbed.loc[number]
        extra = {"labels": base.loc[number, "labels"] if number in base.index else [],
                 "absorbed": bool(absorbed_row["absorbed"]) if pd.notna(absorbed_row["absorbed"]) else False,
                 "absorbed_loose": bool(absorbed_row["absorbed_loose"]) if pd.notna(absorbed_row["absorbed_loose"]) else False,
                 "absorbed_by": absorbed_row["absorbed_by"], "absorbed_via": absorbed_row["absorbed_via"]}
        rows[number] = disposition_row(row, events_by_pr.get(number, empty_events), extra, mass_keys)
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index.name = "number"
    table["absorbed_by"] = table["absorbed_by"].astype("Int64")
    return table
