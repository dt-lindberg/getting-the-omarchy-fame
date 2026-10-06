"""Weekly series from launch and a simple binary-segmentation search for breakpoints."""

import numpy as np
import pandas as pd

from analysis.context.data import engaged_within
from analysis.core.common import DERIVED
from funnel.constants import EPOCH_STARTS

MIN_SEGMENT_WEEKS = 4
MAX_BREAKS = 4
# A split must remove at least this share of the series' total variation to count.
MIN_GAIN_SHARE = 0.05
MIN_WEEK_N = 10
SERIES_LABELS = {
    "opened": "Community PRs opened", "p_engaged7": "Share engaged within 7 days (opened that week)",
    "success_decided": "Success rate among decided (opened that week)", "community_merges": "Community PRs merged or absorbed",
    "core_commits": "Core commits to the default branch"}


def week_start(ts: pd.Series) -> pd.Series:
    """Monday 00:00 UTC of the week containing each timestamp, timezone removed."""
    return ts.dt.tz_convert(None).dt.to_period("W-SUN").dt.start_time


def weekly_table(df: pd.DataFrame) -> pd.DataFrame:
    """One row per week with the five series; rates are blank when fewer than MIN_WEEK_N PRs underlie them."""
    d = df[~df["is_user_pr"]].copy()
    d["week"] = week_start(d["created_at"])
    weeks = pd.date_range(d["week"].min(), d["week"].max(), freq="W-MON")
    out = pd.DataFrame(index=weeks)
    out["opened"] = d.groupby("week").size()
    known = d.dropna(subset=["engaged7"]).groupby("week")["engaged7"]
    out["p_engaged7"] = (known.mean() * 100).where(known.size() >= MIN_WEEK_N)
    dec = d[d["decided"]].groupby("week")["success"]
    out["success_decided"] = (dec.mean() * 100).where(dec.size() >= MIN_WEEK_N)
    won = d[d["success"]]
    out["community_merges"] = won.groupby(week_start(won["resolved_at"])).size()
    commits = pd.read_parquet(DERIVED / "commits.parquet", columns=["landed_at", "is_core", "is_bot", "is_merge"])
    core = commits[commits["is_core"] & ~commits["is_bot"] & ~commits["is_merge"] & commits["landed_at"].notna()]
    out["core_commits"] = core.groupby(week_start(pd.to_datetime(core["landed_at"], utc=True))).size()
    out["opened"] = out["opened"].fillna(0)
    out["community_merges"] = out["community_merges"].fillna(0)
    return out.rename_axis("week")


def best_split(values: np.ndarray, lo: int, hi: int) -> tuple[int, float] | None:
    """Split index in [lo, hi) with the largest drop in squared error, and that drop."""
    best, best_gain = None, 0.0
    total = ((values[lo:hi] - values[lo:hi].mean()) ** 2).sum()
    for k in range(lo + MIN_SEGMENT_WEEKS, hi - MIN_SEGMENT_WEEKS + 1):
        a, b = values[lo:k], values[k:hi]
        gain = total - ((a - a.mean()) ** 2).sum() - ((b - b.mean()) ** 2).sum()
        if gain > best_gain:
            best, best_gain = k, gain
    return (best, best_gain) if best is not None else None


def binary_segmentation(series: pd.Series) -> list[dict]:
    """Up to MAX_BREAKS mean-shift breakpoints found by repeatedly splitting the segment with the biggest gain.

    How:
        Missing weeks are dropped (the split dates refer to the remaining weeks).
        Splits stop when the best one explains less than MIN_GAIN_SHARE of the total
        variation. Each result lists the date, means either side and the nearest epoch start.
    """
    s = series.dropna()
    values, dates = s.to_numpy(float), s.index
    total = ((values - values.mean()) ** 2).sum()
    segments, breaks = [(0, len(values))], []
    for _ in range(MAX_BREAKS):
        options = [(best_split(values, lo, hi), lo, hi) for lo, hi in segments]
        options = [(r, lo, hi) for r, lo, hi in options if r is not None]
        if not options:
            break
        (k, gain), lo, hi = max(options, key=lambda o: o[0][1])
        if gain / total < MIN_GAIN_SHARE:
            break
        segments.remove((lo, hi))
        segments += [(lo, k), (k, hi)]
        breaks.append({"week": dates[k], "gain_share": gain / total, "mean_before": float(values[lo:k].mean()),
                       "mean_after": float(values[k:hi].mean())})
    for b in breaks:
        nearest = min(EPOCH_STARTS, key=lambda e: abs((b["week"] - e[1].tz_convert(None)).days))
        b.update(week=b["week"].date().isoformat(), nearest_epoch=nearest[0],
                 days_from_epoch=int((b["week"] - nearest[1].tz_convert(None)).days))
    return sorted(breaks, key=lambda b: b["week"])


def run(df: pd.DataFrame) -> dict:
    """Weekly series and breakpoints for the JSON."""
    work = df.assign(engaged7=engaged_within(df, 7))
    table = weekly_table(work)
    series = {name: [{"week": w.date().isoformat(), "value": None if pd.isna(v) else float(v)} for w, v in table[name].items()]
              for name in SERIES_LABELS}
    breaks = {name: binary_segmentation(table[name]) for name in SERIES_LABELS}
    return {"series": series, "labels": SERIES_LABELS, "breakpoints": breaks,
            "epoch_starts": {n: t.date().isoformat() for n, t in EPOCH_STARTS},
            "note": "Success among decided is biased in recent weeks: only quickly decided PRs are in, many by the 21 Sep closure."}
