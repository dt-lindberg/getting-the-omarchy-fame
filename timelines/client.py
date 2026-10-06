"""Thin GraphQL client over the `gh` CLI with rate-limit awareness.

Exists so the fetch logic never touches subprocesses, sleeping or retries.
"""

import json
import logging
import subprocess
import time
from datetime import datetime, timezone

LOG = logging.getLogger("timelines")

LOW_WATER_POINTS = 200
RESET_MARGIN_SECONDS = 5
SECONDARY_LIMIT_SLEEP_SECONDS = 120
QUERY_TIMEOUT_SECONDS = 180
MAX_SECONDARY_RETRIES = 5
# Longest slice of gh output or GraphQL errors quoted in an error message.
STDERR_EXCERPT_CHARS = 200
ERRORS_EXCERPT_CHARS = 300


class TransientError(Exception):
    """A failure worth retrying with a smaller query (502, timeout, bad JSON)."""


class GitHubClient:
    """Runs GraphQL queries via `gh api graphql`, tracking the point budget."""

    def __init__(self) -> None:
        """Start with an unknown budget.

        How:
            Remaining points and reset time are unset until the first response reports them.
        """
        self.remaining: int | None = None
        self.reset_at: datetime | None = None
        self.points_spent = 0

    def query(self, text: str) -> tuple[dict, list[dict]]:
        """Run one query, sleeping first if the budget is low.

        Args:
            text: GraphQL query text; should select `rateLimit` at top level.

        How:
            Waits out the budget or a secondary limit as needed, then parses
            stdout (gh prints the JSON body even when it exits non-zero for
            partial errors such as NOT_FOUND).

        Returns:
            The `data` object and the list of GraphQL errors (possibly empty).
        """
        for _ in range(MAX_SECONDARY_RETRIES):
            self._wait_for_budget()
            result = self._run(text)
            if result is not None:
                return result
        raise TransientError("secondary rate limit persisted")

    def _wait_for_budget(self) -> None:
        """Sleep until the hourly reset if the remaining budget is low.

        How:
            Uses the resetAt time from the last response plus a small margin.
        """
        if self.remaining is None or self.remaining >= LOW_WATER_POINTS:
            return
        wait = (self.reset_at - datetime.now(timezone.utc)).total_seconds()
        wait = max(wait, 0) + RESET_MARGIN_SECONDS
        LOG.info("budget low (%s left); sleeping %.0fs until reset", self.remaining, wait)
        time.sleep(wait)
        self.remaining = None

    def _run(self, text: str) -> tuple[dict, list[dict]] | None:
        """Execute gh once.

        Args:
            text: GraphQL query text.

        How:
            Detects secondary limits from stderr, otherwise parses stdout.

        Returns:
            (data, errors), or None when a secondary limit was hit and waited out.
        """
        try:
            proc = subprocess.run(
                ["gh", "api", "graphql", "-f", f"query={text}"],
                capture_output=True, text=True, timeout=QUERY_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as err:
            raise TransientError("gh timed out") from err
        if "secondary rate limit" in proc.stderr.lower() or "abuse" in proc.stderr.lower():
            LOG.warning("secondary rate limit; sleeping %ss", SECONDARY_LIMIT_SLEEP_SECONDS)
            time.sleep(SECONDARY_LIMIT_SLEEP_SECONDS)
            return None
        try:
            body = json.loads(proc.stdout)
        except json.JSONDecodeError as err:
            raise TransientError(f"unparseable response: {proc.stderr.strip()[:STDERR_EXCERPT_CHARS]}") from err
        if not body.get("data"):
            raise TransientError(f"no data: {str(body.get('errors'))[:ERRORS_EXCERPT_CHARS]}")
        self._record_rate_limit(body["data"].get("rateLimit"))
        return body["data"], body.get("errors") or []

    def _record_rate_limit(self, rate: dict | None) -> None:
        """Remember the budget reported by the last response.

        Args:
            rate: The `rateLimit` object, or None if the query omitted it.

        How:
            Stores remaining points and reset time; adds the cost to the total.
        """
        if not rate:
            return
        self.remaining = rate["remaining"]
        self.reset_at = datetime.fromisoformat(rate["resetAt"].replace("Z", "+00:00"))
        self.points_spent += rate["cost"]
