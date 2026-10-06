"""Shared loading and small summaries for the merged analysis.

Wraps analysis.data (population rule, dispositions, engagement flags) and adds
the columns every core module needs, so none of them re-derives them.
"""

import numpy as np
import pandas as pd

from analysis.data import ATTENTION_WINDOW_DAYS, EPOCH_ORDER, GROUPS, engaged_within, in_group, load_community
from analysis.stats import Z95, round_sig
from funnel.constants import DERIVED, DHH, ROOT

RESULTS_FILE = ROOT / "data" / "results" / "analysis.json"
GROUP_NAMES = list(GROUPS)
KINDS = ["bug_fix", "feature", "performance", "security", "docs", "refactor", "packaging", "other"]

__all__ = ["EPOCH_ORDER", "GROUPS", "GROUP_NAMES", "KINDS", "DERIVED", "RESULTS_FILE",
           "in_group", "round_sig", "load_core", "rate", "median_quartiles"]


def load_core() -> pd.DataFrame:
    """Load community PRs since launch with outcomes, engagement flags, kind dummies and who engaged.

    How:
        Starts from load_community, adds the 14-day attention outcome, the
        success outcome (decided PRs only), kind dummies (bug_fix is the
        reference) and the first maintainer engagement's actor and type.

    Returns:
        One row per community PR, indexed by number.
    """
    df = load_community()
    df["engaged14"] = engaged_within(df, ATTENTION_WINDOW_DAYS)
    df["success_f"] = np.where(df["decided"], df["success"].astype(float), np.nan)
    df["success_if_eng"] = np.where(df["decided"] & df["eng"], df["success"].astype(float), np.nan)
    for kind in KINDS[1:]:
        df[f"kind_{kind}"] = df["kind"] == kind
    fetched = df.attrs["fetch_time"]
    df = df.merge(first_engagement(df), on="number", how="left").set_index("number", drop=False)
    df.index.name = None
    df.attrs["fetch_time"] = fetched
    return df


def first_engagement(df: pd.DataFrame) -> pd.DataFrame:
    """Find the actor and type of each PR's first bulk-free maintainer engagement.

    Args:
        df: Community PRs with a `number` column.

    How:
        Takes the first maintainer event (not close or merge, not bulk) per PR from the
        event table; its substantive flag separates real comments from lightweight acts.

    Returns:
        DataFrame with number, eng_by_dhh, eng_substantive and eng_type.
    """
    events = pd.read_parquet(DERIVED / "events.parquet", columns=["number", "ts", "type", "actor", "actor_role", "substantive", "bulk"])
    events = events[events["number"].isin(df["number"]) & (events["actor_role"] == "maintainer") & ~events["bulk"]
                    & ~events["type"].isin(["closed", "merged"])]
    first = events.sort_values("ts", kind="stable").groupby("number").first().reset_index()
    return pd.DataFrame({"number": first["number"], "eng_by_dhh": first["actor"] == DHH,
                         "eng_substantive": first["substantive"].astype(bool), "eng_type": first["type"]})


def rate(values: pd.Series) -> dict:
    """Summarise a 0/1 series as a percentage with a Wilson 95% interval.

    Args:
        values: 0/1 (or boolean) series; NaN is ignored.

    How:
        Wilson score interval around the mean, scaled to percentage points.

    Returns:
        Dict with n, pp (mean in percent), lo and hi; None values when empty.
    """
    observed = values.dropna()
    n = len(observed)
    if n == 0:
        return {"n": 0, "pp": None, "lo": None, "hi": None}
    p = float(observed.mean())
    centre = (p + Z95**2 / (2 * n)) / (1 + Z95**2 / n)
    half = Z95 * np.sqrt(p * (1 - p) / n + Z95**2 / (4 * n * n)) / (1 + Z95**2 / n)
    return {"n": int(n), "pp": p * 100, "lo": (centre - half) * 100, "hi": (centre + half) * 100}


def median_quartiles(values: pd.Series) -> dict:
    """Summarise a numeric series by its median and quartiles.

    Args:
        values: Numeric series; NaN is ignored.

    How:
        Uses pandas median and the 25% and 75% quantiles.

    Returns:
        Dict with n, median, p25 and p75; None values when empty.
    """
    observed = values.dropna()
    if len(observed) == 0:
        return {"n": 0, "median": None, "p25": None, "p75": None}
    return {"n": int(len(observed)), "median": float(observed.median()), "p25": float(observed.quantile(.25)),
            "p75": float(observed.quantile(.75))}
