"""Context at submission: competition, backlog, maintainer activity and dhh focus on the same area."""

import pandas as pd

from analysis import competition
from analysis.common import GROUP_NAMES, in_group, rate

# Context variables are split into this many equal-sized bands.
QUARTILES = 4
CONTEXT_VARIABLES = ["backlog_open_community", "arrivals_prev7d", "maintainer_events_prev7d",
                     "dhh_focus_same_area_14d", "core_commits_prev7d"]


def context_terms(models: dict) -> dict:
    """Pull the context-family effects out of the fitted models.

    Args:
        models: Stage name to {epoch group: effects summary}.

    How:
        Keeps effects whose family is "context".

    Returns:
        Context effects per stage and epoch group.
    """
    context = {}
    for stage, by_group in models.items():
        context[stage] = {group: [effect for effect in model["effects"] if effect["family"] == "context"]
                          for group, model in by_group.items()}
    return context


def quantile_rates(df: pd.DataFrame, column: str) -> list[dict]:
    """Tabulate attention and success rates by quartile of one context variable.

    Args:
        df: Community PRs.
        column: Context variable to split.

    How:
        Quartile edges come from the whole sample (not per group) so bands mean the
        same thing everywhere. Variables with many zeros collapse into fewer bands.

    Returns:
        One row per band with engaged14 and success_decided rates per epoch group.
    """
    bands = pd.qcut(df[column], QUARTILES, duplicates="drop")
    rows = []
    for band, subset in df.groupby(bands, observed=True):
        row = {"band": f"{band.left:.0f} to {band.right:.0f}"}
        for group in GROUP_NAMES:
            part = in_group(subset, group)
            row[group] = {"engaged14": rate(part["engaged14"]), "success_decided": rate(part.loc[part["decided"], "success"].astype(float))}
        rows.append(row)
    return rows


def focus_rates(df: pd.DataFrame) -> dict:
    """Compare attention and success when dhh did or did not commit in the PR's areas in the prior 14 days.

    Args:
        df: Community PRs.

    How:
        Splits on whether dhh_focus_same_area_14d is above zero, then rates per epoch group.

    Returns:
        Per split label and epoch group: n, engaged14 and success_decided rates.
    """
    rates = {}
    for label, mask in [("dhh_active_in_area", df["dhh_focus_same_area_14d"] > 0), ("dhh_not_active", df["dhh_focus_same_area_14d"] == 0)]:
        subset = df[mask]
        rates[label] = {group: {"n": int(len(in_group(subset, group))), "engaged14": rate(in_group(subset, group)["engaged14"]),
                                "success_decided": rate(in_group(subset, group).query("decided")["success"].astype(float))}
                        for group in GROUP_NAMES}
    return rates


def run(df: pd.DataFrame, models: dict) -> dict:
    """Collect all context results for the JSON.

    Args:
        df: Community PRs from load_core.
        models: Fitted attention, conversion and total models.

    How:
        Drops the user's own PRs, then runs the competition, effects, quartile and dhh-focus analyses.

    Returns:
        Dict with competition, effects, quartiles and dhh_focus.
    """
    community = df[~df["is_user_pr"]]
    return {"competition": competition.run(community), "effects": context_terms(models),
            "quartiles": {column: quantile_rates(community, column) for column in CONTEXT_VARIABLES},
            "dhh_focus": focus_rates(community)}
