"""Spot checks of the built tables against the raw GitHub dumps (independent counts)."""

from pathlib import Path

import pandas as pd

from funnel.constants import SAMPLE_SEED
from funnel.load import load_absorbed, load_base_prs
from funnel.reports.md import md_table

FIXED_PRS = [14049, 12814, 13914, 14148, 14220]
LINKED_ISSUE = 10289
DISPOSITION_PICKS = ["absorbed", "maintainer_rejected", "mass_closed", "superseded_duplicate", "merged", "self_closed"]
SPOT_CHECK_COUNT = 10
# Extra PRs picked from the same competition clusters as the fixed ones.
MAX_CLUSTER_PICKS = 3
TITLE_CHARS = 90
DETAIL_CHARS = 40
TIMELINE_HEAD, TIMELINE_TAIL, MAX_TIMELINE_ROWS = 8, 4, 40
NOTES_PATH = Path(__file__).with_name("spot_check_notes.md")


def pick_prs(prs: pd.DataFrame, events: pd.DataFrame, snapshots: pd.DataFrame) -> list[int]:
    """Pick the PRs to spot-check by hand.

    Args:
        prs: PR table.
        events: Events table.
        snapshots: Snapshots table.

    How:
        Linked = closing-reference/cross-reference/body mention of #10289 (it is an issue,
        so it is not a row itself). Remaining slots are filled with one random community
        PR per disposition (fixed seed) so every rule gets a manual look.

    Returns:
        The fixed PRs, PRs linked to #10289, then one community PR per disposition, capped at SPOT_CHECK_COUNT.
    """
    present = set(prs["number"])
    chosen = [number for number in FIXED_PRS if number in present]
    opened = snapshots[snapshots["stage"] == "open"]
    linked = events.loc[events["ref"] == LINKED_ISSUE, "number"].tolist()
    linked += opened.loc[opened["body"].str.contains(rf"#{LINKED_ISSUE}\b", regex=True), "number"].tolist()
    community = prs[prs["author_group"] == "community"]
    cluster = community[community["number"].isin(chosen)]["competition_cluster_id"].dropna()
    linked += community.loc[community["competition_cluster_id"].isin(cluster), "number"].head(MAX_CLUSTER_PICKS).tolist()
    for name in DISPOSITION_PICKS:
        group = community[community["disposition"] == name]
        linked += group.sample(1, random_state=SAMPLE_SEED)["number"].tolist() if len(group) else []
    for number in linked:
        if number not in chosen and number in present and len(chosen) < SPOT_CHECK_COUNT:
            chosen.append(number)
    return chosen


def check_pr(row: pd.Series, events: pd.DataFrame, snaps: pd.DataFrame, base: pd.Series,
             outcome: str | None) -> dict[str, bool]:
    """Named checks of one PR's derived rows against the raw base dump and prs.csv.

    Args:
        row: prs row.
        events: This PR's events.
        snaps: This PR's snapshots.
        base: Base dump row (totals, raw dates).
        outcome: prs.csv outcome (merged/absorbed/closed/open) or None.

    How:
        Compares times and event counts with the raw totals; review events may
        be fewer than the raw total because reply-only reviews are not on the timeline.

    Returns:
        Check name mapped to whether it passed.
    """
    created_ok = pd.Timestamp(base["created_at_raw"]) == row["created_at"]
    closed_raw = base["closed_at_raw"]
    resolved_ok = (pd.isna(row["resolved_at"]) and not closed_raw) or (
        bool(closed_raw) and pd.Timestamp(closed_raw) == row["resolved_at"])
    edited = (events["type"] == "body_edit").any()
    open_body = snaps.loc[snaps["stage"] == "open", "body"].iloc[0]
    final_body = snaps.loc[snaps["stage"] == "final", "body"].iloc[0]
    expected = {"merged": "merged", "absorbed": "absorbed", "open": "open"}.get(outcome)
    return {
        "created_at equals raw": bool(created_ok),
        "resolved_at equals raw closedAt": bool(resolved_ok),
        "comment events equal raw comment total": int((events["type"] == "comment").sum()) == base["comments_total"],
        # Reply-only reviews (answers inside inline threads) are missing from the timeline.
        "review events at most raw review total": int((events["type"] == "review").sum()) <= base["reviews_total"],
        "commit events equal raw commit total": int((events["type"] == "commit").sum()) == base["commits_total"],
        "open body differs from final only if edited": (open_body != final_body) == bool(edited) or not edited,
        "disposition agrees with prs.csv": (row["disposition"] == expected) if expected else
        row["disposition"] not in ("merged", "absorbed", "open"),
    }


def timeline_lines(events: pd.DataFrame) -> list[str]:
    """Render a compact event timeline as a markdown table.

    Args:
        events: One PR's events.

    How:
        Drops commits and plain references, keeps the first TIMELINE_HEAD and last
        TIMELINE_TAIL events plus every maintainer or terminal event, capped at MAX_TIMELINE_ROWS.

    Returns:
        Markdown table lines.
    """
    shown = events[~events["type"].isin(["commit", "referenced"])]
    key = (shown["actor_role"] == "maintainer") | shown["type"].isin(["closed", "merged", "renamed_title"])
    pick = shown[shown.index.isin(shown.head(TIMELINE_HEAD).index) | key | shown.index.isin(shown.tail(TIMELINE_TAIL).index)]
    frame = pick.head(MAX_TIMELINE_ROWS)[["ts", "type", "actor", "actor_role", "details", "substantive"]].copy()
    frame["ts"] = frame["ts"].dt.strftime("%m-%d %H:%M:%S")
    frame["details"] = frame["details"].str.slice(0, DETAIL_CHARS)
    return md_table(frame, index=False)


def validation_section(prs: pd.DataFrame, events: pd.DataFrame, snapshots: pd.DataFrame) -> list[str]:
    """Markdown for the spot-check section.

    Args:
        prs: PR table.
        events: Events table.
        snapshots: Snapshots table.

    How:
        Runs check_pr on each picked PR, tabulates pass/fail, then prints key derived
        columns and an event timeline per PR; hand-written notes are appended if present.

    Returns:
        Markdown lines.
    """
    base = load_base_prs()
    absorbed = load_absorbed()
    outcome = {number: ("absorbed" if is_absorbed else None) for number, is_absorbed in absorbed["absorbed"].items()}
    summary_rows, detail = [], []
    for number in pick_prs(prs, events, snapshots):
        row = prs[prs["number"] == number].iloc[0]
        pr_events = events[events["number"] == number]
        checks = check_pr(row, pr_events, snapshots[snapshots["number"] == number], base.loc[number],
                          outcome.get(number) or {"merged": "merged", "open": "open"}.get(row["state"]))
        failed = [name for name, passed in checks.items() if not passed]
        summary_rows.append({"number": number, "author": row["author"], "disposition": row["disposition"],
                             "checks passed": f"{len(checks) - len(failed)}/{len(checks)}",
                             "failed": "; ".join(failed)})
        detail += [f"### #{number}: {row['title'][:TITLE_CHARS]}", "",
                   f"author {row['author']} ({row['author_group']}), epoch {row['epoch']}, created {row['created_at']:%Y-%m-%d %H:%M}, "
                   f"disposition **{row['disposition']}**, closed by {row['closed_by']}, "
                   f"h to touch {row['h_maintainer_touch']:.1f}, h to engagement {row['h_maintainer_engagement']:.1f}, "
                   f"silent_decision {row['silent_decision']}, cluster {row['competition_cluster_id']} "
                   f"(size {row['cluster_size']}), feedback {row['feedback_type']}, responded {row['author_responded']}.", ""
                   ] + timeline_lines(pr_events) + [""]
    lines = ["## Spot checks", "",
             "Automatic checks compare the derived rows with the raw dumps (omarchy-pr-stats prs_*.jsonl and prs.csv): "
             "creation and close times, comment/review/commit totals, body history, disposition.", ""]
    lines += md_table(pd.DataFrame(summary_rows), index=False) + [""] + detail
    if NOTES_PATH.exists():
        lines += ["### Manual review notes", "", NOTES_PATH.read_text().strip(), ""]
    return lines
