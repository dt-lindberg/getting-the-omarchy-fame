"""funnel_summary.md: stage counts, dispositions, timing, competition, edits and spot checks."""

from pathlib import Path

import pandas as pd

from funnel.competition import MIN_CLUSTER_SIZE
from funnel.constants import BULK_MIN_PRS, EPOCHS, SAMPLE_SEED
from funnel.reports.md import md_table
from funnel.reports.problems import problems_lines
from funnel.reports.validation import validation_section

STAGES = [("submitted", None), ("any interaction (incl. bots)", "first_any_interaction"),
          ("maintainer touch", "first_maintainer_touch"), ("maintainer engagement", "first_maintainer_engagement"),
          ("substantive maintainer feedback", "first_substantive_maintainer")]
DISPOSITION_ORDER = ["merged", "absorbed", "self_closed", "superseded_duplicate", "mass_closed",
                     "bot_admin_closed", "maintainer_rejected", "other_closed", "open"]
REWRITE_EXAMPLES = 15
# Cluster sizes above this are pooled into one "N+" row of the distribution.
CLUSTER_SIZE_CAP = 10


def by_epoch(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    """Split a PR table into per-epoch slices plus the whole.

    Args:
        frame: Table with an `epoch` column.

    How:
        Keeps epochs in EPOCHS order, skipping empty ones, and appends the whole frame as "all".

    Returns:
        (name, slice) pairs.
    """
    parts = [(epoch, frame[frame["epoch"] == epoch]) for epoch in EPOCHS if (frame["epoch"] == epoch).any()]
    return parts + [("all", frame)]


def funnel_stage_table(community: pd.DataFrame) -> pd.DataFrame:
    """Count community PRs at each funnel stage per epoch.

    Args:
        community: Community PRs.

    How:
        A PR reaches a stage when its stage timestamp is set; success is counted separately.

    Returns:
        DataFrame with one row per epoch and one column per stage.
    """
    rows = {}
    for name, part in by_epoch(community):
        row = {label: int(part[column].notna().sum()) if column else len(part) for label, column in STAGES}
        row["success (merged or absorbed)"] = int(part["success"].sum())
        rows[name] = row
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("epoch")


def disposition_table(community: pd.DataFrame) -> pd.DataFrame:
    """Count dispositions per epoch plus the 21 Sep mass-close flag count.

    Args:
        community: Community PRs.

    How:
        Cross-tabulates disposition by epoch in DISPOSITION_ORDER, then adds totals
        and the number flagged by the 2026-09-21 mass close.

    Returns:
        DataFrame with one row per disposition.
    """
    table = pd.crosstab(community["disposition"], community["epoch"]).reindex(
        [disposition for disposition in DISPOSITION_ORDER if disposition in set(community["disposition"])]).fillna(0).astype(int)
    table = table[[epoch for epoch in EPOCHS if epoch in table.columns]]
    table["all"] = table.sum(axis=1)
    flagged = community[community["mass_close_event"] != ""].groupby("disposition").size()
    table["of which on 2026-09-21 mass close"] = flagged.reindex(table.index).fillna(0).astype(int)
    return table


def timing_table(community: pd.DataFrame) -> pd.DataFrame:
    """Summarise hours to first maintainer touch and engagement per epoch.

    Args:
        community: Community PRs.

    How:
        Medians over the PRs that got one. No-bulk columns ignore actions repeated
        on BULK_MIN_PRS or more PRs within a minute (bulk labelling, review requests).

    Returns:
        DataFrame with one row per epoch.
    """
    rows = {}
    for name, part in by_epoch(community):
        rows[name] = {
            "n engaged": int(part["h_maintainer_engagement"].notna().sum()),
            "median h to engagement": part["h_maintainer_engagement"].median(),
            "median h to substantive": part["h_substantive_maintainer"].median(),
            "n engaged (no bulk)": int(part["h_maintainer_engagement_nobulk"].notna().sum()),
            "median h (no bulk)": part["h_maintainer_engagement_nobulk"].median(),
            "n touched": int(part["h_maintainer_touch"].notna().sum()),
            "median h to touch": part["h_maintainer_touch"].median(),
        }
    return pd.DataFrame.from_dict(rows, orient="index").rename_axis("epoch")


def competition_lines(prs: pd.DataFrame) -> list[str]:
    """Describe competition clusters as markdown lines.

    Args:
        prs: PR table.

    How:
        Counts clusters over all PRs and those with 2+ community PRs, and tabulates
        sizes with everything above CLUSTER_SIZE_CAP pooled.

    Returns:
        Markdown lines.
    """
    clustered = prs[prs["competition_cluster_id"].notna()]
    sizes = clustered.groupby("competition_cluster_id").size()
    community = clustered[clustered["author_group"] == "community"]
    community_sizes = community.groupby("competition_cluster_id").size()
    size_distribution = sizes.clip(upper=CLUSTER_SIZE_CAP).value_counts().sort_index().rename(
        lambda size: f"{size}+" if size == CLUSTER_SIZE_CAP else str(size))
    return [f"Clusters (2+ PRs): {len(sizes)}, covering {len(clustered)} PRs; largest {int(sizes.max()) if len(sizes) else 0}.",
            f"Clusters with 2+ community PRs: {int((community_sizes >= MIN_CLUSTER_SIZE).sum())}.", "",
            "Cluster size distribution (PRs per cluster):", ""] + md_table(
                size_distribution.rename("clusters").to_frame().rename_axis("size"))


def edits_lines(community: pd.DataFrame, snapshots: pd.DataFrame) -> list[str]:
    """Count author edits before first attention, per epoch.

    Args:
        community: Community PRs.
        snapshots: Snapshots table.

    How:
        Reads the pre_attention snapshot's author-edit flag and tabulates it for
        all PRs and for those that later got maintainer engagement.

    Returns:
        Markdown lines.
    """
    edited_before_attention = snapshots[snapshots["stage"] == "pre_attention"].set_index("number")["edited_by_author_before_stage"]
    flagged = community.assign(edited=community["number"].map(edited_before_attention))
    rows = {}
    for name, part in by_epoch(flagged):
        engaged = part[part["first_maintainer_engagement"].notna()]
        rows[name] = {"community PRs": len(part), "author edited before cut-off": int(part["edited"].sum()),
                      "engaged PRs": len(engaged), "engaged and edited before engagement": int(engaged["edited"].sum())}
    return ["Cut-off is the first maintainer engagement, or the resolution/now if there was none.", ""] + md_table(
        pd.DataFrame.from_dict(rows, orient="index").rename_axis("epoch"))


def rewrite_lines(community: pd.DataFrame) -> list[str]:
    """Report accepted community PRs whose title a maintainer rewrote.

    Args:
        community: Community PRs.

    How:
        Gives the counts and share, then up to REWRITE_EXAMPLES random examples (fixed seed).

    Returns:
        Markdown lines.
    """
    accepted = community[community["success"]]
    rewritten = accepted[accepted["maintainer_renamed_title"]]
    lines = [f"Community PRs accepted (merged or absorbed): {len(accepted)}; with a maintainer title rewrite: "
             f"{len(rewritten)} ({100 * len(rewritten) / max(len(accepted), 1):.1f}%). "
             f"Among all community PRs a maintainer renamed: {int(community['maintainer_renamed_title'].sum())}.", ""]
    shown = rewritten.sample(min(REWRITE_EXAMPLES, len(rewritten)), random_state=SAMPLE_SEED).sort_values("number")
    return lines + md_table(shown[["number", "epoch", "title_before_rename", "title_after_rename"]], index=False)


def write_summary(path: Path, prs: pd.DataFrame, events: pd.DataFrame, snapshots: pd.DataFrame) -> None:
    """Write the full funnel summary.

    Args:
        path: Output file.
        prs: PR table.
        events: Events table.
        snapshots: Snapshots table.

    How:
        Assembles each section's markdown lines in order and writes them as one file.
    """
    community = prs[prs["author_group"] == "community"]
    lines = ["# Funnel summary", "",
             f"Tables: events {len(events):,} rows, prs {len(prs):,} rows ({len(community):,} community), "
             f"snapshots {len(snapshots):,} rows. Epoch is at creation (E0 = before 2025-06-26).", "",
             "## Funnel stages, community PRs", ""] + md_table(funnel_stage_table(community)) + [
             "", "## Dispositions, community PRs", ""] + md_table(disposition_table(community)) + [
             "", "## Hours from creation to maintainer attention, community PRs", ""] + md_table(timing_table(community)) + [
             "", "## Competition clusters", ""] + competition_lines(prs) + [
             "", "## Author edits before first attention, community PRs", ""] + edits_lines(community, snapshots) + [
             "", "## Maintainer title rewrites of accepted community PRs", ""] + rewrite_lines(community) + [
             ""] + validation_section(prs, events, snapshots) + problems_lines(prs, events)
    path.write_text("\n".join(lines) + "\n")
