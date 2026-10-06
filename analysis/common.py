"""Shared loading and small summaries for the merged analysis.

Wraps analysis.data (population rule, dispositions, engagement flags) and adds
the columns every core module needs, so none of them re-derives them.
"""

import numpy as np
import pandas as pd

from analysis.data import EPOCH_ORDER, GROUPS, engaged_within, in_group, load_community
from analysis.stats import Z95, round_sig
from funnel.constants import DERIVED, ROOT

RESULTS_FILE = ROOT / "data" / "results" / "analysis.json"
GROUP_NAMES = list(GROUPS)
KINDS = ["bug_fix", "feature", "performance", "security", "docs", "refactor", "packaging", "other"]
# Share of events above which a cell is flagged as thin on the page.
THIN_N = 30

__all__ = ["EPOCH_ORDER", "GROUPS", "GROUP_NAMES", "KINDS", "THIN_N", "DERIVED", "RESULTS_FILE",
           "in_group", "round_sig", "load_core", "rate", "median_quartiles"]


def load_core() -> pd.DataFrame:
    """Community PRs since launch with outcomes, engagement flags, kind dummies and who engaged.

    How:
        Starts from load_community, adds the 14-day attention outcome, the
        success outcome (decided PRs only), kind dummies (bug_fix is the
        reference) and the first maintainer engagement's actor and type.
    """
    df = load_community()
    df["engaged14"] = engaged_within(df, 14)
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
    """Actor and type of each PR's first bulk-free maintainer engagement.

    How:
        Takes the first maintainer event (not close or merge, not bulk) per PR from the
        event table; its substantive flag separates real comments from lightweight acts.
    """
    ev = pd.read_parquet(DERIVED / "events.parquet", columns=["number", "ts", "type", "actor", "actor_role", "substantive", "bulk"])
    ev = ev[ev["number"].isin(df["number"]) & (ev["actor_role"] == "maintainer") & ~ev["bulk"]
            & ~ev["type"].isin(["closed", "merged"])]
    first = ev.sort_values("ts", kind="stable").groupby("number").first().reset_index()
    return pd.DataFrame({"number": first["number"], "eng_by_dhh": first["actor"] == "dhh",
                         "eng_substantive": first["substantive"].astype(bool), "eng_type": first["type"]})


def rate(values: pd.Series) -> dict:
    """Mean in percent with count and a Wilson 95% interval, ignoring NaN."""
    v = values.dropna()
    n = len(v)
    if n == 0:
        return {"n": 0, "pp": None, "lo": None, "hi": None}
    p = float(v.mean())
    centre = (p + Z95**2 / (2 * n)) / (1 + Z95**2 / n)
    half = Z95 * np.sqrt(p * (1 - p) / n + Z95**2 / (4 * n * n)) / (1 + Z95**2 / n)
    return {"n": int(n), "pp": p * 100, "lo": (centre - half) * 100, "hi": (centre + half) * 100}


def median_quartiles(values: pd.Series) -> dict:
    """Median and quartiles of a numeric series, with the count."""
    v = values.dropna()
    if len(v) == 0:
        return {"n": 0, "median": None, "p25": None, "p75": None}
    return {"n": int(len(v)), "median": float(v.median()), "p25": float(v.quantile(.25)), "p75": float(v.quantile(.75))}
