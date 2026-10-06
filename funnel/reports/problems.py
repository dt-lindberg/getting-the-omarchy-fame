"""Data-quality notes computed from the tables, appended to the funnel summary."""

import pandas as pd

from funnel.constants import BULK_MIN_PRS, FILE_LIST_CAP, MAINTAINERS
from funnel.load import load_base_prs


def hidden_review_prs(prs: pd.DataFrame, events: pd.DataFrame, base: pd.DataFrame) -> int:
    """Count PRs where a maintainer review exists in the raw dump but not on the timeline.

    Args:
        prs: PR table with number and author.
        events: Events table.
        base: Base PR records indexed by number, with review_authors.

    How:
        The timeline omits reply-only reviews (answers inside inline threads), so a
        maintainer replying inline can be invisible to every timing column. Compares
        maintainer review counts per PR in both sources, ignoring maintainer-authored PRs.

    Returns:
        Number of PRs with more raw maintainer reviews than timeline ones.
    """
    raw_review_counts = base["review_authors"].map(lambda names: sum(name in MAINTAINERS for name in names))
    timeline_review_counts = events[(events["type"] == "review") & events["actor"].isin(MAINTAINERS)].groupby("number").size()
    timeline_review_counts = timeline_review_counts.reindex(base.index).fillna(0)
    author_by_number = prs.set_index("number")["author"]
    authored_by_maintainer = base.index.map(lambda number: author_by_number.get(number) in MAINTAINERS)
    return int(((raw_review_counts > timeline_review_counts) & ~authored_by_maintainer).sum())


def problems_lines(prs: pd.DataFrame, events: pd.DataFrame) -> list[str]:
    """Write the known data problems, with counts, as markdown lines.

    Args:
        prs: PR table.
        events: Events table.

    How:
        Computes each count from the tables, so the notes stay current when the data changes.

    Returns:
        Markdown lines: a heading, one bullet per problem and a trailing blank line.
    """
    base = load_base_prs()
    missing = sorted(set(base.index) - set(prs["number"]))
    community = prs[prs["author_group"] == "community"]
    return [
        "## Data problems", "",
        f"- PRs with no timeline record (API returned null): {len(missing)} ({', '.join('#' + str(n) for n in missing)}); "
        "they are absent from every table.",
        f"- Reply-only inline reviews are not on the GitHub timeline: {hidden_review_prs(prs, events, base)} PRs show a "
        "maintainer review in the raw dump with no matching timeline review, so maintainer attention can be late by that reply.",
        f"- Bulk actions (same actor, type and detail on {BULK_MIN_PRS}+ PRs in one minute): {int(events['bulk'].sum()):,} events. "
        "They count as maintainer touch/engagement by the brief's definition; use the `_nobulk` engagement columns to ignore them.",
        f"- Reaction timestamps exist only for the PR body; comment reactions are totals (`reaction_count`) with no time.",
        f"- File lists cover the first {FILE_LIST_CAP} files: {int(prs['files_truncated'].sum())} PRs truncated (areas partial).",
        f"- Commits with an unlinked git author have actor `ghost`: {int(((events['type'] == 'commit') & (events['actor'] == 'ghost')).sum()):,}; "
        "they are counted as author commits.",
        f"- Org MEMBERs outside the core list (csfh, acrogenesis, kwilczynski) are treated as community; "
        f"{int((prs['disposition'] == 'other_closed').sum())} PRs were closed by such a non-author community account (`other_closed`).",
        f"- Open-snapshot body not exact (no creation revision recorded): {int((~prs['open_body_exact']).sum())} PRs.",
        f"- 2026-09-21 closures: {int((prs['mass_close_event'] != '').sum())} PRs flagged, mostly `superseded_duplicate` because "
        "the closing comment says so (precedence puts duplicates before mass_closed); filter on `mass_close_event` for the event.",
        f"- Competition clusters are transitive and chain through absorbing PRs (largest {int(prs.groupby('competition_cluster_id').size().max())}); "
        "use `direct_competitors*` for one-hop competition.",
        f"- Absorbed uses the earlier study's strict rule on data from 09:17 UTC ({int(community['absorbed'].sum())} community PRs); "
        "`superseded_duplicate` also holds unverified 'brought in / cherry-picked' closings.",
        ""]
