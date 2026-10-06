"""Maintainer focus per code area: direct core commits plus merged core-authored PRs.

After mid-August 2026 core work mostly goes through PRs, so commits alone miss it. The two
sources never overlap: commits that came via a PR are excluded from the commit side.
"""

import numpy as np
import pandas as pd

from areas import pr_areas_from_files
from funnel.constants import CONTEXT_DAYS, DERIVED, DHH, FOCUS_DAYS, MAINTAINERS, SECONDS_PER_DAY

NANOSECONDS_PER_SECOND = 10**9
NS_PER_DAY = SECONDS_PER_DAY * NANOSECONDS_PER_SECOND


class FocusIndex:
    """Sorted maintainer-work events with a per-area index for fast window queries."""

    def __init__(self, work: pd.DataFrame):
        """Index events.

        Args:
            work: Columns ts (UTC), is_dhh (bool), areas (list of fine areas).

        How:
            Sorts by time, stores times as int64 nanoseconds and lists each
            area's event positions so window queries search only that area.
        """
        work = work.sort_values("ts").reset_index(drop=True)
        self.ts = work["ts"].dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ns]").astype("int64")
        self.is_dhh = work["is_dhh"].to_numpy()
        by_area: dict[str, list[int]] = {}
        for position, areas in enumerate(work["areas"]):
            for area in areas:
                by_area.setdefault(area, []).append(position)
        self.by_area = {area: np.array(positions) for area, positions in by_area.items()}

    def _window(self, when: int, areas: list[str], days: int) -> np.ndarray:
        """Find the events in some areas within a window before a time.

        Args:
            when: Reference time, int64 nanoseconds.
            areas: Fine areas to search.
            days: Window length in days.

        How:
            Binary-searches each area's event times for the window and
            de-duplicates events that touch several of the areas.

        Returns:
            Unique event ids in the window.
        """
        low = when - days * NS_PER_DAY
        hits = []
        for area in areas:
            ids = self.by_area.get(area)
            if ids is not None:
                times = self.ts[ids]
                hits.append(ids[np.searchsorted(times, low, "right"):np.searchsorted(times, when, "left")])
        return np.unique(np.concatenate(hits)) if hits else np.array([], dtype=int)

    def _days_since(self, when: int, areas: list[str], dhh_only: bool) -> float:
        """Measure days since the latest event in some areas.

        Args:
            when: Reference time, int64 nanoseconds.
            areas: Fine areas to search.
            dhh_only: Count only dhh's events.

        How:
            Per area, finds the last event strictly before `when` and keeps the smallest age.

        Returns:
            Days since the latest such event, NaN if none.
        """
        best = np.nan
        for area in areas:
            ids = self.by_area.get(area)
            if ids is None:
                continue
            ids = ids[self.is_dhh[ids]] if dhh_only else ids
            position = np.searchsorted(self.ts[ids], when, "left")
            if position:
                age = (when - self.ts[ids[position - 1]]) / NS_PER_DAY
                best = age if np.isnan(best) else min(best, age)
        return float(best)

    def features(self, created_at: pd.Timestamp, areas: list[str]) -> dict:
        """Focus columns for one PR using only events before its creation.

        Args:
            created_at: PR creation time (UTC).
            areas: The PR's fine areas.

        How:
            Counts same-area events over FOCUS_DAYS, any-area events over the
            week and fortnight, and the age of the latest event in the areas.

        Returns:
            Column dictionary of dhh and core focus counts and days-since values.
        """
        when = int(created_at.tz_convert("UTC").tz_localize(None).to_datetime64().astype("datetime64[ns]").astype("int64"))
        near = self._window(when, areas, FOCUS_DAYS)
        week_low = np.searchsorted(self.ts, when - CONTEXT_DAYS * NS_PER_DAY, "right")
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

    Returns:
        FocusIndex over the direct commits and the merged PRs.
    """
    commits = pd.read_parquet(DERIVED / "commits.parquet")
    direct = commits[commits["is_core"] & ~commits["via_pr_any"] & ~commits["is_merge"]
                     & ~commits["is_integration_merge"]]
    from_commits = pd.DataFrame({"ts": direct["committed_at"],
                                 "is_dhh": direct["maintainer_login"] == DHH,
                                 "areas": direct["areas"].map(list)})
    return FocusIndex(pd.concat([from_commits, pr_work], ignore_index=True))


def merged_core_pr_work(identity: pd.DataFrame, paths_by_pr: pd.Series) -> pd.DataFrame:
    """Build focus-event rows for merged PRs authored by a maintainer.

    Args:
        identity: Identity table indexed by number (merged, author, resolved_at).
        paths_by_pr: Changed file paths per PR number.

    How:
        Keeps merged maintainer-authored PRs and maps their file paths to areas.

    Returns:
        DataFrame with ts, is_dhh and areas columns.
    """
    core = identity[identity["merged"] & identity["author"].isin(MAINTAINERS)]
    return pd.DataFrame({"ts": core["resolved_at"], "is_dhh": core["author"] == DHH,
                         "areas": [pr_areas_from_files(paths_by_pr.get(number, [])) for number in core.index]})
