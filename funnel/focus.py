"""Maintainer focus per code area: direct core commits plus merged core-authored PRs.

After mid-August 2026 core work mostly goes through PRs, so commits alone miss it. The two
sources never overlap: commits that came via a PR are excluded from the commit side.
"""

import numpy as np
import pandas as pd

from areas import pr_areas_from_files
from funnel.constants import DERIVED, FOCUS_DAYS, MAINTAINERS

NS_PER_DAY = 86_400 * 10**9


class FocusIndex:
    """Sorted maintainer-work events with a per-area index for fast window queries."""

    def __init__(self, work: pd.DataFrame):
        """Index events.

        Args:
            work: Columns ts (UTC), is_dhh (bool), areas (list of fine areas).
        """
        work = work.sort_values("ts").reset_index(drop=True)
        self.ts = work["ts"].dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ns]").astype("int64")
        self.is_dhh = work["is_dhh"].to_numpy()
        by_area: dict[str, list[int]] = {}
        for i, areas in enumerate(work["areas"]):
            for area in areas:
                by_area.setdefault(area, []).append(i)
        self.by_area = {a: np.array(v) for a, v in by_area.items()}

    def _window(self, when: int, areas: list[str], days: int) -> np.ndarray:
        """Unique event ids in the areas within `days` before `when`."""
        low = when - days * NS_PER_DAY
        hits = []
        for area in areas:
            ids = self.by_area.get(area)
            if ids is not None:
                times = self.ts[ids]
                hits.append(ids[np.searchsorted(times, low, "right"):np.searchsorted(times, when, "left")])
        return np.unique(np.concatenate(hits)) if hits else np.array([], dtype=int)

    def _days_since(self, when: int, areas: list[str], dhh_only: bool) -> float:
        """Days since the latest event in the areas (before `when`), NaN if none."""
        best = np.nan
        for area in areas:
            ids = self.by_area.get(area)
            if ids is None:
                continue
            ids = ids[self.is_dhh[ids]] if dhh_only else ids
            pos = np.searchsorted(self.ts[ids], when, "left")
            if pos:
                age = (when - self.ts[ids[pos - 1]]) / NS_PER_DAY
                best = age if np.isnan(best) else min(best, age)
        return float(best)

    def features(self, created_at: pd.Timestamp, areas: list[str]) -> dict:
        """Focus columns for one PR using only events before its creation."""
        when = int(created_at.tz_convert("UTC").tz_localize(None).to_datetime64().astype("datetime64[ns]").astype("int64"))
        near = self._window(when, areas, FOCUS_DAYS)
        week_low = np.searchsorted(self.ts, when - 7 * NS_PER_DAY, "right")
        week_high = np.searchsorted(self.ts, when, "left")
        fortnight_low = np.searchsorted(self.ts, when - FOCUS_DAYS * NS_PER_DAY, "right")
        return {
            f"dhh_focus_same_area_{FOCUS_DAYS}d": int(self.is_dhh[near].sum()),
            f"core_focus_same_area_{FOCUS_DAYS}d": len(near),
            f"dhh_focus_any_{FOCUS_DAYS}d": int(self.is_dhh[fortnight_low:week_high].sum()),
            "core_commits_prev7d": int(week_high - week_low),
            "days_since_core_touched_area": self._days_since(when, areas, dhh_only=False),
            "days_since_dhh_touched_area": self._days_since(when, areas, dhh_only=True),
        }


def build_focus_index(pr_work: pd.DataFrame) -> FocusIndex:
    """Combine direct core commits with merged core-authored PRs.

    Args:
        pr_work: One row per merged core-authored PR: ts (mergedAt), is_dhh, areas.

    How:
        Direct commits are core, non-merge, not via a PR and not release merges.
    """
    commits = pd.read_parquet(DERIVED / "commits.parquet")
    direct = commits[commits["is_core"] & ~commits["via_pr_any"] & ~commits["is_merge"]
                     & ~commits["is_integration_merge"]]
    from_commits = pd.DataFrame({"ts": direct["committed_at"],
                                 "is_dhh": direct["maintainer_login"] == "dhh",
                                 "areas": direct["areas"].map(list)})
    return FocusIndex(pd.concat([from_commits, pr_work], ignore_index=True))


def merged_core_pr_work(identity: pd.DataFrame, paths_by_pr: pd.Series) -> pd.DataFrame:
    """Rows for merged PRs authored by a maintainer, with areas from their files."""
    core = identity[identity["merged"] & identity["author"].isin(MAINTAINERS)]
    return pd.DataFrame({"ts": core["resolved_at"], "is_dhh": core["author"] == "dhh",
                         "areas": [pr_areas_from_files(paths_by_pr.get(n, [])) for n in core.index]})
