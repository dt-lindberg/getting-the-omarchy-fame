"""Weekly series from launch and a simple binary-segmentation search for breakpoints."""

import numpy as np
import pandas as pd

from analysis.data import engaged_within
from analysis.common import DERIVED
from funnel.constants import EPOCH_STARTS

MIN_SEGMENT_WEEKS = 4
MAX_BREAKS = 4
# A split must remove at least this share of the series' total variation to count.
MIN_GAIN_SHARE = 0.05
MIN_WEEK_N = 10
# Engagement window for the weekly share; the series name says "7".
WEEKLY_ENGAGEMENT_DAYS = 7
SERIES_LABELS = {
    "opened": "Community PRs opened", "p_engaged7": "Share engaged within 7 days (opened that week)",
    "success_decided": "Success rate among decided (opened that week)", "community_merges": "Community PRs merged or absorbed",
    "core_commits": "Core commits to the default branch"}


def week_start(ts: pd.Series) -> pd.Series:
    """Find the week start for each timestamp.

    Args:
        ts: Timezone-aware timestamps.

    How:
        Drops the timezone and buckets into weeks that end on Sunday.

    Returns:
        Monday 00:00 UTC of the containing week, timezone removed.
    """
    return ts.dt.tz_convert(None).dt.to_period("W-SUN").dt.start_time


def weekly_table(df: pd.DataFrame) -> pd.DataFrame:
    """Build one row per week with the five series.

    Args:
        df: Community PRs with an `engaged7` column.

    How:
        Rates are blank when fewer than MIN_WEEK_N PRs underlie them; core commits come from
        the commit table by landing week.

    Returns:
        DataFrame indexed by week start.
    """
    community = df[~df["is_user_pr"]].copy()
    community["week"] = week_start(community["created_at"])
    weeks = pd.date_range(community["week"].min(), community["week"].max(), freq="W-MON")
    weekly = pd.DataFrame(index=weeks)
    weekly["opened"] = community.groupby("week").size()
    known = community.dropna(subset=["engaged7"]).groupby("week")["engaged7"]
    weekly["p_engaged7"] = (known.mean() * 100).where(known.size() >= MIN_WEEK_N)
    decided = community[community["decided"]].groupby("week")["success"]
    weekly["success_decided"] = (decided.mean() * 100).where(decided.size() >= MIN_WEEK_N)
    won = community[community["success"]]
    weekly["community_merges"] = won.groupby(week_start(won["resolved_at"])).size()
    commits = pd.read_parquet(DERIVED / "commits.parquet", columns=["landed_at", "is_core", "is_bot", "is_merge"])
    core = commits[commits["is_core"] & ~commits["is_bot"] & ~commits["is_merge"] & commits["landed_at"].notna()]
    weekly["core_commits"] = core.groupby(week_start(pd.to_datetime(core["landed_at"], utc=True))).size()
    weekly["opened"] = weekly["opened"].fillna(0)
    weekly["community_merges"] = weekly["community_merges"].fillna(0)
    return weekly.rename_axis("week")


def best_split(values: np.ndarray, lo: int, hi: int) -> tuple[int, float] | None:
    """Find the best single split of a segment.

    Args:
        values: The whole series.
        lo: Segment start (inclusive).
        hi: Segment end (exclusive).

    How:
        Tries each split leaving at least MIN_SEGMENT_WEEKS on both sides and keeps the largest drop in squared error.

    Returns:
        (split index, error drop), or None when no split gives a positive drop.
    """
    best, best_gain = None, 0.0
    total = ((values[lo:hi] - values[lo:hi].mean()) ** 2).sum()
    for k in range(lo + MIN_SEGMENT_WEEKS, hi - MIN_SEGMENT_WEEKS + 1):
        a, b = values[lo:k], values[k:hi]
        gain = total - ((a - a.mean()) ** 2).sum() - ((b - b.mean()) ** 2).sum()
        if gain > best_gain:
            best, best_gain = k, gain
    return (best, best_gain) if best is not None else None


def binary_segmentation(series: pd.Series) -> list[dict]:
    """Find mean-shift breakpoints by repeatedly splitting the segment with the biggest gain.

    Args:
        series: Weekly values indexed by week start; missing weeks are dropped.

    How:
        Missing weeks are dropped (the split dates refer to the remaining weeks).
        Splits stop when the best one explains less than MIN_GAIN_SHARE of the total
        variation. Each result lists the date, means either side and the nearest epoch start.

    Returns:
        Up to MAX_BREAKS breakpoints sorted by week.
    """
    observed = series.dropna()
    values, dates = observed.to_numpy(float), observed.index
    total = ((values - values.mean()) ** 2).sum()
    segments, breaks = [(0, len(values))], []
    for _ in range(MAX_BREAKS):
        options = [(best_split(values, lo, hi), lo, hi) for lo, hi in segments]
        options = [(split, lo, hi) for split, lo, hi in options if split is not None]
        if not options:
            break
        (k, gain), lo, hi = max(options, key=lambda option: option[0][1])
        if gain / total < MIN_GAIN_SHARE:
            break
        segments.remove((lo, hi))
        segments += [(lo, k), (k, hi)]
        breaks.append({"week": dates[k], "gain_share": gain / total, "mean_before": float(values[lo:k].mean()),
                       "mean_after": float(values[k:hi].mean())})
    for change in breaks:
        nearest = min(EPOCH_STARTS, key=lambda epoch: abs((change["week"] - epoch[1].tz_convert(None)).days))
        change.update(week=change["week"].date().isoformat(), nearest_epoch=nearest[0],
                      days_from_epoch=int((change["week"] - nearest[1].tz_convert(None)).days))
    return sorted(breaks, key=lambda change: change["week"])


def run(df: pd.DataFrame) -> dict:
    """Collect the weekly series and breakpoints for the JSON.

    Args:
        df: Community PRs from load_core.

    How:
        Builds the weekly table, then searches each series for breakpoints.

    Returns:
        Dict with the series, labels, breakpoints, epoch starts and a note.
    """
    work = df.assign(engaged7=engaged_within(df, WEEKLY_ENGAGEMENT_DAYS))
    table = weekly_table(work)
    series = {name: [{"week": week.date().isoformat(), "value": None if pd.isna(value) else float(value)}
                     for week, value in table[name].items()]
              for name in SERIES_LABELS}
    breaks = {name: binary_segmentation(table[name]) for name in SERIES_LABELS}
    return {"series": series, "labels": SERIES_LABELS, "breakpoints": breaks,
            "epoch_starts": {name: start.date().isoformat() for name, start in EPOCH_STARTS},
            "note": "Success among decided is biased in recent weeks: only quickly decided PRs are in, many by the 21 Sep closure."}
