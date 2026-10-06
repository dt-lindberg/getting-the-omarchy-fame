"""Assemble prs.parquet and snapshots.parquet from the per-topic builders.

Per-PR work (attention, snapshots, feedback, structure) runs in one loop; cross-PR work
(context, focus, competition) runs on whole tables afterwards.
"""

import logging

import pandas as pd

from funnel.attention import attention_row
from funnel.competition import collect_links, competition_columns, components, direct_neighbours
from funnel.context import author_history, repo_context
from funnel.disposition import build_disposition
from funnel.feedback import feedback_row
from funnel.focus import build_focus_index, merged_core_pr_work
from funnel.identity import build_identity
from funnel.snapshots import SNAPSHOT_COLUMNS, snapshot_rows
from funnel.structure import maintainer_edits, size_and_files
from funnel.text_rules import presentation_features

LOG = logging.getLogger("funnel")
PRESENTATION_STAGES = {"open": "", "pre_attention": "_pre"}


def group_events(events: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """Split the events table per PR.

    Args:
        events: Events table with a `number` column, time-sorted.

    How:
        Groups by number without re-sorting, so each frame keeps time order.

    Returns:
        Mapping from PR number to that PR's events.
    """
    return {number: frame for number, frame in events.groupby("number", sort=False)}


def per_pr_rows(nodes: list[dict], identity: pd.DataFrame, disposition: pd.DataFrame,
                events_by_pr: dict, base: pd.DataFrame, data_end: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Attention, feedback, structure, presentation and snapshot rows for every PR.

    Args:
        nodes: PR nodes.
        identity: Identity table.
        disposition: Disposition table.
        events_by_pr: Events per PR.
        base: Base table (current title/body, files).
        data_end: Latest event time in the data.

    How:
        Snapshots come after attention (they need its cut-off times); presentation
        features are computed on the open and pre_attention snapshots.

    Returns:
        (per-PR columns indexed by number, snapshots table).
    """
    rows, snapshots = {}, []
    empty = next(iter(events_by_pr.values())).iloc[:0]
    for node in nodes:
        number = node["number"]
        events = events_by_pr.get(number, empty)
        identity_row, disposition_values, base_row = identity.loc[number], disposition.loc[number], base.loc[number]
        attention = attention_row(events, identity_row["created_at"], identity_row["resolved_at"],
                                  identity_row["closed_by"], identity_row["closed_by_role"])
        pr_snapshots, exact = snapshot_rows(node, base_row["title"], base_row["body"], events, attention,
                                            identity_row["resolved_at"])
        snapshots += pr_snapshots
        row = {"title": base_row["title"], **attention, **size_and_files(base_row), **maintainer_edits(events),
               "open_body_exact": exact,
               **feedback_row(events, attention["first_substantive_maintainer"], identity_row["resolved_at"],
                              data_end, disposition_values["disposition"])}
        for snapshot in pr_snapshots:
            suffix = PRESENTATION_STAGES.get(snapshot["stage"])
            if suffix is not None:
                row.update({name + suffix: value
                            for name, value in presentation_features(snapshot["title"], snapshot["body"]).items()})
        rows[number] = row
    table = pd.DataFrame.from_dict(rows, orient="index")
    table.index.name = "number"
    return table, pd.DataFrame(snapshots, columns=SNAPSHOT_COLUMNS)


def cross_pr_columns(nodes: list[dict], prs: pd.DataFrame, events: pd.DataFrame, snapshots: pd.DataFrame,
                     base: pd.DataFrame) -> pd.DataFrame:
    """Author history, repo context, maintainer focus and competition columns.

    Args:
        nodes: PR nodes (closing issue references).
        prs: Partial PR table with identity, disposition, areas.
        events: Events table.
        snapshots: Snapshots table (open bodies feed competition links).
        base: Base table (file paths for core PR focus).

    How:
        Each part uses only information before a PR's creation (competition membership is
        the one ex-post link, counted only against PRs already open at creation).

    Returns:
        DataFrame indexed by number.
    """
    timing = prs[["author", "author_group", "created_at", "resolved_at", "success", "merged"]]
    focus = build_focus_index(merged_core_pr_work(prs, base["paths"]))
    focus_rows = [focus.features(row.created_at, row.areas) for row in prs.itertuples()]
    open_bodies = snapshots[snapshots["stage"] == "open"].set_index("number")["body"].to_dict()
    links = collect_links(nodes, events, open_bodies)
    numbers = set(prs.index)
    return pd.concat([author_history(timing), repo_context(timing, events),
                      pd.DataFrame(focus_rows, index=prs.index),
                      competition_columns(timing, components(links, numbers), direct_neighbours(links, numbers))], axis=1)


def build_tables(nodes: list[dict], events: pd.DataFrame, base: pd.DataFrame,
                 absorbed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build prs and snapshots tables.

    Args:
        nodes: PR nodes from load_timeline_nodes.
        events: Events table.
        base: Base PR table.
        absorbed: Absorbed table.

    How:
        identity -> disposition -> per-PR loop -> cross-PR columns, then joins on number.

    Returns:
        (prs with `number` as a column, snapshots).
    """
    events_by_pr = group_events(events)
    nodes = sorted(nodes, key=lambda node: node["number"])
    identity = build_identity(nodes, events_by_pr)
    disposition = build_disposition(identity, events_by_pr, base, absorbed)
    per_pr, snapshots = per_pr_rows(nodes, identity, disposition, events_by_pr, base, events["ts"].max())
    prs = identity.join(disposition).join(per_pr).sort_index()
    # silent_decision also covers closes with a one-line explanation; this is the truly wordless subset.
    prs["silent_no_comment"] = prs["silent_decision"] & ~prs["has_terminal_comment"]
    LOG.info("per-PR columns done: %d PRs", len(prs))
    prs = prs.join(cross_pr_columns(nodes, prs, events, snapshots, base))
    return prs.reset_index(), snapshots
