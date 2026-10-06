"""Render timelines_README.md and referenced_issues.csv from collected statistics.

Exists to keep presentation separate from the statistics pass in summary.py.
"""

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

from funnel.constants import SECONDS_PER_HOUR

FIELDS_TEXT = """\
## Files

- `timelines.jsonl`: one line per PR number: `{number, fetched_at, node, meta}`.
  `node` is the raw GraphQL object (null if the number is not a PR).
- `fetch.log`: progress log of the fetch run(s).
- `referenced_issues.csv`: every same-repo issue/PR number referenced by a PR via
  `closingIssuesReferences` or a `CrossReferencedEvent` (`number,kind,count`).
  Numbers only; no issue metadata was fetched. Some numbers are PRs.

## `node` fields

- Scalars: number, state, isDraft, createdAt, updatedAt, closedAt, mergedAt,
  lastEditedAt, includesCreatedEdit, author.login, mergedBy.login.
- `closingIssuesReferences(first: 10)`: totalCount and nodes[number].
- `userContentEdits` (PR description revisions): createdAt, editedAt, deletedAt,
  editor.login, diff. Newest first.
- `reactions` (on the PR body): content, createdAt, user.login.
- `reviewThreads` (inline review conversations): path, isResolved, isOutdated,
  resolvedBy.login, comments.totalCount. No timestamps (see below).
- `timelineItems`, filtered by itemTypes, each node tagged `__typename`:
  - IssueComment: createdAt, author, authorAssociation, body,
    reactionGroups[content, reactors.totalCount], userContentEdits.totalCount.
  - PullRequestReview: createdAt, submittedAt, author, authorAssociation, state,
    body, comments.totalCount.
  - ReviewRequestedEvent: createdAt, actor, requestedReviewer (login, or teamSlug).
  - LabeledEvent / UnlabeledEvent: createdAt, actor, label.name.
  - RenamedTitleEvent: createdAt, actor, previousTitle, currentTitle.
  - PullRequestCommit: commit{oid, committedDate, authoredDate, messageHeadline,
    author.user.login}. There is no createdAt on this item; use committedDate.
  - HeadRefForcePushedEvent: createdAt, actor, beforeCommit.oid, afterCommit.oid.
  - ClosedEvent: createdAt, actor, stateReason, closer (PullRequest number or Commit oid).
  - ReopenedEvent, ConvertToDraftEvent, ReadyForReviewEvent: createdAt, actor.
  - MergedEvent: createdAt, actor, commit.oid.
  - AssignedEvent: createdAt, actor, assignee.login.
  - MarkedAsDuplicateEvent: createdAt, actor, canonical (type + number).
  - CrossReferencedEvent: createdAt, actor, willCloseTarget, isCrossRepository,
    source (Issue or PullRequest: number, repository.nameWithOwner).
  - ConnectedEvent: createdAt, actor, subject (type + number).
  - ReferencedEvent: createdAt, actor, commit.oid.
- `meta`: `pages` (pages fetched per connection), `paginated` (any connection
  needed more than one page), `truncated` (connection -> totalCount, for any
  connection where fewer nodes than totalCount were kept), `not_found`,
  `piecewise` (fetched with small pages after repeated failures).

## Caveats found while fetching

- `PULL_REQUEST_REVIEW_THREAD` is accepted as an itemType but returns no nodes in
  `timelineItems`. Threads are fetched through the separate `reviewThreads`
  connection instead, with comment counts only. Thread and inline-comment
  timestamps were not fetched (first-comment times doubled the query cost).
  `PullRequestReview.submittedAt` is the available time signal for review comments.
- `timelineItems.totalCount` ignores the itemTypes filter (it counts review
  threads and any unrequested event types too), so it is not an item count.
  Worse, requesting it made GitHub return a null for the first PullRequestCommit
  on some PRs (e.g. #14215), so it is not requested. Pages were followed by
  `pageInfo.hasNextPage`.
- `closingIssuesReferences` is deliberately capped at 10; PRs exceeding that are
  listed under truncation.

## What `userContentEdits.diff` contains

`diff` is the full description body text at that revision, not a unified diff
(verified below against the body from the earlier pull). Timestamps: `editedAt`
is when that revision became the live text; the oldest entry's `editedAt` is the
PR creation time (the original body). `createdAt` on the oldest entry is the time
of the first edit (the record is created lazily), so use `editedAt` as the
revision time. Entries are newest first. `includesCreatedEdit` is true when the
original body is among the entries; PRs never edited have no entries at all.
"""


def write_refs_csv(refs: Counter, path: Path) -> None:
    """Write referenced issue numbers with kind and reference count.

    Args:
        refs: Counter keyed by (number, kind).
        path: Output CSV path.

    How:
        Sorted by number then kind.
    """
    with open(path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["number", "kind", "count"])
        for (number, kind), count in sorted(refs.items()):
            writer.writerow([number, kind, count])


def counter_lines(counter: Counter, total_key: Counter | None = None) -> str:
    """Format a counter as a markdown table body.

    Args:
        counter: Event type (or key) to count.
        total_key: Optional second counter (PRs containing the key).

    How:
        Rows sorted by descending count.

    Returns:
        Markdown rows.
    """
    rows = []
    for key, count in counter.most_common():
        extra = f" | {total_key[key]}" if total_key is not None else ""
        rows.append(f"| {key} | {count}{extra} |")
    return "\n".join(rows)


def render_readme(result: dict, refs_total: int, span: tuple[str, str]) -> str:
    """Build the README text.

    Args:
        result: Output of summary.collect.
        refs_total: Number of distinct referenced numbers.
        span: First and last log timestamps.

    How:
        Static field description plus tables filled from the statistics.

    Returns:
        Markdown text.
    """
    stats = result["stats"]
    seconds = (datetime.fromisoformat(span[1]) - datetime.fromisoformat(span[0])).total_seconds()
    counts = (
        f"# Timelines fetch\n\nRecords: {stats['records']} PRs (not found / not a PR: {stats['not_found']}). "
        f"Fetched {span[0]} to {span[1]} local time, wall time {seconds / SECONDS_PER_HOUR:.2f} h "
        "including waiting for the rate-limit reset.\n\n"
    )
    pagination = (
        f"## Pagination and truncation\n\nPRs needing more than one page on any connection: "
        f"{stats['paginated']}. Per connection: {dict(stats['paginated_by'])}. Max pages seen: "
        f"{dict(stats['max_pages'])}. Piecewise fallbacks: {stats['piecewise']}. "
        f"Truncated connections: {dict(stats['truncated']) or 'none'}. "
        f"Null nodes returned by the API: {dict(stats['null_nodes']) or 'none'}.\n\n"
        f"PullRequestCommit items vs the PR's commits.totalCount: equal for "
        f"{stats['commit_count_match']} PRs, different for {stats['commit_count_differs']} "
        f"(examples as (number, timeline, api): {stats['commit_differences']}).\n\n"
    )
    events = (
        "## Timeline items by type\n\n| type | items | PRs containing |\n|---|---|---|\n"
        + counter_lines(stats["events"], stats["pr_with_event"])
        + f"\n\nReview threads (total over PRs): {stats['reviewThreads']}. "
        f"Body reactions by content: {dict(stats['reactions'])}.\n\n"
    )
    edits = (
        f"## Description edits\n\nPRs with any edit entry: {stats['edit_prs']}; with 2 or more "
        f"(a real edit beyond the original): {stats['multi_edit_prs']}; entries in total: {stats['edits']}; "
        f"entries with deletedAt set: {stats['deleted_edits']}.\n\n"
        f"Newest entry's diff equals the body from the earlier pull: {stats['newest_equals_body']} PRs; "
        f"differs: {stats['newest_differs']} (edited between the two pulls, or whitespace).\n\n"
    )
    refs = f"Distinct referenced same-repo numbers: {refs_total}.\n\n"
    return counts + pagination + events + edits + refs + FIELDS_TEXT
