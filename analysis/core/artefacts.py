"""Triage artefacts (labels, bot comments, review requests, reactions) and maintainer rewrites."""

import numpy as np
import pandas as pd

from analysis.core.common import DERIVED, in_group, median_quartiles, rate

LABELS_OF_INTEREST = ["verified", "ready", "bug", "enhancement", "duplicate", "compatibility", "documentation"]
EVENT_COLUMNS = ["number", "ts", "type", "actor", "actor_role", "details", "bulk"]
# Artefact name -> predicate over the event table.
ARTEFACTS = {
    **{f"label: {name}": (lambda e, n=name: (e["type"] == "labeled") & (e["details"] == n)) for name in LABELS_OF_INTEREST},
    "omarchybot comment": lambda e: (e["type"] == "comment") & (e["actor"] == "omarchybot"),
    "AI code review (copilot, greptile)": lambda e: (e["type"] == "review") & e["actor"].str.contains("copilot|greptile", regex=True),
    "maintainer review request (individual)": lambda e: (e["type"] == "review_requested") & (e["actor_role"] == "maintainer") & ~e["bulk"],
    "maintainer review request (bulk)": lambda e: (e["type"] == "review_requested") & (e["actor_role"] == "maintainer") & e["bulk"],
    "maintainer reaction": lambda e: (e["type"] == "reaction") & (e["actor_role"] == "maintainer"),
    "assignment": lambda e: e["type"] == "assigned",
}


def first_times(df: pd.DataFrame) -> pd.DataFrame:
    """First timestamp of each artefact per PR, as a wide table indexed by PR number."""
    ev = pd.read_parquet(DERIVED / "events.parquet", columns=EVENT_COLUMNS)
    ev = ev[ev["number"].isin(df["number"])]
    cols = {}
    for name, predicate in ARTEFACTS.items():
        hit = ev[predicate(ev)]
        cols[name] = hit.groupby("number")["ts"].min()
    return pd.DataFrame(cols).reindex(df["number"])


def artefact_table(df: pd.DataFrame) -> list[dict]:
    """Per artefact: success with and without it (before the decision), and hours before the decision.

    How:
        Only decided PRs. An artefact counts when its first occurrence is on or
        before the decision time; later ones (bot labels on closed PRs) are ignored.
        Hours-before-decision is shown for successes and non-successes separately.
    """
    d = df[df["decided"] & ~df["is_user_pr"]]
    first = first_times(d).set_axis(d.index)
    rows = []
    for name in ARTEFACTS:
        has = first[name].notna() & (first[name] <= d["resolved_at"])
        gap = (d["resolved_at"] - first[name]).dt.total_seconds() / 3600
        row = {"artefact": name, "n_with": int(has.sum()), "share_of_decided_pp": float(has.mean() * 100),
               "hours_before_decision": {"success": median_quartiles(gap[has & d["success"]]),
                                         "not_success": median_quartiles(gap[has & ~d["success"]])}}
        for group in ["E1", "E2", "Quattro", "all"]:
            sel = d.index.isin(in_group(d, group).index)
            row[group] = {"with": rate(d.loc[has & sel, "success"].astype(float)),
                          "without": rate(d.loc[~has & sel, "success"].astype(float))}
        rows.append(row)
    return rows


def rewrites(df: pd.DataFrame) -> dict:
    """How often maintainers renamed or edited the body of community PRs, with every title example."""
    d = df[~df["is_user_pr"]]
    acc = d[d["success"]]
    ren = d[d["maintainer_renamed_title"]]
    by_epoch = {e: {"accepted": int((acc["epoch"] == e).sum()),
                    "title_rewritten": int(((acc["epoch"] == e) & acc["maintainer_renamed_title"]).sum()),
                    "body_edited": int(((acc["epoch"] == e) & acc["maintainer_edited_body"]).sum())}
                for e in ["E1", "E2", "E3", "E4"]}
    examples = [{"number": int(r.number), "epoch": str(r.epoch), "accepted": bool(r.success), "disposition": r.disp,
                 "before": r.title_before_rename, "after": r.title_after_rename}
                for r in ren.sort_values("number").itertuples()]
    return {"accepted": int(len(acc)), "accepted_title_rewritten": int(acc["maintainer_renamed_title"].sum()),
            "accepted_body_edited": int(acc["maintainer_edited_body"].sum()),
            "all_community_title_rewritten": int(len(ren)), "all_community_body_edited": int(d["maintainer_edited_body"].sum()),
            "by_epoch": by_epoch, "examples": examples,
            "body_edited_numbers_accepted": [int(n) for n in acc.loc[acc["maintainer_edited_body"], "number"]][:40]}


def run(df: pd.DataFrame) -> dict:
    """Artefact and rewrite results for the JSON."""
    return {"artefacts": artefact_table(df), "rewrites": rewrites(df)}
