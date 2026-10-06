"""Context at creation: author history, backlog, arrivals, recent maintainer activity.

Every column uses only information strictly before the PR's creation time (outcomes count
only once resolved), so none looks ahead.
"""

import numpy as np
import pandas as pd

from funnel.constants import CONTEXT_DAYS, MAINTAINERS, SHRINK_K

WEEK = pd.Timedelta(days=CONTEXT_DAYS)


def _count_before(sorted_times: np.ndarray, stamps: np.ndarray) -> np.ndarray:
    """Count, for each stamp, how many sorted_times are strictly earlier.

    Args:
        sorted_times: Ascending datetime64 array.
        stamps: Times to count before.

    How:
        Binary search with side="left".

    Returns:
        Integer array, one count per stamp.
    """
    return np.searchsorted(sorted_times, stamps, side="left")


def _window_count(sorted_times: np.ndarray, stamps: np.ndarray, window: pd.Timedelta) -> np.ndarray:
    """Count, for each stamp, how many sorted_times fall in [stamp - window, stamp).

    Args:
        sorted_times: Ascending datetime64 array.
        stamps: Times to count before.
        window: Length of the look-back window.

    How:
        Difference of two binary searches: events before the stamp minus events before the window start.

    Returns:
        Integer array, one count per stamp.
    """
    low = stamps - np.timedelta64(window.value, "ns")
    return _count_before(sorted_times, stamps) - np.searchsorted(sorted_times, low, side="left")


def _times(series: pd.Series) -> np.ndarray:
    """Convert a UTC series to a sorted array of naive datetime64 values.

    Args:
        series: Timezone-aware UTC timestamps; nulls are dropped.

    How:
        Drops nulls, removes the timezone and sorts.

    Returns:
        Sorted datetime64[ns] array.
    """
    return np.sort(series.dropna().dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ns]"))


def author_history(table: pd.DataFrame) -> pd.DataFrame:
    """Prior PRs and prior successes per author at each PR's creation.

    Args:
        table: Index number; columns author, author_group, created_at, resolved_at, success.

    How:
        p0 is the community success rate among PRs resolved before the date (0 when none
        resolved yet). shrunk_rate = (prior_success + k*p0) / (prior_prs + k).

    Returns:
        DataFrame indexed by number.
    """
    created = table["created_at"].dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ns]")
    community = table[table["author_group"] == "community"]
    resolved_all = _times(community["resolved_at"])
    resolved_success = _times(community.loc[community["success"], "resolved_at"])
    p0_den = _count_before(resolved_all, created)
    p0 = np.divide(_count_before(resolved_success, created), p0_den, out=np.zeros(len(table)), where=p0_den > 0)
    history = pd.DataFrame(0, index=table.index, dtype="int64",
                       columns=["author_prior_prs", "author_prior_success", "author_prior_resolved"])
    for _, group in table.groupby("author"):
        stamps = group["created_at"].dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ns]")
        own_created = np.sort(stamps)
        own_success = _times(group.loc[group["success"], "resolved_at"])
        own_resolved = _times(group["resolved_at"])
        history.loc[group.index, "author_prior_prs"] = _count_before(own_created, stamps)
        history.loc[group.index, "author_prior_success"] = _count_before(own_success, stamps)
        history.loc[group.index, "author_prior_resolved"] = _count_before(own_resolved, stamps)
    history = history.astype("int64")
    history["author_p0"] = p0
    history["author_shrunk_rate"] = (history["author_prior_success"] + SHRINK_K * p0) / (history["author_prior_prs"] + SHRINK_K)
    history["author_open_prs_at_creation"] = history["author_prior_prs"] - history["author_prior_resolved"]
    return history


def repo_context(table: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """Backlog, arrivals and recent maintainer activity at each PR's creation.

    Args:
        table: Same as author_history.
        events: Events table (actor, type, ts, actor_role).

    How:
        Counts over sorted arrays with searchsorted; maintainers are identified by login
        so activity on any PR counts.

    Returns:
        DataFrame indexed by number.
    """
    stamps = table["created_at"].dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ns]")
    community = table[table["author_group"] == "community"]
    created = _times(community["created_at"])
    resolved = _times(community["resolved_at"])
    by_maintainer = events[events["actor"].isin(MAINTAINERS)]
    merges = _times(by_maintainer.loc[by_maintainer["type"] == "merged", "ts"])
    activity = _times(by_maintainer.loc[by_maintainer["type"].isin(["comment", "review", "closed"]), "ts"])
    community_merges = _times(community.loc[community["merged"], "resolved_at"])
    return pd.DataFrame({
        "backlog_open_community": _count_before(created, stamps) - _count_before(resolved, stamps),
        "arrivals_prev7d": _window_count(created, stamps, WEEK),
        "community_merged_prev7d": _window_count(community_merges, stamps, WEEK),
        "maintainer_merges_prev7d": _window_count(merges, stamps, WEEK),
        "maintainer_events_prev7d": _window_count(activity, stamps, WEEK),
    }, index=table.index)
