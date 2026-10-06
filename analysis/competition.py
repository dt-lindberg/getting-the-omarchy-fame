"""Competition between PRs: first versus later, open rivals at creation, cluster outcomes, gaps.

Uses one-hop `direct_competitors*` for effects and capped clusters for descriptive
comparisons because transitive clusters chain through absorbing PRs (largest 258).
"""

import numpy as np
import pandas as pd

from analysis.data import ATTENTION_WINDOW_DAYS, EPOCH_ORDER, GROUPS, engaged_within, in_group, load_prs
from analysis.effects import adjusted_effects
from funnel.competition import MIN_CLUSTER_SIZE
from funnel.constants import SECONDS_PER_DAY

SMALL_CLUSTER_MAX = 10
RIVAL_CONTROLS = ("direct_competitors_open_at_creation",)
# The upper bound 99 of the last bucket stands in for "no limit".
RIVAL_BUCKETS = [(0, 0, "0"), (1, 1, "1"), (2, 99, "2+")]


def with_cluster_rank(community: pd.DataFrame) -> pd.DataFrame:
    """Add each PR's arrival order inside its cluster, counted over all authors.

    Args:
        community: Community PRs from load_core.

    How:
        Ranks by creation time over every PR in the cluster (core and bots
        included) so "first" means first to arrive, not first community PR.

    Returns:
        The table with a `rank` column (1 for PRs outside clusters).
    """
    everyone = load_prs()[["number", "competition_cluster_id", "created_at"]].dropna()
    everyone["rank"] = everyone.groupby("competition_cluster_id")["created_at"].rank(method="first")
    ranked = community.merge(everyone[["number", "rank"]], on="number", how="left")
    ranked["rank"] = ranked["rank"].fillna(1)
    return ranked


def _rate_table(df: pd.DataFrame, by: pd.Series, labels: list[str]) -> dict:
    """Tabulate the success rate among decided PRs for each label of a grouping.

    Args:
        df: Community PRs.
        by: Group label per row, aligned with df.
        labels: Labels to report.

    How:
        Keeps decided rows of each label and takes the mean success in percentage points.

    Returns:
        Per label: n_decided and success_pp (None when empty).
    """
    rates = {}
    for label in labels:
        part = df[(by == label) & df["decided"]]
        rates[label] = {"n_decided": int(len(part)),
                        "success_pp": float(part["success"].mean() * 100) if len(part) else None}
    return rates


def first_vs_later(df: pd.DataFrame) -> dict:
    """Compare success by arrival order in small clusters, per epoch group.

    Args:
        df: Community PRs with `rank` from with_cluster_rank.

    How:
        Uses clusters of MIN_CLUSTER_SIZE to SMALL_CLUSTER_MAX PRs and compares later arrivals with the first
        among decided PRs, with adjusted effects.

    Returns:
        Per epoch group: success rates by position and the adjusted effect of arriving later.
    """
    small = df[df["cluster_size"].between(MIN_CLUSTER_SIZE, SMALL_CLUSTER_MAX)].copy()
    small["position"] = np.select([small["rank"] == 1, small["rank"] == 2], ["first", "second"], "third_or_later")
    by_group = {}
    for group in GROUPS:
        part = in_group(small, group)
        later = (part["position"] != "first").astype(float)
        part = part.assign(later=later)
        decided = part[part["decided"]]
        by_group[group] = {
            "rates": _rate_table(part, part["position"], ["first", "second", "third_or_later"]),
            "later_vs_first": adjusted_effects(decided, decided["success"].astype(float), [], ["later"]),
        }
    return by_group


def rivals_at_creation(df: pd.DataFrame) -> dict:
    """Estimate the effect of direct rivals already open at creation on engagement (14 d) and success.

    Args:
        df: Community PRs with cluster columns.

    How:
        Tabulates outcomes by rival count bucket, then fits adjusted effects of having any rival
        (and of the cluster's open competitors) per epoch group.

    Returns:
        Dict with `buckets` and `effects` per epoch group.
    """
    rivals = df["direct_competitors_open_at_creation"]
    data = df.assign(has_rival=(rivals >= 1).astype(float), engaged14=engaged_within(df, ATTENTION_WINDOW_DAYS))
    result = {"buckets": {}, "effects": {}}
    for group in GROUPS:
        part = in_group(data, group)
        result["buckets"][group] = {}
        for lo, hi, label in RIVAL_BUCKETS:
            sel = part[rivals.loc[part.index].between(lo, hi)]
            dec = sel[sel["decided"]]
            result["buckets"][group][label] = {
                "n": int(len(sel)), "n_decided": int(len(dec)),
                "success_pp": float(dec["success"].mean() * 100) if len(dec) else None,
                "engaged14_pp": float(sel["engaged14"].mean() * 100) if sel["engaged14"].notna().any() else None}
        decided = part[part["decided"]]
        result["effects"][group] = {
            "has_rival_success": adjusted_effects(decided, decided["success"].astype(float), [], ["has_rival"], drop=RIVAL_CONTROLS),
            "has_rival_engaged14": adjusted_effects(part, part["engaged14"], [], ["has_rival"], drop=RIVAL_CONTROLS),
            "cluster_competing_success": adjusted_effects(decided, decided["success"].astype(float),
                                                          ["competing_open_at_creation"], [], drop=RIVAL_CONTROLS),
        }
    return result


def cluster_outcomes(df: pd.DataFrame) -> dict:
    """Measure how often a cluster ends in a success, for small clusters with 2+ community PRs.

    Args:
        df: Community PRs with cluster columns.

    How:
        "Fully decided" clusters have no open community PR left, which avoids
        counting an unfinished cluster as a failure.

    Returns:
        Cluster counts, success shares overall and per epoch, and a summary of larger clusters.
    """
    multi = df[df["cluster_size"].between(MIN_CLUSTER_SIZE, SMALL_CLUSTER_MAX)]
    grouped = multi.groupby("competition_cluster_id").agg(
        n=("number", "size"), any_success=("success", "max"), any_open=("decided", lambda decided: not decided.all()),
        epoch=("epoch", "first"))
    grouped = grouped[grouped["n"] >= MIN_CLUSTER_SIZE]
    done = grouped[~grouped["any_open"]]
    result = {"clusters": int(len(grouped)), "fully_decided": int(len(done)),
           "success_share_decided_pp": float(done["any_success"].mean() * 100),
           "success_share_all_pp": float(grouped["any_success"].mean() * 100), "by_epoch": {}}
    for epoch in EPOCH_ORDER:
        part = done[done["epoch"] == epoch]
        result["by_epoch"][epoch] = {"n": int(len(part)),
                                     "success_share_pp": float(part["any_success"].mean() * 100) if len(part) else None}
    big = df[df["cluster_size"] > SMALL_CLUSTER_MAX]
    result["large_clusters"] = {"community_prs": int(len(big)), "clusters": int(big["competition_cluster_id"].nunique()),
                                "success_pp_decided": float(big[big["decided"]]["success"].mean() * 100)}
    return result


def arrival_gaps(df: pd.DataFrame) -> dict:
    """Measure the days between competing PRs in small clusters.

    Args:
        df: Community PRs (unused; the gaps use all authors from the full table).

    How:
        Over all authors in clusters of MIN_CLUSTER_SIZE to SMALL_CLUSTER_MAX PRs, takes gaps between
        consecutive arrivals and between the first and second arrival.

    Returns:
        Median and quartile days with counts, for consecutive and first-to-second gaps.
    """
    everyone = load_prs()
    small = everyone[everyone["cluster_size"].between(MIN_CLUSTER_SIZE, SMALL_CLUSTER_MAX)].sort_values("created_at")
    gaps = small.groupby("competition_cluster_id")["created_at"].diff().dropna().dt.total_seconds() / SECONDS_PER_DAY
    firsts = small.groupby("competition_cluster_id")["created_at"].apply(
        lambda times: (times.iloc[1] - times.iloc[0]).total_seconds() / SECONDS_PER_DAY if len(times) > 1 else np.nan).dropna()
    summarise_days = lambda days: {"median_days": float(days.median()), "p25": float(days.quantile(.25)),
                                   "p75": float(days.quantile(.75)), "n": int(len(days))}
    return {"consecutive": summarise_days(gaps), "first_to_second": summarise_days(firsts)}


def run(df: pd.DataFrame) -> dict:
    """Collect all competition results for the JSON.

    Args:
        df: Community PRs from load_core.

    How:
        Adds cluster ranks, then runs the four competition analyses.

    Returns:
        Dict with first_vs_later, rivals_at_creation, cluster_outcomes and gaps.
    """
    ranked = with_cluster_rank(df)
    return {"first_vs_later": first_vs_later(ranked), "rivals_at_creation": rivals_at_creation(ranked),
            "cluster_outcomes": cluster_outcomes(ranked), "gaps": arrival_gaps(ranked)}
