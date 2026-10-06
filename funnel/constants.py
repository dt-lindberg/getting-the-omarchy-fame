"""Paths, epoch boundaries, thresholds and people lists shared across the funnel package.

One place for every tunable rule so the definitions can be audited and changed together.
"""

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_TIMELINES = ROOT / "data" / "raw" / "timelines.jsonl"
DERIVED = ROOT / "data" / "derived"
TOPICS_FILE = ROOT / "data" / "labels" / "topics.parquet"
# The earlier per-PR pull and its feature table, unpacked from data/snapshot/ by scripts/unpack_data.py.
PR_STATS = ROOT / "data" / "raw" / "base"
PR_RAW_FILES = ["prs_open.jsonl", "prs_merged.jsonl", "prs_closed.jsonl", "prs_user.jsonl"]
EXPECTED_PRS = 6950
SECONDS_PER_DAY = 86_400
SECONDS_PER_HOUR = 3_600
HOURS_PER_DAY = 24
ONE_HOUR = pd.Timedelta(hours=1)

USER_LOGIN = "dt-lindberg"
DHH = "dhh"
CORE_LOGINS = {"ryanrhughes", "spencerbull", "bjarneo", "ErikMelton", "birkskyum", "emirb"}
MAINTAINERS = CORE_LOGINS | {DHH}
BOT_LOGINS = {
    "omarchybot", "dependabot", "copilot", "copilot-swe-agent", "greptile-apps",
    "github-actions", "coderabbitai", "claude",
}
# Automation that closes PRs or comments on closures; other bots (reviewers) are ignored there.
CLOSING_BOTS = {"omarchybot", "github-actions", "dependabot"}

# Epoch starts (UTC); anything before the first is E0 (pre-launch).
EPOCH_STARTS = [
    ("E1", pd.Timestamp("2025-06-26", tz="UTC")),
    ("E2", pd.Timestamp("2025-09-17", tz="UTC")),
    ("E3", pd.Timestamp("2026-08-14", tz="UTC")),
    ("E4", pd.Timestamp("2026-08-19", tz="UTC")),
]
EPOCHS = ["E0"] + [name for name, _ in EPOCH_STARTS]

MASS_CLOSE_MIN = 50
MASS_CLOSE_EVENT_DAY = "2026-09-21"
# A maintainer comment this close to the close, with no author activity between, is part of the close.
TERMINAL_COMMENT_MINUTES = 10
# Window around a close in which a maintainer/bot comment counts as "the closing comment".
CLOSING_COMMENT_WINDOW_HOURS = 1
RESPONSE_WINDOW_DAYS = 7
CONTEXT_DAYS = 7
FOCUS_DAYS = 14
SHRINK_K = 5

TEXT_CAP_HUMAN = 3000
TEXT_CAP_BOT = 300

# Same actor, event type and detail on at least this many PRs within one minute is a bulk action.
BULK_MIN_PRS = 20
# Changed-file lists in the raw PR data stop at this many files.
FILE_LIST_CAP = 100
# Seed for the random examples picked for the markdown reports, so reruns match.
SAMPLE_SEED = 7
