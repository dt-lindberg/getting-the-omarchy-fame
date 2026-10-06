"""Stage 1 (getting noticed): cumulative incidence of first maintainer engagement and the 14-day model."""

import numpy as np
import pandas as pd

from analysis.stats import aalen_johansen
from analysis.common import EPOCH_ORDER, median_quartiles
from analysis.models import fit_by_group, spec
from funnel.constants import HOURS_PER_DAY

GRID_DAYS = [1, 3, 7, 14, 30, 90]
# Cause codes for aalen_johansen; 0 means censored (still open).
CAUSE_ENGAGED, CAUSE_SILENT_MERGE, CAUSE_SILENT_CLOSE = 1, 2, 3


def engagement_incidence(df: pd.DataFrame) -> dict:
    """Estimate Aalen-Johansen curves per epoch: engaged, decided without engagement, still waiting.

    Args:
        df: Community PRs from load_core.

    How:
        Event 1 is the first bulk-free maintainer engagement, events 2 and 3 are a
        merge or a close with no earlier engagement, censored is still open. The
        wait is measured from opening in days.

    Returns:
        Per epoch (and "all"): n, cumulative incidence at GRID_DAYS for each outcome and median hours to engagement.
    """
    eng_days = df["h_maintainer_engagement_nobulk"] / HOURS_PER_DAY
    silent = np.where(df["success"], CAUSE_SILENT_MERGE, CAUSE_SILENT_CLOSE)
    cause = np.where(df["eng"], CAUSE_ENGAGED, np.where(df["decided"], silent, 0))
    duration = np.where(df["eng"], eng_days, df["follow_days"]).astype(float)
    incidence = {"grid_days": GRID_DAYS}
    for name in EPOCH_ORDER + ["all"]:
        mask = (df["epoch"] == name) if name != "all" else pd.Series(True, index=df.index)
        mask = mask & ~df["is_user_pr"]
        curves = aalen_johansen(duration[mask.to_numpy()], cause[mask.to_numpy()], ["engaged", "silent_merge", "silent_close"], GRID_DAYS)
        incidence[name] = {"n": int(mask.sum()), "engaged": curves["engaged"], "silent_merge": curves["silent_merge"],
                           "silent_close": curves["silent_close"],
                           "median_hours_to_engagement": median_quartiles(df.loc[mask & df["eng"], "h_maintainer_engagement_nobulk"])}
    return incidence


def attention_model(df: pd.DataFrame) -> dict:
    """Model P(engaged within 14 days) on open-time features, overall and per epoch group.

    Args:
        df: Community PRs from load_core.

    How:
        PRs count when they were engaged in 14 days (1), or were followed 14 days or decided
        without engagement (0); the rest are dropped. AMEs in pp for +1 SD (logged
        counts) or 0 to 1 (flags).

    Returns:
        Effects summary per epoch group.
    """
    return fit_by_group(df, df["engaged14"], spec())


def run(df: pd.DataFrame) -> dict:
    """Collect all stage 1 results for the JSON.

    Args:
        df: Community PRs from load_core.

    How:
        Runs engagement_incidence and attention_model.

    Returns:
        Dict with incidence, model and an outcome description.
    """
    return {"incidence": engagement_incidence(df), "model": attention_model(df),
            "outcome": "engaged within 14 days (first maintainer engagement, bulk actions removed)"}
