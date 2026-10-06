"""Read the funnel tables and cut out the community cohort that this analysis uses."""

import pandas as pd

from analysis.feedback.constants import DERIVED, STUDY_START


def load_community() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Community PRs since launch and their events.

    How:
        Keeps community-authored PRs created on or after the public launch; the
        user's own PRs stay in the table (they have no feedback, so they cannot
        drive a finding here).

    Returns:
        (prs indexed by number, events for those PRs).
    """
    prs = pd.read_parquet(DERIVED / "prs.parquet")
    keep = (prs["author_group"] == "community") & (prs["created_at"] >= STUDY_START)
    prs = prs[keep].set_index("number", drop=False)
    events = pd.read_parquet(DERIVED / "events.parquet")
    events = events[events["number"].isin(prs.index)].sort_values(["number", "ts"], kind="stable")
    return prs, events
