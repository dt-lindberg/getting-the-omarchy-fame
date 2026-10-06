"""Statistics over timelines.jsonl, used for the README and the issue-reference list.

Exists so the README numbers are computed from the data rather than typed by hand.
"""

import json
import re
from collections import Counter
from pathlib import Path

from timelines.store import PR_FILES, PR_STATS_RAW

LOG_TIME = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")
THIS_REPO = "omacom/omarchy"


def iter_records(path: Path):
    """Yield each parsed record from the JSONL file.

    Args:
        path: timelines.jsonl.

    How:
        Streams line by line so the multi-hundred-MB file is never held whole.

    Returns:
        Generator of record dicts.
    """
    with open(path) as handle:
        for line in handle:
            yield json.loads(line)


def current_bodies() -> dict[int, str]:
    """Map PR number to its body as of the earlier pull.

    How:
        Reads the earlier PR files; used to test what `diff` contains.

    Returns:
        Dict of number to current body text.
    """
    bodies: dict[int, str] = {}
    for name in PR_FILES:
        with open(PR_STATS_RAW / name) as handle:
            for line in handle:
                pr = json.loads(line)
                bodies[pr["number"]] = pr["body"] or ""
    return bodies


def referenced_issue_numbers(node: dict) -> list[tuple[int, str]]:
    """List issue/PR numbers in this repo referenced by one PR.

    Args:
        node: The PR node.

    How:
        Collects closingIssuesReferences and same-repo CrossReferencedEvent sources.

    Returns:
        (number, kind) pairs; kind is "closing" or "cross_reference".
    """
    refs = [(n["number"], "closing") for n in node["closingIssuesReferences"]["nodes"]]
    for item in node["timelineItems"]["nodes"]:
        if item["__typename"] != "CrossReferencedEvent":
            continue
        source = item["source"]
        if source["repository"]["nameWithOwner"] == THIS_REPO:
            refs.append((source["number"], "cross_reference"))
    return refs


def collect(path: Path) -> dict:
    """Make one pass over the file gathering every statistic.

    Args:
        path: timelines.jsonl.

    How:
        Counters for event types, pagination, truncation, edit history and the
        equality test between the newest edit's diff and the earlier-pulled body.

    Returns:
        Dict of statistics plus the (number, kind) -> count reference table.
    """
    bodies = current_bodies()
    stats: dict = {
        "records": 0, "not_found": 0, "piecewise": 0, "paginated": 0,
        "events": Counter(), "paginated_by": Counter(), "truncated": Counter(),
        "pr_with_event": Counter(), "edit_prs": 0, "multi_edit_prs": 0,
        "edits": 0, "newest_equals_body": 0, "newest_differs": 0,
        "deleted_edits": 0, "reactions": Counter(), "max_pages": Counter(),
        "null_nodes": Counter(), "commit_count_match": 0, "commit_count_differs": 0,
        "commit_differences": [],
    }
    refs: Counter = Counter()
    for record in iter_records(path):
        stats["records"] += 1
        node, meta = record["node"], record["meta"]
        if node is None:
            stats["not_found"] += 1
            continue
        stats["piecewise"] += bool(meta.get("piecewise"))
        stats["paginated"] += meta["paginated"]
        for name, pages in meta["pages"].items():
            stats["paginated_by"][name] += pages > 1
            stats["max_pages"][name] = max(stats["max_pages"][name], pages)
        stats["truncated"].update(meta["truncated"].keys())
        types = Counter(item["__typename"] for item in node["timelineItems"]["nodes"])
        stats["null_nodes"].update(meta.get("null_nodes", {}))
        tally_commits(stats, record["number"], types["PullRequestCommit"], node["commits"]["totalCount"])
        stats["events"].update(types)
        stats["pr_with_event"].update(types.keys())
        stats["reviewThreads"] = stats.get("reviewThreads", 0) + node["reviewThreads"]["totalCount"]
        stats["reactions"].update(r["content"] for r in node["reactions"]["nodes"])
        tally_edits(stats, node["userContentEdits"]["nodes"], bodies.get(record["number"]))
        refs.update((n, kind) for n, kind in referenced_issue_numbers(node))
    return {"stats": stats, "refs": refs}


def tally_commits(stats: dict, number: int, timeline_commits: int, api_total: int) -> None:
    """Compare PullRequestCommit items with the PR's own commit count.

    Args:
        stats: Mutable statistics dict.
        number: PR number.
        timeline_commits: PullRequestCommit nodes in the timeline.
        api_total: `commits.totalCount` from the API.

    How:
        A mismatch means the timeline does not carry every commit; keeps the
        first few examples for the README.
    """
    if timeline_commits == api_total:
        stats["commit_count_match"] += 1
        return
    stats["commit_count_differs"] += 1
    if len(stats["commit_differences"]) < 10:
        stats["commit_differences"].append((number, timeline_commits, api_total))


def tally_edits(stats: dict, edits: list[dict], current_body: str | None) -> None:
    """Update edit-history statistics for one PR.

    Args:
        stats: Mutable statistics dict.
        edits: userContentEdits nodes, newest first.
        current_body: Body from the earlier pull, or None if unknown.

    How:
        Compares the newest revision's diff with the earlier-pulled body (they can
        legitimately differ if the body was edited between the two pulls).
    """
    if not edits:
        return
    stats["edit_prs"] += 1
    stats["multi_edit_prs"] += len(edits) > 1
    stats["edits"] += len(edits)
    stats["deleted_edits"] += sum(e["deletedAt"] is not None for e in edits)
    if current_body is not None:
        same = (edits[0]["diff"] or "") == current_body
        stats["newest_equals_body" if same else "newest_differs"] += 1


def log_span(log_path: Path) -> tuple[str, str]:
    """First and last timestamps in the fetch log.

    Args:
        log_path: data/raw/fetch.log.

    How:
        Reads the leading timestamp of each log line.

    Returns:
        (first, last) timestamp strings, local time.
    """
    stamps = [m.group(1) for line in open(log_path) if (m := LOG_TIME.match(line))]
    return stamps[0], stamps[-1]
