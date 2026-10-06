"""GraphQL query text for the timeline fetch: one place defining every field pulled.

Kept separate from the transport code so field changes touch only this file.
"""

REPO_OWNER = "omacom"
REPO_NAME = "omarchy"
PAGE_SIZE = 100

ITEM_TYPES = [
    "ISSUE_COMMENT", "PULL_REQUEST_REVIEW",
    "REVIEW_REQUESTED_EVENT", "LABELED_EVENT", "UNLABELED_EVENT",
    "RENAMED_TITLE_EVENT", "PULL_REQUEST_COMMIT", "HEAD_REF_FORCE_PUSHED_EVENT",
    "CLOSED_EVENT", "REOPENED_EVENT", "MERGED_EVENT", "CONVERT_TO_DRAFT_EVENT",
    "READY_FOR_REVIEW_EVENT", "ASSIGNED_EVENT", "MARKED_AS_DUPLICATE_EVENT",
    "CROSS_REFERENCED_EVENT", "CONNECTED_EVENT", "REFERENCED_EVENT",
]

ACTOR = "actor { login }"
PAGE_INFO = "pageInfo { hasNextPage endCursor } totalCount"
# Asking timelineItems for totalCount makes GitHub return a null for the first
# PullRequestCommit on some PRs (seen on #14215), and the count ignores itemTypes anyway.
TIMELINE_PAGE_INFO = "pageInfo { hasNextPage endCursor }"

# PULL_REQUEST_REVIEW_THREAD is accepted as an itemType but returns no nodes, so
# threads are fetched through the separate reviewThreads connection instead.
# One inline fragment per timeline item type; every one carries createdAt and actor.
TIMELINE_NODE = f"""
__typename
... on IssueComment {{
  createdAt author {{ login }} authorAssociation body
  reactionGroups {{ content reactors {{ totalCount }} }}
  userContentEdits(first: 1) {{ totalCount }}
}}
... on PullRequestReview {{
  createdAt submittedAt author {{ login }} authorAssociation state body
  comments {{ totalCount }}
}}
... on ReviewRequestedEvent {{
  createdAt {ACTOR}
  requestedReviewer {{ ... on User {{ login }} ... on Team {{ teamSlug: slug }} ... on Bot {{ login }} }}
}}
... on LabeledEvent {{ createdAt {ACTOR} label {{ name }} }}
... on UnlabeledEvent {{ createdAt {ACTOR} label {{ name }} }}
... on RenamedTitleEvent {{ createdAt {ACTOR} previousTitle currentTitle }}
... on PullRequestCommit {{
  commit {{
    oid committedDate authoredDate messageHeadline
    author {{ user {{ login }} }}
  }}
}}
... on HeadRefForcePushedEvent {{
  createdAt {ACTOR}
  beforeCommit {{ oid }} afterCommit {{ oid }}
}}
... on ClosedEvent {{ createdAt {ACTOR} stateReason closer {{ __typename ... on PullRequest {{ number }} ... on Commit {{ oid }} }} }}
... on ReopenedEvent {{ createdAt {ACTOR} }}
... on MergedEvent {{ createdAt {ACTOR} commit {{ oid }} }}
... on ConvertToDraftEvent {{ createdAt {ACTOR} }}
... on ReadyForReviewEvent {{ createdAt {ACTOR} }}
... on AssignedEvent {{ createdAt {ACTOR} assignee {{ ... on User {{ login }} ... on Bot {{ login }} }} }}
... on MarkedAsDuplicateEvent {{
  createdAt {ACTOR}
  canonical {{ __typename ... on Issue {{ number }} ... on PullRequest {{ number }} }}
}}
... on CrossReferencedEvent {{
  createdAt {ACTOR} willCloseTarget isCrossRepository
  source {{
    __typename
    ... on Issue {{ number repository {{ nameWithOwner }} }}
    ... on PullRequest {{ number repository {{ nameWithOwner }} }}
  }}
}}
... on ConnectedEvent {{
  createdAt {ACTOR}
  subject {{ __typename ... on Issue {{ number }} ... on PullRequest {{ number }} }}
}}
... on ReferencedEvent {{ createdAt {ACTOR} commit {{ oid }} }}
"""

EDIT_NODE = "createdAt editedAt deletedAt editor { login } diff"
REACTION_NODE = "content createdAt user { login }"
THREAD_NODE = (
    "path isResolved isOutdated resolvedBy { login } "
    "comments { totalCount }"
)


def after_arg(cursor: str | None) -> str:
    """Format the optional `after:` argument for a connection.

    Args:
        cursor: End cursor of the previous page, or None for the first page.

    How:
        Returns an empty string for the first page so the query text stays valid.

    Returns:
        Argument text starting with a comma, or an empty string.
    """
    return f', after: "{cursor}"' if cursor else ""


def timeline_connection(cursor: str | None = None, first: int = PAGE_SIZE) -> str:
    """Build the timelineItems selection for one page.

    Args:
        cursor: End cursor of the previous page, or None for the first page.
        first: Page size.

    How:
        Joins the item type list and per-type fragments into one selection.

    Returns:
        GraphQL text for the connection.
    """
    types = ", ".join(ITEM_TYPES)
    return (
        f"timelineItems(first: {first}, itemTypes: [{types}]{after_arg(cursor)}) "
        f"{{ {TIMELINE_PAGE_INFO} nodes {{ {TIMELINE_NODE} }} }}"
    )


def edits_connection(cursor: str | None = None, first: int = PAGE_SIZE) -> str:
    """Build the userContentEdits selection (description revision history).

    Args:
        cursor: End cursor of the previous page, or None for the first page.
        first: Page size.

    How:
        Newest edit comes first from the API; pagination is by cursor.

    Returns:
        GraphQL text for the connection.
    """
    return (
        f"userContentEdits(first: {first}{after_arg(cursor)}) "
        f"{{ {PAGE_INFO} nodes {{ {EDIT_NODE} }} }}"
    )


def reactions_connection(cursor: str | None = None, first: int = PAGE_SIZE) -> str:
    """Build the selection for reactions on the PR body.

    Args:
        cursor: End cursor of the previous page, or None for the first page.
        first: Page size.

    How:
        Plain connection with content, time and user per reaction.

    Returns:
        GraphQL text for the connection.
    """
    return (
        f"reactions(first: {first}{after_arg(cursor)}) "
        f"{{ {PAGE_INFO} nodes {{ {REACTION_NODE} }} }}"
    )


def threads_connection(cursor: str | None = None, first: int = PAGE_SIZE) -> str:
    """Build the reviewThreads selection (inline review conversations).

    Args:
        cursor: End cursor of the previous page, or None for the first page.
        first: Page size.

    How:
        Comment counts only: fetching first-comment times doubled the query cost.

    Returns:
        GraphQL text for the connection.
    """
    return (
        f"reviewThreads(first: {first}{after_arg(cursor)}) "
        f"{{ {PAGE_INFO} nodes {{ {THREAD_NODE} }} }}"
    )


# Scalar fields and the closing-issue list, fetched once with the first page.
PR_SCALARS = (
    "number state isDraft createdAt updatedAt closedAt mergedAt lastEditedAt "
    "includesCreatedEdit author { login } mergedBy { login } "
    "commits { totalCount } closingIssuesReferences(first: 10) { totalCount nodes { number } }"
)

# Connection name in the API response -> builder for its selection text.
CONNECTIONS = {
    "timelineItems": timeline_connection,
    "userContentEdits": edits_connection,
    "reactions": reactions_connection,
    "reviewThreads": threads_connection,
}

RATE_LIMIT = "rateLimit { cost remaining resetAt }"


def pr_selection(connections: bool = True, first: int = PAGE_SIZE) -> str:
    """Build the selection set for one pull request.

    Args:
        connections: Include the three paginated connections (first page).
        first: Page size for those connections.

    How:
        Scalars always; connections only when asked, so the piecewise fallback
        can fetch them separately.

    Returns:
        GraphQL text to place inside `pullRequest(...) { }`.
    """
    parts = [PR_SCALARS]
    if connections:
        parts += [build(None, first) for build in CONNECTIONS.values()]
    return " ".join(parts)


def batch_query(numbers: list[int], connections: bool = True, first: int = PAGE_SIZE) -> str:
    """Build one query fetching several PRs through aliases (`pr123`).

    Args:
        numbers: PR numbers to fetch.
        connections: Include the paginated connections.
        first: Page size for those connections.

    How:
        One alias per PR under a single repository selection, plus rateLimit.

    Returns:
        Full GraphQL query text.
    """
    selection = pr_selection(connections, first)
    aliases = " ".join(f"pr{number}: pullRequest(number: {number}) {{ {selection} }}" for number in numbers)
    return (
        f"query {{ {RATE_LIMIT} "
        f'repository(owner: "{REPO_OWNER}", name: "{REPO_NAME}") {{ {aliases} }} }}'
    )


def page_query(number: int, name: str, cursor: str | None, first: int = PAGE_SIZE) -> str:
    """Build a query for one further page of one connection of one PR.

    Args:
        number: PR number.
        name: Connection name, a key of CONNECTIONS.
        cursor: End cursor of the previous page.
        first: Page size.

    How:
        Reuses the connection builder with a cursor.

    Returns:
        Full GraphQL query text.
    """
    connection = CONNECTIONS[name](cursor, first)
    return (
        f"query {{ {RATE_LIMIT} "
        f'repository(owner: "{REPO_OWNER}", name: "{REPO_NAME}") '
        f"{{ pr{number}: pullRequest(number: {number}) {{ {connection} }} }} }}"
    )
