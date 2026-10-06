"""Competition between PRs: first versus later, open rivals at creation, cluster outcomes, gaps.

Uses one-hop `direct_competitors*` for effects and capped clusters for descriptive
comparisons because transitive clusters chain through absorbing PRs (largest 258).
"""

import numpy as np
import pandas as pd

from analysis.context.data import EPOCH_ORDER, GROUPS, engaged_within, in_group, load_prs
from analysis.context.effects import adjusted_effects

SMALL_CLUSTER_MAX = 10
RIVAL_CONTROLS = ("direct_competitors_open_at_creation",)
RIVAL_BUCKETS = [(0, 0, "0"), (1, 1, "1"), (2, 99, "2+")]


def with_cluster_rank(community: pd.DataFrame) -> pd.DataFrame:
    """Add each PR's arrival order inside its cluster, counted over all authors.

    How:
        Ranks by creation time over every PR in the cluster (core and bots
        included) so "first" means first to arrive, not first community PR.
    """
    everyone = load_prs()[["number", "competition_cluster_id", "created_at"]].dropna()
    everyone["rank"] = everyone.groupby("competition_cluster_id")["created_at"].rank(method="first")
    out = community.merge(everyone[["number", "rank"]], on="number", how="left")
    out["rank"] = out["rank"].fillna(1)
    return out


def _rate_table(df: pd.DataFrame, by: pd.Series, labels: list[str]) -> dict:
    """Success rate (pp) among decided PRs, with counts, for each label of `by`."""
    out = {}
    for label in labels:
        part = df[(by == label) & df["decided"]]
        out[label] = {"n_decided": int(len(part)),
                      "success_pp": float(part["success"].mean() * 100) if len(part) else None}
    return out


def first_vs_later(df: pd.DataFrame) -> dict:
    """Success among decided PRs by arrival order in clusters of 2 to 10 PRs, per epoch group."""
    small = df[df["cluster_size"].between(2, SMALL_CLUSTER_MAX)].copy()
    small["position"] = np.select([small["rank"] == 1, small["rank"] == 2], ["first", "second"], "third_or_later")
    out = {}
    for group in GROUPS:
        part = in_group(small, group)
        later = (part["position"] != "first").astype(float)
        part = part.assign(later=later)
        decided = part[part["decided"]]
        out[group] = {
            "rates": _rate_table(part, part["position"], ["first", "second", "third_or_later"]),
            "later_vs_first": adjusted_effects(decided, decided["success"].astype(float), [], ["later"]),
        }
    return out


def rivals_at_creation(df: pd.DataFrame) -> dict:
    """Effect of direct rivals already open at creation on engagement (14 d) and success."""
    rivals = df["direct_competitors_open_at_creation"]
    data = df.assign(has_rival=(rivals >= 1).astype(float), engaged14=engaged_within(df, 14))
    out = {"buckets": {}, "effects": {}}
    for group in GROUPS:
        part = in_group(data, group)
        out["buckets"][group] = {}
        for lo, hi, label in RIVAL_BUCKETS:
            sel = part[rivals.loc[part.index].between(lo, hi)]
            dec = sel[sel["decided"]]
            out["buckets"][group][label] = {
                "n": int(len(sel)), "n_decided": int(len(dec)),
                "success_pp": float(dec["success"].mean() * 100) if len(dec) else None,
                "engaged14_pp": float(sel["engaged14"].mean() * 100) if sel["engaged14"].notna().any() else None}
        decided = part[part["decided"]]
        out["effects"][group] = {
            "has_rival_success": adjusted_effects(decided, decided["success"].astype(float), [], ["has_rival"], drop=RIVAL_CONTROLS),
            "has_rival_engaged14": adjusted_effects(part, part["engaged14"], [], ["has_rival"], drop=RIVAL_CONTROLS),
            "cluster_competing_success": adjusted_effects(decided, decided["success"].astype(float),
                                                          ["competing_open_at_creation"], [], drop=RIVAL_CONTROLS),
        }
    return out


def cluster_outcomes(df: pd.DataFrame) -> dict:
    """How often a cluster ends in a success, for small clusters with 2+ community PRs.

    How:
        "Fully decided" clusters have no open community PR left, which avoids
        counting an unfinished cluster as a failure.
    """
    multi = df[df["cluster_size"].between(2, SMALL_CLUSTER_MAX)]
    grouped = multi.groupby("competition_cluster_id").agg(
        n=("number", "size"), any_success=("success", "max"), any_open=("decided", lambda s: not s.all()),
        epoch=("epoch", "first"))
    grouped = grouped[grouped["n"] >= 2]
    done = grouped[~grouped["any_open"]]
    out = {"clusters": int(len(grouped)), "fully_decided": int(len(done)),
           "success_share_decided_pp": float(done["any_success"].mean() * 100),
           "success_share_all_pp": float(grouped["any_success"].mean() * 100), "by_epoch": {}}
    for ep in EPOCH_ORDER:
        part = done[done["epoch"] == ep]
        out["by_epoch"][ep] = {"n": int(len(part)),
                               "success_share_pp": float(part["any_success"].mean() * 100) if len(part) else None}
    big = df[df["cluster_size"] > SMALL_CLUSTER_MAX]
    out["large_clusters"] = {"community_prs": int(len(big)), "clusters": int(big["competition_cluster_id"].nunique()),
                             "success_pp_decided": float(big[big["decided"]]["success"].mean() * 100)}
    return out


def arrival_gaps(df: pd.DataFrame) -> dict:
    """Days between competing PRs in clusters of 2 to 10 (all authors), overall and first to second."""
    everyone = load_prs()
    small = everyone[everyone["cluster_size"].between(2, SMALL_CLUSTER_MAX)].sort_values("created_at")
    gaps = small.groupby("competition_cluster_id")["created_at"].diff().dropna().dt.total_seconds() / 86400
    firsts = small.groupby("competition_cluster_id")["created_at"].apply(
        lambda s: (s.iloc[1] - s.iloc[0]).total_seconds() / 86400 if len(s) > 1 else np.nan).dropna()
    quant = lambda s: {"median_days": float(s.median()), "p25": float(s.quantile(.25)), "p75": float(s.quantile(.75)),
                       "n": int(len(s))}
    return {"consecutive": quant(gaps), "first_to_second": quant(firsts)}


def run(df: pd.DataFrame) -> dict:
    """All competition results for the JSON."""
    ranked = with_cluster_rank(df)
    return {"first_vs_later": first_vs_later(ranked), "rivals_at_creation": rivals_at_creation(ranked),
            "cluster_outcomes": cluster_outcomes(ranked), "gaps": arrival_gaps(ranked)}
