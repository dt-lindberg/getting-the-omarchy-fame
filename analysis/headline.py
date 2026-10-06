"""Headline numbers, funnel (sankey) counts, dispositions by epoch and the 2026-09-21 mass closure."""

import numpy as np
import pandas as pd

from analysis.data import DISPOSITIONS
from analysis.stats import aalen_johansen
from analysis.common import EPOCH_ORDER, median_quartiles, rate
from funnel.constants import MASS_CLOSE_EVENT_DAY

CURVE_DAYS = [7, 30, 90, 180, 365]
DISPOSITION_ORDER = DISPOSITIONS
REFERENCE_PATTERN = r"similar to #(\d+)"


def _per_epoch(df: pd.DataFrame, fn) -> dict:
    """Apply fn to each epoch's rows and to all rows (excluding the user's own PRs)."""
    base = df[~df["is_user_pr"]]
    return {**{e: fn(base[base["epoch"] == e]) for e in EPOCH_ORDER}, "all": fn(base)}


def headline(df: pd.DataFrame, all_prs: pd.DataFrame) -> dict:
    """Totals, success rates, waits, never-noticed share, mass-close size and open backlog."""
    decided = lambda d: d[d["decided"]]
    return {
        "total_prs": int(len(all_prs)), "community_prs": int(len(df)),
        "community_prs_excl_user": int((~df["is_user_pr"]).sum()),
        "decided": _per_epoch(df, lambda d: int(d["decided"].sum())),
        "success_among_decided": _per_epoch(df, lambda d: rate(decided(d)["success"].astype(float))),
        "success_among_all_submitted": _per_epoch(df, lambda d: rate(d["success"].astype(float))),
        "median_hours_to_engagement": _per_epoch(df, lambda d: median_quartiles(d["h_maintainer_engagement_nobulk"])),
        "median_hours_to_engagement_with_bulk": _per_epoch(df, lambda d: median_quartiles(d["h_maintainer_engagement"])),
        "never_engaged_before_close": _per_epoch(df, lambda d: rate(~decided(d)["eng"])),
        "never_engaged_before_close_with_bulk": _per_epoch(df, lambda d: rate(~decided(d)["eng_bulk"])),
        "mass_close_event": {"prs": int((all_prs["mass_close_event"] == MASS_CLOSE_EVENT_DAY).sum()),
                             "community_prs": int(df["mass_event"].sum()), "date": MASS_CLOSE_EVENT_DAY},
        "mass_closed_all_days_community": int(df["mass"].sum()),
        "open_community_now": _per_epoch(df, lambda d: int((~d["decided"]).sum())),
        "fetched_at": df.attrs["fetch_time"].isoformat(),
    }


def sankey(df: pd.DataFrame) -> dict:
    """Counts for submitted -> attention class -> final disposition (community PRs, user's own excluded).

    How:
        Attention class: engaged (bulk-free maintainer engagement), touched only by a
        bulk action, bot or community activity only, or nothing. The outcome is the
        final disposition with mass closures folded in; open means undecided.
    """
    d = df[~df["is_user_pr"]].copy()
    d["attention"] = np.select(
        [d["eng"], d["eng_bulk"], d["first_any_interaction"].notna()],
        ["maintainer engaged", "bulk maintainer action only", "bots or community only"], "no activity")
    d["outcome"] = d["disp"].where(d["decided"], "open")
    links = d.groupby(["attention", "outcome"]).size().reset_index(name="n")
    by_epoch = {e: d[d["epoch"] == e].groupby(["attention", "outcome"]).size().reset_index(name="n").to_dict("records")
                for e in EPOCH_ORDER}
    return {"submitted": int(len(d)), "attention": d["attention"].value_counts().to_dict(),
            "links": links.to_dict("records"), "links_by_epoch": by_epoch}


def disposition_tables(df: pd.DataFrame) -> dict:
    """Counts and shares per epoch, plus cumulative incidence of every disposition by days open."""
    d = df[~df["is_user_pr"]]
    counts = pd.crosstab(d["epoch"], d["disp"].where(d["decided"], "open")).reindex(columns=DISPOSITION_ORDER + ["open"], fill_value=0)
    counts.loc["all"] = counts.sum()
    cause_code = {name: i for i, name in enumerate(DISPOSITION_ORDER, start=1)}
    curves = {}
    for name in EPOCH_ORDER + ["all"]:
        part = d if name == "all" else d[d["epoch"] == name]
        cause = part["disp"].map(cause_code).where(part["decided"], 0).fillna(0).astype(int).to_numpy()
        curves[name] = aalen_johansen(part["follow_days"].to_numpy(float), cause, DISPOSITION_ORDER, CURVE_DAYS)
    return {"order": DISPOSITION_ORDER, "counts": counts.reset_index().rename(columns={"index": "epoch"}).to_dict("records"),
            "curves": curves, "curve_days": CURVE_DAYS,
            "note": "Mass-closed includes every PR flagged as part of the 2026-09-21 event plus other mass-close days. "
                    "Curves for a calendar event show a jump at one date, not an age effect."}


def _profile(part: pd.DataFrame, now: pd.Timestamp) -> dict:
    """Age, attention, author history, size and mix of a group of community PRs."""
    return {"n": int(len(part)), "age_days": median_quartiles((now - part["created_at"]).dt.total_seconds() / 86400),
            "ever_engaged": rate(part["eng"]), "ever_touched_by_maintainer": rate(part["first_maintainer_touch"].notna()),
            "had_bot_review_or_comment": rate(part["first_bot_interaction"].notna()),
            "first_pr": rate(part["first_pr"]), "author_prior_prs": median_quartiles(part["author_prior_prs"]),
            "lines_changed": median_quartiles(part["lines_changed"]), "has_rival": rate(part["direct_competitors"] > 0),
            "kind_share_pp": (part["kind"].value_counts(normalize=True) * 100).round(1).to_dict(),
            "top_topics_pp": (part["topic"].value_counts(normalize=True).head(5) * 100).round(1).to_dict()}


def mass_close(df: pd.DataFrame, prs: pd.DataFrame) -> dict:
    """Who and what the 2026-09-21 closure hit, against community PRs left open that day.

    How:
        Left-open = open at the start of the day and still open at its end, created
        before it. Each closure comment names the PR it duplicates; the status of
        those targets shows what the closures were measured against.
    """
    day = pd.Timestamp(MASS_CLOSE_EVENT_DAY, tz="UTC")
    d = df[~df["is_user_pr"]]
    event = d[d["mass_event"]]
    still_open = d[(d["created_at"] < day) & ~d["mass_event"] & (d["resolved_at"].isna() | (d["resolved_at"] >= day + pd.Timedelta(days=1)))]
    targets = event["closing_comment"].str.extract(REFERENCE_PATTERN)[0].dropna().astype(int)
    status = prs.set_index("number").loc[targets[targets.isin(prs["number"])], "disposition"]
    return {"closed": _profile(event, day), "left_open": _profile(still_open, day),
            "closed_by": event["closed_by"].value_counts().to_dict(),
            "closing_comment_cites_a_pr": rate(event["closing_comment"].str.contains(REFERENCE_PATTERN, regex=True)),
            "cited_target_status": status.value_counts().to_dict(),
            "cited_targets_distinct": int(targets.nunique())}


def run(df: pd.DataFrame, all_prs: pd.DataFrame) -> dict:
    """Headline, sankey, dispositions and mass-close composition for the JSON."""
    return {"headline": headline(df, all_prs), "sankey": sankey(df), "dispositions": disposition_tables(df),
            "mass_close": mass_close(df, all_prs)}
