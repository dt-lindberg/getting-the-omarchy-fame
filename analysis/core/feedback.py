"""Responding to feedback (mostly E1 and E2): response latency, response kind, feedback type and timing."""

import numpy as np
import pandas as pd

from analysis.context.effects import adjusted_effects
from analysis.core.common import DERIVED, in_group, median_quartiles, rate
from analysis.feedback.constants import LANDMARK_HOURS, LATENCY_BUCKETS, POSITIVE_PATTERN, REQUEST_PATTERN

# The funnel build only watched for author replies for this many hours after feedback.
FULL_WINDOW_H = 168


def feedback_cohort(df: pd.DataFrame) -> pd.DataFrame:
    """PRs with substantive maintainer feedback and a final decision, with response labels.

    How:
        Response kind is derived from the funnel's list: pushed commits, replied only,
        edited only or nothing. Latency buckets use hours from feedback to the first reply.
        full_window marks PRs still open when the 7-day reply window ended; comparing
        only those avoids calling a PR "unanswered" because it was closed in under a day.
    """
    f = df[df["has_feedback"] & df["decided"] & ~df["is_user_pr"]].copy()
    kinds = f["response_kinds"].map(lambda a: set(a) if a is not None else set())
    f["pushed_commits"] = kinds.map(lambda k: "commit" in k)
    f["replied_only"] = kinds.map(lambda k: "comment" in k and "commit" not in k)
    f["responded"] = f["author_responded"].fillna(False).astype(bool)
    f["full_window"] = f["feedback_window_h"] >= FULL_WINDOW_H
    f["latency"] = "never"
    for label, lo, hi in LATENCY_BUCKETS:
        f.loc[f["responded"] & (f["response_hours"] >= lo) & (f["response_hours"] < hi), "latency"] = label
    return f


def _split(f: pd.DataFrame, column: str, order: list) -> dict:
    """Success rate by a categorical column, all and full-window only, per epoch pair."""
    out = {}
    for name, part in [("all_decided", f), ("full_window_only", f[f["full_window"]])]:
        out[name] = {str(v): {"all": rate(part.loc[part[column] == v, "success"].astype(float)),
                              "E1": rate(part.loc[(part[column] == v) & (part["epoch"] == "E1"), "success"].astype(float)),
                              "E2": rate(part.loc[(part[column] == v) & (part["epoch"] == "E2"), "success"].astype(float)),
                              "Quattro": rate(part.loc[(part[column] == v) & part["epoch"].isin(["E3", "E4"]), "success"].astype(float))}
                     for v in order}
    return out


def maintainer_tone(f: pd.DataFrame) -> pd.Series:
    """Positive / request / other, from the wording of the maintainer comment that counted as feedback."""
    ev = pd.read_parquet(DERIVED / "events.parquet", columns=["number", "ts", "actor_role", "substantive", "text"])
    ev = ev[ev["number"].isin(f["number"]) & (ev["actor_role"] == "maintainer") & ev["substantive"]]
    ev = ev.merge(f[["number", "feedback_at"]], on="number")
    text = ev[ev["ts"] == ev["feedback_at"]].groupby("number")["text"].first().reindex(f["number"]).fillna("").to_numpy()
    s = pd.Series(text, index=f.index).str.lower()
    return pd.Series(np.select([s.str.contains(POSITIVE_PATTERN, regex=True), s.str.contains(REQUEST_PATTERN, regex=True)],
                               ["positive", "request"], "other"), index=f.index)


def last_response_gap(f: pd.DataFrame) -> dict:
    """Hours from the author's last activity after feedback to the decision, merged versus not.

    How:
        If successes are decided right after small last responses, the maintainer may
        have been ready to merge anyway (reverse causality).
    """
    ev = pd.read_parquet(DERIVED / "events.parquet", columns=["number", "ts", "actor_role", "type"])
    ev = ev[ev["number"].isin(f["number"]) & (ev["actor_role"] == "author") & ev["type"].isin(["commit", "comment", "force_push"])]
    ev = ev.merge(f[["number", "feedback_at", "resolved_at"]], on="number")
    ev = ev[(ev["ts"] > ev["feedback_at"]) & (ev["ts"] <= ev["resolved_at"])]
    last = ev.groupby("number")["ts"].max()
    gap = (f["resolved_at"] - last.reindex(f["number"]).set_axis(f.index)).dt.total_seconds() / 3600
    return {"success": median_quartiles(gap[f["success"]]), "not_success": median_quartiles(gap[~f["success"]])}


def landmark(f: pd.DataFrame) -> dict:
    """Success by whether the author had replied by 24 h / 7 d, among PRs still open at that point.

    How:
        Starting the clock at the landmark removes the bias that quick decisions give
        authors no time to reply (and that fast merges need no reply).
    """
    out = {}
    for hours in LANDMARK_HOURS:
        alive = f[f["feedback_window_h"] >= hours]
        replied = alive["responded"] & (alive["response_hours"] < hours)
        out[f"{hours}h"] = {"still_open_n": int(len(alive)),
                            "replied": rate(alive.loc[replied, "success"].astype(float)),
                            "not_replied": rate(alive.loc[~replied, "success"].astype(float))}
    return out


def adjusted(f: pd.DataFrame) -> dict:
    """Adjusted effect (pp) of pushing commits and of replying at all, among full-window PRs, per group."""
    f = f.assign(feedback_changes=(f["feedback_type"] == "changes_requested"), feedback_review=(f["feedback_type"] == "review"),
                 quick_close=~f["full_window"])
    out = {}
    for group in ["E1", "E2", "all"]:
        part = in_group(f, group)
        y = part["success"].astype(float)
        out[group] = {name: adjusted_effects(part, y, [], [name, "feedback_changes", "feedback_review"], drop=())
                      for name in ["pushed_commits", "responded"]}
        for res in out[group].values():
            res["effects"] = [e for e in res["effects"] if e["term"] in ("pushed_commits", "responded")]
    return out


def run(df: pd.DataFrame) -> dict:
    """All feedback results for the JSON."""
    f = feedback_cohort(df)
    f["tone"] = maintainer_tone(f)
    f["response_kind"] = np.select([f["pushed_commits"], f["replied_only"], f["responded"]], ["pushed commits", "replied only", "edited only"], "no response")
    return {
        "cohort": {"n_with_feedback": int((df["has_feedback"] & ~df["is_user_pr"]).sum()), "n_decided": int(len(f)),
                   "by_epoch": f["epoch"].value_counts().to_dict(), "n_full_window": int(f["full_window"].sum()),
                   "success_overall": rate(f["success"].astype(float))},
        "by_latency": _split(f, "latency", [b[0] for b in LATENCY_BUCKETS] + ["never"]),
        "by_response_kind": _split(f, "response_kind", ["pushed commits", "replied only", "edited only", "no response"]),
        "by_feedback_type": _split(f, "feedback_type", ["comment", "review", "changes_requested"]),
        "by_tone": _split(f, "tone", ["positive", "request", "other"]),
        "landmark": landmark(f), "last_response_to_decision_hours": last_response_gap(f), "adjusted": adjusted(f),
        "note": "Author replies were only recorded for 7 days after feedback; E3 and E4 have 48 feedback PRs, so stability across epochs is weak."}
