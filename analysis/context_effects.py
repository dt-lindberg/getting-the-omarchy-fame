"""Context at submission: competition, backlog, maintainer activity and dhh focus on the same area."""

import pandas as pd

from analysis import competition
from analysis.common import GROUP_NAMES, in_group, rate

CONTEXT_VARIABLES = ["backlog_open_community", "arrivals_prev7d", "maintainer_events_prev7d",
                     "dhh_focus_same_area_14d", "core_commits_prev7d"]


def context_terms(models: dict) -> dict:
    """Context-family effects pulled from the fitted models, per group, for each outcome."""
    out = {}
    for stage, by_group in models.items():
        out[stage] = {g: [e for e in m["effects"] if e["family"] == "context"] for g, m in by_group.items()}
    return out


def quantile_rates(df: pd.DataFrame, column: str) -> list[dict]:
    """Attention and success rates by quartile of one context variable, per epoch group.

    How:
        Quartile edges come from the whole sample (not per group) so bands mean the
        same thing everywhere. Variables with many zeros collapse into fewer bands.
    """
    bands = pd.qcut(df[column], 4, duplicates="drop")
    rows = []
    for band, sub in df.groupby(bands, observed=True):
        row = {"band": f"{band.left:.0f} to {band.right:.0f}"}
        for g in GROUP_NAMES:
            part = in_group(sub, g)
            row[g] = {"engaged14": rate(part["engaged14"]), "success_decided": rate(part.loc[part["decided"], "success"].astype(float))}
        rows.append(row)
    return rows


def focus_rates(df: pd.DataFrame) -> dict:
    """Attention and success when dhh did / did not commit in the PR's areas in the prior 14 days."""
    out = {}
    for label, mask in [("dhh_active_in_area", df["dhh_focus_same_area_14d"] > 0), ("dhh_not_active", df["dhh_focus_same_area_14d"] == 0)]:
        sub = df[mask]
        out[label] = {g: {"n": int(len(in_group(sub, g))), "engaged14": rate(in_group(sub, g)["engaged14"]),
                          "success_decided": rate(in_group(sub, g).query("decided")["success"].astype(float))}
                      for g in GROUP_NAMES}
    return out


def run(df: pd.DataFrame, models: dict) -> dict:
    """All context results for the JSON."""
    d = df[~df["is_user_pr"]]
    return {"competition": competition.run(d), "effects": context_terms(models),
            "quartiles": {c: quantile_rates(d, c) for c in CONTEXT_VARIABLES}, "dhh_focus": focus_rates(d)}
