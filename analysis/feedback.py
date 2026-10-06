"""Responding to feedback (mostly E1 and E2): response latency, response kind, feedback type and timing."""

import numpy as np
import pandas as pd

from analysis.effects import adjusted_effects
from analysis.common import DERIVED, in_group, median_quartiles, rate
from funnel.constants import HOURS_PER_DAY, RESPONSE_WINDOW_DAYS, SECONDS_PER_HOUR

# Response latency buckets in hours: (label, lower inclusive, upper exclusive).
LATENCY_BUCKETS = [("<6h", 0, 6), ("6-24h", 6, 24), ("1-3d", 24, 72), ("3-7d", 72, 168), (">7d", 168, float("inf"))]
# A PR closed sooner than this after feedback gave the author no real chance to respond.
LANDMARK_HOURS = (HOURS_PER_DAY, RESPONSE_WINDOW_DAYS * HOURS_PER_DAY)
POSITIVE_PATTERN = (r"\b(lgtm|looks good|looks great|good to (?:go|merge)|will merge|ready to merge|ship it|"
                    r"nice work|great work|great job|approved)\b")
REQUEST_PATTERN = (r"\?|\b(please|could you|can you|would you|need to|needs to|should|have to|must|"
                   r"can't have|going to need)\b")
# The funnel build only watched for author replies for this many hours after feedback.
FULL_WINDOW_H = RESPONSE_WINDOW_DAYS * HOURS_PER_DAY


def feedback_cohort(df: pd.DataFrame) -> pd.DataFrame:
    """Select PRs with substantive maintainer feedback and a final decision, with response labels.

    Args:
        df: Community PRs from load_core.

    How:
        Response kind is derived from the funnel's list: pushed commits, replied only,
        edited only or nothing. Latency buckets use hours from feedback to the first reply.
        full_window marks PRs still open when the 7-day reply window ended; comparing
        only those avoids calling a PR "unanswered" because it was closed in under a day.

    Returns:
        The cohort with pushed_commits, replied_only, responded, full_window and latency columns.
    """
    cohort = df[df["has_feedback"] & df["decided"] & ~df["is_user_pr"]].copy()
    kinds = cohort["response_kinds"].map(lambda response_kinds: set(response_kinds) if response_kinds is not None else set())
    cohort["pushed_commits"] = kinds.map(lambda kind_set: "commit" in kind_set)
    cohort["replied_only"] = kinds.map(lambda kind_set: "comment" in kind_set and "commit" not in kind_set)
    cohort["responded"] = cohort["author_responded"].fillna(False).astype(bool)
    cohort["full_window"] = cohort["feedback_window_h"] >= FULL_WINDOW_H
    cohort["latency"] = "never"
    for label, lower, upper in LATENCY_BUCKETS:
        cohort.loc[cohort["responded"] & (cohort["response_hours"] >= lower) & (cohort["response_hours"] < upper), "latency"] = label
    return cohort


def _split(cohort: pd.DataFrame, column: str, order: list) -> dict:
    """Tabulate success rate by a categorical column, all and full-window only, per epoch group.

    Args:
        cohort: Output of feedback_cohort.
        column: Categorical column to split on.
        order: Values of the column to report, in order.

    How:
        Computes a rate for all epochs, E1, E2 and Quattro (E3 and E4), for all decided PRs and
        for full-window PRs only.

    Returns:
        Per subset and value: success rate per epoch group.
    """
    split = {}
    for name, part in [("all_decided", cohort), ("full_window_only", cohort[cohort["full_window"]])]:
        split[name] = {str(value): {"all": rate(part.loc[part[column] == value, "success"].astype(float)),
                                    "E1": rate(part.loc[(part[column] == value) & (part["epoch"] == "E1"), "success"].astype(float)),
                                    "E2": rate(part.loc[(part[column] == value) & (part["epoch"] == "E2"), "success"].astype(float)),
                                    "Quattro": rate(part.loc[(part[column] == value) & part["epoch"].isin(["E3", "E4"]), "success"].astype(float))}
                       for value in order}
    return split


def maintainer_tone(cohort: pd.DataFrame) -> pd.Series:
    """Classify the tone of the maintainer comment that counted as feedback.

    Args:
        cohort: Output of feedback_cohort.

    How:
        Looks up the comment text at feedback_at and matches POSITIVE_PATTERN, then REQUEST_PATTERN, on the lower-cased text.

    Returns:
        "positive", "request" or "other" per PR.
    """
    events = pd.read_parquet(DERIVED / "events.parquet", columns=["number", "ts", "actor_role", "substantive", "text"])
    events = events[events["number"].isin(cohort["number"]) & (events["actor_role"] == "maintainer") & events["substantive"]]
    events = events.merge(cohort[["number", "feedback_at"]], on="number")
    text = events[events["ts"] == events["feedback_at"]].groupby("number")["text"].first().reindex(cohort["number"]).fillna("").to_numpy()
    lowered = pd.Series(text, index=cohort.index).str.lower()
    return pd.Series(np.select([lowered.str.contains(POSITIVE_PATTERN, regex=True), lowered.str.contains(REQUEST_PATTERN, regex=True)],
                               ["positive", "request"], "other"), index=cohort.index)


def last_response_gap(cohort: pd.DataFrame) -> dict:
    """Measure hours from the author's last activity after feedback to the decision, merged versus not.

    Args:
        cohort: Output of feedback_cohort.

    How:
        If successes are decided right after small last responses, the maintainer may
        have been ready to merge anyway (reverse causality).

    Returns:
        Median and quartile hours for successes and non-successes.
    """
    events = pd.read_parquet(DERIVED / "events.parquet", columns=["number", "ts", "actor_role", "type"])
    events = events[events["number"].isin(cohort["number"]) & (events["actor_role"] == "author") & events["type"].isin(["commit", "comment", "force_push"])]
    events = events.merge(cohort[["number", "feedback_at", "resolved_at"]], on="number")
    events = events[(events["ts"] > events["feedback_at"]) & (events["ts"] <= events["resolved_at"])]
    last = events.groupby("number")["ts"].max()
    gap = (cohort["resolved_at"] - last.reindex(cohort["number"]).set_axis(cohort.index)).dt.total_seconds() / SECONDS_PER_HOUR
    return {"success": median_quartiles(gap[cohort["success"]]), "not_success": median_quartiles(gap[~cohort["success"]])}


def landmark(cohort: pd.DataFrame) -> dict:
    """Compare success by whether the author had replied by 24 h / 7 d, among PRs still open at that point.

    Args:
        cohort: Output of feedback_cohort.

    How:
        Starting the clock at the landmark removes the bias that quick decisions give
        authors no time to reply (and that fast merges need no reply).

    Returns:
        Per landmark: how many PRs were still open and the success rate with and without a reply.
    """
    by_landmark = {}
    for hours in LANDMARK_HOURS:
        alive = cohort[cohort["feedback_window_h"] >= hours]
        replied = alive["responded"] & (alive["response_hours"] < hours)
        by_landmark[f"{hours}h"] = {"still_open_n": int(len(alive)),
                                    "replied": rate(alive.loc[replied, "success"].astype(float)),
                                    "not_replied": rate(alive.loc[~replied, "success"].astype(float))}
    return by_landmark


def adjusted(cohort: pd.DataFrame) -> dict:
    """Estimate the adjusted effect (pp) of pushing commits and of replying at all, per group.

    Args:
        cohort: Output of feedback_cohort.

    How:
        Fits each response term with the feedback type as controls and keeps only the response terms.

    Returns:
        Per epoch group and response term: the effects summary.
    """
    cohort = cohort.assign(feedback_changes=(cohort["feedback_type"] == "changes_requested"),
                           feedback_review=(cohort["feedback_type"] == "review"), quick_close=~cohort["full_window"])
    by_group = {}
    for group in ["E1", "E2", "all"]:
        part = in_group(cohort, group)
        y = part["success"].astype(float)
        by_group[group] = {name: adjusted_effects(part, y, [], [name, "feedback_changes", "feedback_review"], drop=())
                           for name in ["pushed_commits", "responded"]}
        for summary in by_group[group].values():
            summary["effects"] = [effect for effect in summary["effects"] if effect["term"] in ("pushed_commits", "responded")]
    return by_group


def run(df: pd.DataFrame) -> dict:
    """Collect all feedback results for the JSON.

    Args:
        df: Community PRs from load_core.

    How:
        Builds the feedback cohort, labels tone and response kind, then runs each breakdown.

    Returns:
        Dict with the cohort summary and the breakdowns by latency, response kind, feedback type and tone.
    """
    cohort = feedback_cohort(df)
    cohort["tone"] = maintainer_tone(cohort)
    cohort["response_kind"] = np.select([cohort["pushed_commits"], cohort["replied_only"], cohort["responded"]], ["pushed commits", "replied only", "edited only"], "no response")
    return {
        "cohort": {"n_with_feedback": int((df["has_feedback"] & ~df["is_user_pr"]).sum()), "n_decided": int(len(cohort)),
                   "by_epoch": cohort["epoch"].value_counts().to_dict(), "n_full_window": int(cohort["full_window"].sum()),
                   "success_overall": rate(cohort["success"].astype(float))},
        "by_latency": _split(cohort, "latency", [bucket[0] for bucket in LATENCY_BUCKETS] + ["never"]),
        "by_response_kind": _split(cohort, "response_kind", ["pushed commits", "replied only", "edited only", "no response"]),
        "by_feedback_type": _split(cohort, "feedback_type", ["comment", "review", "changes_requested"]),
        "by_tone": _split(cohort, "tone", ["positive", "request", "other"]),
        "landmark": landmark(cohort), "last_response_to_decision_hours": last_response_gap(cohort), "adjusted": adjusted(cohort),
        "note": "Author replies were only recorded for 7 days after feedback; E3 and E4 have 48 feedback PRs, so stability across epochs is weak."}
