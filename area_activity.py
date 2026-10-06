"""Daily area activity, weekly activity, and no-look-ahead maintainer-focus features.

Timing uses committed_at (when the work landed on quattro); rebased or merged
commits keep their original authored_at, which would mislead.
"""
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from areas import pr_areas_from_files, top_of  # noqa: F401  (re-exported)

D = Path(__file__).parent / "data/derived"
COMMITS = D / "commits.parquet"


@lru_cache(maxsize=1)
def _load():
    c = pd.read_parquet(COMMITS).sort_values("committed_at").reset_index(drop=True)
    c["is_dhh"] = c.maintainer_login == "dhh"
    return c


def _exploded():
    c = _load()
    ex = c[["sha", "committed_at", "is_core", "is_dhh", "via_pr_any", "is_merge",
            "areas", "file_added", "file_deleted", "files"]].copy()
    return ex


def build_daily() -> pd.DataFrame:
    c = _load()
    from areas import area_of
    rows = []
    for r in c.itertuples():
        lines = {}
        # Merge diffs repeat their branch commits, so only non-merges add lines.
        if not r.is_merge:
            for p, a, d in zip(r.files, r.file_added, r.file_deleted):
                lines[area_of(p)] = lines.get(area_of(p), 0) + a + d
        for a in r.areas:
            rows.append((r.committed_at.normalize(), a, r.is_core, r.is_dhh,
                         r.is_core and not r.via_pr_any, lines.get(a, 0)))
    x = pd.DataFrame(rows, columns=["day", "area", "core", "dhh", "core_direct", "lines"])
    g = x.groupby(["day", "area"]).agg(
        n_commits=("core", "size"), core_commits=("core", "sum"),
        dhh_commits=("dhh", "sum"), core_direct_commits=("core_direct", "sum"),
        lines_changed=("lines", "sum")).reset_index()
    g["day"] = g["day"].dt.tz_localize(None)
    return g


def build_weekly() -> pd.DataFrame:
    c = _load().copy()
    c["week"] = c.committed_at.dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time
    iso = c.week.dt.isocalendar()
    c["iso_week"] = iso.year.astype(str) + "-W" + iso.week.astype(str).str.zfill(2)
    c["landed_week"] = c.landed_at.dt.tz_localize(None).dt.to_period("W-SUN").dt.start_time
    core = c[c.is_core]
    w = c.groupby(["week", "iso_week"]).agg(all_commits=("sha", "size"),
                                            merge_commits=("is_merge", "sum")).reset_index()
    parts = {
        "core_commits": core.groupby("week").size(),
        "core_direct": core[~core.via_pr_any].groupby("week").size(),
        "core_via_pr": core[core.via_pr_any].groupby("week").size(),
        "dhh_commits": core[core.is_dhh].groupby("week").size(),
        "dhh_direct": core[core.is_dhh & ~core.via_pr_any].groupby("week").size(),
        "core_merge_commits": core[core.subject.str.startswith("Merge pull request") & ~core.is_integration_merge].groupby("week").size(),
        "core_landed_commits": core.groupby("landed_week").size(),
        "community_commits": c[~c.is_core & ~c.is_bot].groupby("week").size(),
    }
    for k, s in parts.items():
        s.index.name = "week"
        w[k] = w.week.map(s).fillna(0).astype(int)
    return w.rename(columns={"week": "week_start"})


@lru_cache(maxsize=1)
def _index():
    ex = _exploded()
    t = ex.committed_at.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ns]")
    return ex, t


def focus_features(pr_created_at, pr_areas, window_days: int = 14, level: str = "fine") -> dict:
    """Maintainer-focus features using only commits strictly before pr_created_at.

    pr_areas: areas from pr_areas_from_files (same `level`). Commits count once
    per PR even if they touch several of its areas. Core commits include merges
    done by core members, so squash merges by the GitHub bot are not visible.
    """
    ts = pd.Timestamp(pr_created_at)
    ts = ts.tz_convert("UTC").tz_localize(None) if ts.tzinfo else ts
    ex, t = _index()
    hi = np.searchsorted(t, ts.to_datetime64(), side="left")
    past = ex.iloc[:hi]
    areas = set(pr_areas)
    key = (lambda a: set(a)) if level == "fine" else (lambda a: {top_of(x) for x in a})
    same = np.fromiter((bool(key(a) & areas) for a in past.areas), bool, len(past))
    age = (ts - past.committed_at.dt.tz_localize(None)).dt.total_seconds().values / 86400
    core, dhh = past.is_core.values, past.is_dhh.values
    w = (age <= window_days)
    dhh_same = same & dhh
    return {
        f"dhh_commits_same_area_prev{window_days}d": int((w & dhh_same).sum()),
        f"core_commits_same_area_prev{window_days}d": int((w & same & core).sum()),
        f"dhh_commits_any_prev{window_days}d": int((w & dhh).sum()),
        "core_commits_any_prev7d": int(((age <= 7) & core).sum()),
        "days_since_dhh_touched_area": float(age[dhh_same].min()) if dhh_same.any() else np.nan,
    }


if __name__ == "__main__":
    build_daily().to_parquet(D / "area_activity_daily.parquet", index=False)
    build_weekly().to_csv(D / "weekly_activity.csv", index=False)
    d = pd.read_parquet(D / "area_activity_daily.parquet")
    print(len(d), "day-area rows;", d.area.nunique(), "areas")
    print(focus_features("2026-09-01T12:00:00Z", ["bin", "default/hypr"]))
