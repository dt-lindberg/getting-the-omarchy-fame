"""Fetch full PR records: batched first pages, then per-PR pagination.

Exists to hold the retry-with-smaller-batches and page-through-everything logic
away from the command-line loop.
"""

import logging
from datetime import datetime, timezone

from timelines.client import GitHubClient, TransientError
from timelines.queries import CONNECTIONS, PAGE_SIZE, batch_query, page_query

LOG = logging.getLogger("timelines")

SINGLE_RETRIES = 3
FALLBACK_PAGE_SIZE = 20
CLOSING_ISSUES_CAP = 10
MAX_ERRORS_SHOWN = 3


def fetch_records(client: GitHubClient, numbers: list[int]) -> list[dict]:
    """Fetch complete records for PRs, splitting the batch on transient errors.

    Args:
        client: Query runner.
        numbers: PR numbers to fetch in one batch query.

    How:
        Tries the whole batch; on a transient failure splits it in halves. A
        single PR that keeps failing is fetched piecewise with small pages.

    Returns:
        One record per number: {number, fetched_at, node, meta}.
    """
    try:
        data, errors = client.query(batch_query(numbers))
    except TransientError as err:
        LOG.warning("batch of %d failed (%s)", len(numbers), err)
        if len(numbers) > 1:
            middle = len(numbers) // 2
            return fetch_records(client, numbers[:middle]) + fetch_records(client, numbers[middle:])
        return [fetch_piecewise(client, numbers[0])]
    unexpected = [error for error in errors if error.get("type") != "NOT_FOUND"]
    if unexpected:
        raise RuntimeError(f"unexpected GraphQL errors: {unexpected[:MAX_ERRORS_SHOWN]}")
    repo = data["repository"]
    return [finish_record(client, number, repo.get(f"pr{number}")) for number in numbers]


def fetch_piecewise(client: GitHubClient, number: int) -> dict:
    """Fetch one PR whose combined query keeps failing.

    Args:
        client: Query runner.
        number: PR number.

    How:
        Retries the combined query, then falls back to scalars only plus every
        connection paged in small pages, which keeps each response small.

    Returns:
        A record as from fetch_records, with meta.piecewise set.
    """
    for _ in range(SINGLE_RETRIES):
        try:
            data, _ = client.query(batch_query([number]))
            return finish_record(client, number, data["repository"][f"pr{number}"])
        except TransientError as err:
            LOG.warning("PR %d single fetch failed: %s", number, err)
    data, _ = client.query(batch_query([number], connections=False))
    node = data["repository"][f"pr{number}"]
    for name in CONNECTIONS:
        node[name] = {"totalCount": 0, "nodes": [], "pageInfo": {"hasNextPage": True, "endCursor": None}}
    record = finish_record(client, number, node, page_size=FALLBACK_PAGE_SIZE)
    record["meta"]["piecewise"] = True
    return record


def finish_record(client: GitHubClient, number: int, node: dict | None,
                  page_size: int = PAGE_SIZE) -> dict:
    """Page through every connection of one PR and attach metadata.

    Args:
        client: Query runner.
        number: PR number.
        node: First-page node from the batch query, or None if not a PR.
        page_size: Page size for follow-up pages.

    How:
        Follows endCursor while hasNextPage, appending nodes; counts pages and
        records any deliberate cap (closing issues) with its totalCount.

    Returns:
        Record dict {number, fetched_at, node, meta}.
    """
    meta: dict = {"pages": {}, "paginated": False, "truncated": {}, "null_nodes": {}}
    record = {"number": number, "fetched_at": datetime.now(timezone.utc).isoformat(),
              "node": node, "meta": meta}
    if node is None:
        meta["not_found"] = True
        return record
    for name in CONNECTIONS:
        connection = node[name]
        # The piecewise fallback starts with an empty placeholder page.
        meta["pages"][name] = 0 if connection["pageInfo"]["endCursor"] is None and \
            connection["pageInfo"]["hasNextPage"] else 1
        while connection["pageInfo"]["hasNextPage"]:
            meta["paginated"] = True
            cursor = connection["pageInfo"]["endCursor"]
            data, _ = client.query(page_query(number, name, cursor, page_size))
            page = data["repository"][f"pr{number}"][name]
            connection["nodes"].extend(page["nodes"])
            connection["pageInfo"] = page["pageInfo"]
            connection["totalCount"] = page.get("totalCount", connection.get("totalCount"))
            meta["pages"][name] += 1
        # timelineItems is not requested with totalCount (see queries.py), so skip it.
        meta["null_nodes"][name] = sum(item is None for item in connection["nodes"])
        if name != "timelineItems" and len(connection["nodes"]) != connection["totalCount"]:
            meta["truncated"][name] = connection["totalCount"]
    meta["null_nodes"] = {name: count for name, count in meta["null_nodes"].items() if count}
    closing = node["closingIssuesReferences"]
    if closing["totalCount"] > CLOSING_ISSUES_CAP:
        meta["truncated"]["closingIssuesReferences"] = closing["totalCount"]
    return record
