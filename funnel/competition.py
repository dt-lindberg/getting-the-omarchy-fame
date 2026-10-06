"""Competition clusters: PRs that touch the same issue or each other.

Union-find over PR numbers and the issue numbers they link. Edges: shared closing issue
references, "Fixes #N" links in the open-snapshot body, marked duplicates, and maintainer/bot
cross-references. Anchors linked to more than MAX_ANCHOR_LINKS PRs are treated as trackers.
"""

import re
from collections import defaultdict

import pandas as pd

from funnel.constants import MAINTAINERS
from funnel.roles import is_bot

MAX_ANCHOR_LINKS = 10
# A single PR is not a cluster.
MIN_CLUSTER_SIZE = 2
# Closing keyword followed by an issue/PR number, e.g. "Fixes #123" or "closes omacom/omarchy#123".
KEYWORD_LINK_RE = re.compile(r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\b\s*:?\s*(?:[\w.-]+/[\w.-]+)?#(\d+)", re.I)


def collect_links(nodes: list[dict], events: pd.DataFrame, open_bodies: dict[int, str]) -> dict[int, set[int]]:
    """Anchors (issue or PR numbers) linked to each PR.

    Args:
        nodes: PR nodes (closingIssuesReferences).
        events: Events table (cross_referenced, marked_duplicate with ref).
        open_bodies: Open-snapshot body per PR.

    How:
        Only strong evidence: API closing references, "Fixes #N" style links in the
        original body, marked duplicates, and cross-references written by maintainers or
        bots (their "closed in favour of #N" comments). Bare #N mentions and mentions by
        other contributors are skipped: they chain unrelated PRs into one giant cluster.

    Returns:
        {pr_number: set of anchor numbers}.
    """
    links: dict[int, set[int]] = defaultdict(set)
    for node in nodes:
        number = node["number"]
        links[number].update(issue["number"] for issue in node["closingIssuesReferences"]["nodes"])
        links[number].update(int(issue_number) for issue_number in KEYWORD_LINK_RE.findall(open_bodies.get(number, "")))
        links[number].discard(number)
    marked = events["type"] == "marked_duplicate"
    # Judge by login, not role: a maintainer's mention is evidence even on their own PR.
    official = events["actor"].isin(MAINTAINERS) | events["actor"].map(is_bot)
    crossed = (events["type"] == "cross_referenced") & official
    linked = events[(marked | crossed) & events["ref"].notna()]
    for number, ref in zip(linked["number"], linked["ref"]):
        if int(ref) != number:
            links[number].add(int(ref))
    return links


def direct_neighbours(links: dict[int, set[int]], pr_numbers: set[int]) -> dict[int, set[int]]:
    """PRs one hop away: linked directly, or sharing an anchor (issue or PR).

    Args:
        links: Output of collect_links.
        pr_numbers: All PR numbers.

    How:
        Unlike components this is not transitive, so chains of duplicates do not blow up
        the competitor count. Tracker anchors (too many links) are skipped.

    Returns:
        {pr_number: set of neighbouring PR numbers}.
    """
    by_anchor: dict[int, set[int]] = defaultdict(set)
    for number, anchors in links.items():
        for anchor in anchors:
            by_anchor[anchor].add(number)
    neighbours: dict[int, set[int]] = {}
    for number in pr_numbers:
        found = set(by_anchor.get(number, ()))
        for anchor in links.get(number, ()):
            if len(by_anchor[anchor]) <= MAX_ANCHOR_LINKS:
                found |= by_anchor[anchor] | ({anchor} if anchor in pr_numbers else set())
        found = (found & pr_numbers) - {number}
        if found:
            neighbours[number] = found
    return neighbours


def components(links: dict[int, set[int]], pr_numbers: set[int]) -> dict[int, int]:
    """Cluster id (smallest member PR number) for PRs linked into groups of two or more.

    Args:
        links: Output of collect_links.
        pr_numbers: All PR numbers.

    How:
        Anchors linked to too many PRs are dropped first. Because #N may itself be a PR,
        a direct PR-to-PR mention joins the two PRs.

    Returns:
        {pr_number: cluster_id}, only for PRs in clusters of at least MIN_CLUSTER_SIZE.
    """
    degree: dict[int, int] = defaultdict(int)
    for number, anchors in links.items():
        for anchor in anchors:
            degree[anchor] += 1
    parent: dict[int, int] = {}

    def find(member: int) -> int:
        """Find a member's cluster root.

        Args:
            member: PR or anchor number.

        How:
            Union-find lookup with path halving.

        Returns:
            The root number of the member's cluster.
        """
        parent.setdefault(member, member)
        while parent[member] != member:
            parent[member] = parent[parent[member]]
            member = parent[member]
        return member

    for number, anchors in links.items():
        for anchor in anchors:
            if degree[anchor] <= MAX_ANCHOR_LINKS:
                parent[find(number)] = find(anchor)
    groups: dict[int, list[int]] = defaultdict(list)
    for number in pr_numbers:
        if number in parent:
            groups[find(number)].append(number)
    return {number: min(members) for members in groups.values() if len(members) >= MIN_CLUSTER_SIZE for number in members}


def _open_before(table: pd.DataFrame, others: set[int], when: pd.Timestamp) -> int:
    """Count how many of some PRs were already open at a time.

    Args:
        table: Index number; columns created_at, resolved_at.
        others: PR numbers to check.
        when: Reference time.

    How:
        Keeps PRs created before `when` that are unresolved or resolved after it.

    Returns:
        The number of PRs open at `when`.
    """
    if not others:
        return 0
    group = table.loc[sorted(others)]
    return int(((group["created_at"] < when) & (group["resolved_at"].isna() | (group["resolved_at"] > when))).sum())


def competition_columns(table: pd.DataFrame, cluster_of: dict[int, int],
                        neighbours: dict[int, set[int]]) -> pd.DataFrame:
    """Cluster size, competitors open at creation, first-in-cluster and success flags.

    Args:
        table: Index number; columns created_at, resolved_at, success.
        cluster_of: Output of components.
        neighbours: Output of direct_neighbours.

    How:
        A competitor is another member created earlier and not yet resolved at creation.

    Returns:
        DataFrame indexed by number.
    """
    ids = pd.Series([cluster_of.get(number) for number in table.index], index=table.index, dtype="Int64")
    stats = {}
    for _, members in table[ids.notna()].groupby(ids[ids.notna()]):
        # Table is sorted by number, so a stable sort breaks creation-time ties by number.
        first = members.sort_values("created_at", kind="stable").index[0]
        for number in members.index:
            started = members.at[number, "created_at"]
            others = members.index != number
            open_before = (members["created_at"] < started) & (members["resolved_at"].isna() | (members["resolved_at"] > started))
            stats[number] = (len(members), int((others & open_before).sum()), number == first,
                             bool(members["success"].any()), bool(members.loc[others, "success"].any()))
    columns = ["cluster_size", "competing_open_at_creation", "is_first_in_cluster",
               "cluster_has_success", "cluster_other_success"]
    rows = [stats.get(number, (1, 0, True, bool(table.at[number, "success"]), False)) for number in table.index]
    competition = pd.DataFrame(rows, index=table.index, columns=columns)
    competition["direct_competitors"] = [len(neighbours.get(number, ())) for number in table.index]
    competition["direct_competitors_open_at_creation"] = [
        _open_before(table, neighbours.get(number, ()), table.at[number, "created_at"]) for number in table.index]
    competition.insert(0, "competition_cluster_id", ids)
    return competition
