"""Load the community PR table and derive the columns every part of analysis C shares.

One place for the population rule, the disposition grouping and the engagement
definitions, so the other modules cannot drift apart.
"""

import numpy as np
import pandas as pd

from funnel.constants import DERIVED, EPOCH_STARTS, MASS_CLOSE_EVENT_DAY

HOURS_PER_DAY = 24
ATTENTION_WINDOW_DAYS = 14
LAUNCH = EPOCH_STARTS[0][1]
QUATTRO_START = pd.Timestamp("2026-08-14", tz="UTC")
EPOCH_ORDER = ["E1", "E2", "E3", "E4"]
# Pooled group used wherever E3 alone (five days) is too small.
GROUPS = {"E1": ["E1"], "E2": ["E2"], "Quattro": ["E3", "E4"], "all": EPOCH_ORDER}
DISPOSITIONS = ["merged", "absorbed", "superseded_duplicate", "self_closed",
                "maintainer_rejected", "bot_admin_closed", "mass_closed"]
# Controls used by every adjusted model; epoch dummies drop out automatically inside a single epoch.
CONTROL_LOGGED = ["lines_changed", "direct_competitors_open_at_creation"]
CONTROL_BINARY = ["first_pr", "ep_E2", "ep_E3", "ep_E4"]
CONTROL_CONTINUOUS = ["author_shrunk_rate"]
HOUR_BANDS = [(0, "h00_06"), (6, "h06_12"), (12, "h12_18"), (18, "h18_24")]


def load_prs() -> pd.DataFrame:
    """Read the full PR table (all authors) from data/derived."""
    return pd.read_parquet(DERIVED / "prs.parquet")


def fetch_time(prs: pd.DataFrame) -> pd.Timestamp:
    """Latest timestamp seen in the table, used as the follow-up cut-off."""
    return max(prs["created_at"].max(), prs["resolved_at"].max())


def final_disposition(prs: pd.DataFrame) -> pd.Series:
    """Disposition with the 2026-09-21 event and other mass-close days folded into mass_closed.

    How:
        The funnel table gives duplicate comments precedence over mass_closed, so
        the event PRs are mostly labelled superseded_duplicate. Filtering on the
        event flag restores the event as one cause.
    """
    mass = (prs["mass_close_event"] != "") | (prs["disposition"] == "mass_closed")
    out = prs["disposition"].where(~mass, "mass_closed")
    return out.replace({"other_closed": "bot_admin_closed"})


def load_community() -> pd.DataFrame:
    """Community PRs with the derived outcome, follow-up and calendar columns.

    How:
        Keeps community authors created from launch, adds disposition, decided and
        success flags, engagement indicators (bulk-free is the main one), follow-up
        time, and weekday / hour-band. Whole-table fetch time is stored in attrs.

    Returns:
        One row per community PR.
    """
    prs = load_prs()
    now = fetch_time(prs)
    df = prs[(prs["author_group"] == "community") & (prs["created_at"] >= LAUNCH)].copy()
    df["disp"] = final_disposition(df)
    df["decided"] = df["resolved_at"].notna()
    df["mass"] = df["disp"] == "mass_closed"
    df["mass_event"] = df["mass_close_event"] == MASS_CLOSE_EVENT_DAY
    df["eng"] = df["first_maintainer_engagement_nobulk"].notna()
    df["eng_bulk"] = df["first_maintainer_engagement"].notna()
    end = df["resolved_at"].fillna(now)
    df["follow_days"] = (end - df["created_at"]).dt.total_seconds() / 86400
    df["epoch"] = pd.Categorical(df["epoch"], EPOCH_ORDER)
    df["weekday"] = df["created_at"].dt.dayofweek
    df["weekend"] = df["weekday"] >= 5
    for start, name in HOUR_BANDS:
        df[name] = (df["created_at"].dt.hour >= start) & (df["created_at"].dt.hour < start + 6)
    df["first_pr"] = df["author_prior_prs"] == 0
    for name in EPOCH_ORDER[1:]:
        df[f"ep_{name}"] = df["epoch"] == name
    df.attrs["fetch_time"] = now
    return df


def engaged_within(df: pd.DataFrame, days: float, bulk: bool = False) -> pd.Series:
    """Indicator of maintainer engagement within `days`, NaN when follow-up is too short.

    Args:
        df: Community PRs from load_community.
        days: Window length in days.
        bulk: Use the bulk-inclusive engagement time instead of the bulk-free one.

    How:
        Engaged in the window gives 1. Otherwise 0 if the PR was followed for the
        full window or was decided inside it; the rest are not yet determinable.

    Returns:
        Float series with 1, 0 or NaN.
    """
    hours = df["h_maintainer_engagement" if bulk else "h_maintainer_engagement_nobulk"]
    hit = hours <= days * HOURS_PER_DAY
    known = hit | (df["follow_days"] >= days) | df["decided"]
    return pd.Series(np.where(known, hit.astype(float), np.nan), index=df.index)


def in_group(df: pd.DataFrame, group: str) -> pd.DataFrame:
    """Rows whose creation epoch belongs to the named epoch group."""
    return df[df["epoch"].isin(GROUPS[group])]
