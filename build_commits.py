"""Build data/derived/commits.parquet from `git log origin/quattro` (read-only).

Maps commit authors to GitHub logins, areas and pull requests so commit activity
can be compared with PR activity.
"""
import os
import re
import subprocess
from pathlib import Path

import pandas as pd

from areas import area_of
from funnel.constants import MAINTAINERS

# A local clone of omacom/omarchy; defaults to a sibling directory named "omarchy".
REPO = os.environ.get("OMARCHY_REPO", str(Path(__file__).resolve().parent.parent / "omarchy"))
OUT = Path(__file__).parent / "data/derived/commits.parquet"

# (name regex on author name, email regex) -> GitHub login. First match wins.
LOGIN_RULES = [
    ("dhh", r"^David Heinemeier Hansson$", r"^david@hey\.com$"),
    ("ryanrhughes", r"^Ryan Hughes$", r"ryanrhughes@|^ryan@heyoodle\.com$"),
    ("spencerbull", r"^Spencer Bull$", r"spencer"),
    ("bjarneo", r"^(bjarneo|Bjarne (Øverli|Oeverli))$", r"bjarne"),
    ("ErikMelton", r"^Erik Melton$", r"meltonaerik@|ErikMelton@"),
    ("emirb", r"^Emir Beganović$", r"beganovic\.emir@"),
    ("omarchybot", r"^Omarchybot$", r"omarchy(\.org|bot)"),
    # Community committers who push branches but do not merge others' PRs.
    ("AFOliveira", r"^Afonso Oliveira$", r"afonso\.oliveira707@"),
    ("acrogenesis", r"^acrogenesis$", r"adrian\.rangel@"),
]
CORE = MAINTAINERS
BOTS = {"omarchybot"}

# Git log fields are split on unit separators, records on record separators, so
# subjects and names cannot collide with the delimiter.
LOG_FORMAT = "\x1e%H\x1f%an\x1f%ae\x1f%cn\x1f%aI\x1f%cI\x1f%P\x1f%s"
LOG_FIELD_COUNT = 8
TOP_LOGINS_SHOWN = 12
TOP_UNMAPPED_SHOWN = 10

PR_SUBJECT = re.compile(r"\(#(\d+)\)")
PR_MERGE = re.compile(r"^Merge pull request #(\d+)")
# 'Merge pull request #N from basecamp/dev' etc. are release/integration merges
INTEGRATION = re.compile(
    r"^Merge pull request #\d+ from (basecamp|omacom)/(dev|rc|master|main|quattro|omarchy-.*)$"
    r"|^Merge (remote-tracking )?branch")


def login_of(name: str, email: str):
    """Look up the GitHub login for a commit author.

    Args:
        name: Commit author name.
        email: Commit author email.

    How:
        Tests LOGIN_RULES in order; the first rule whose name and email
        patterns both match wins (email matching ignores case).

    Returns:
        The login, or None when no rule matches.
    """
    for login, name_re, email_re in LOGIN_RULES:
        if re.search(name_re, name or "") and re.search(email_re, email or "", re.I):
            return login
    return None


def git(*args: str) -> str:
    """Run a read-only git command in the local Omarchy clone.

    Args:
        *args: Arguments passed to git after `-C REPO`.

    How:
        Runs git as a subprocess; invalid UTF-8 is replaced and a non-zero exit raises.

    Returns:
        The command's standard output.
    """
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True,
                          check=True, errors="replace").stdout


def parse_log() -> list[dict]:
    """Read every commit on origin/quattro with its per-file line counts.

    How:
        Splits `git log --numstat` output into records and fields using the
        separators in LOG_FORMAT; binary files ("-") count as 0 lines.

    Returns:
        One dict per commit with author, timing, parents, subject and per-file columns.
    """
    raw = git("log", "origin/quattro", "--diff-merges=first-parent", "--numstat",
              "--no-renames", f"--format={LOG_FORMAT}")
    rows = []
    for record in raw.split("\x1e")[1:]:
        head, _, body = record.partition("\n")
        sha, author_name, author_email, committer_name, authored_at, committed_at, parents, subject = head.split(
            "\x1f", LOG_FIELD_COUNT - 1)
        files, added, deleted = [], [], []
        for line in body.splitlines():
            if not line.strip():
                continue
            added_text, deleted_text, path = line.split("\t", 2)
            files.append(path)
            added.append(0 if added_text == "-" else int(added_text))
            deleted.append(0 if deleted_text == "-" else int(deleted_text))
        rows.append(dict(sha=sha, author_name=author_name, author_email=author_email, committer_name=committer_name,
                         authored_at=authored_at, committed_at=committed_at, parents=parents.split(),
                         subject=subject, files=files, file_added=added, file_deleted=deleted))
    return rows


def side_branches(rows: list[dict]) -> tuple[dict, dict, set]:
    """Map side-branch commits to their PR number and landing time.

    Args:
        rows: Commit dicts from parse_log.

    How:
        For each two-parent merge that is a PR merge (not an integration merge)
        or sits on the first-parent chain, lists the commits it brought in with
        `git rev-list parent1..parent2`.

    Returns:
        Side-branch sha to 'Merge pull request' number (any merge), sha to the
        commit time of the first-parent merge that landed it on quattro, and
        the set of first-parent chain shas.
    """
    chain = set(git("rev-list", "--first-parent", "origin/quattro").split())
    pr_by_sha, landed_by_sha = {}, {}
    for row in rows:
        if len(row["parents"]) != 2:
            continue
        pr_match = PR_MERGE.match(row["subject"])
        if pr_match and INTEGRATION.match(row["subject"]):
            pr_match = None
        on_chain = row["sha"] in chain
        if not pr_match and not on_chain:
            continue
        first_parent, second_parent = row["parents"]
        for sha in git("rev-list", f"{first_parent}..{second_parent}").split():
            if on_chain:
                landed_by_sha.setdefault(sha, row["committed_at"])
            if pr_match:
                pr_by_sha.setdefault(sha, int(pr_match.group(1)))
    return pr_by_sha, landed_by_sha, chain


def main() -> None:
    """Build the commit table and write it to commits.parquet.

    How:
        Parses the log, tags each commit with login, areas and PR links, sorts
        by commit time, and prints the heaviest unmapped authors for rule upkeep.
    """
    rows = parse_log()
    side, landed, chain = side_branches(rows)
    records = []
    for row in rows:
        pr_match = PR_MERGE.match(row["subject"]) or PR_SUBJECT.search(row["subject"])
        subject_pr = int(pr_match.group(1)) if pr_match else None
        login = login_of(row["author_name"], row["author_email"])
        areas = sorted({area_of(path) for path in row["files"]})
        records.append(dict(
            sha=row["sha"], author_name=row["author_name"], author_email=row["author_email"],
            committer_name=row["committer_name"],
            authored_at=pd.Timestamp(row["authored_at"]).tz_convert("UTC"),
            committed_at=pd.Timestamp(row["committed_at"]).tz_convert("UTC"),
            subject=row["subject"], pr_number=subject_pr,
            is_integration_merge=bool(INTEGRATION.match(row["subject"])), is_merge=len(row["parents"]) > 1,
            files=row["files"], areas=areas,
            lines_added=sum(row["file_added"]), lines_deleted=sum(row["file_deleted"]),
            file_added=row["file_added"], file_deleted=row["file_deleted"],
            maintainer_login=login, is_core=login in CORE, is_bot=login in BOTS,
            via_pr=subject_pr is not None,
            # also true for commits inside a merged PR branch
            via_pr_any=subject_pr is not None or row["sha"] in side,
            side_branch_pr=side.get(row["sha"]),
            # on_first_parent: landed directly on quattro; else arrived via a branch merge
            on_first_parent=row["sha"] in chain,
            landed_at=pd.Timestamp(landed.get(row["sha"], row["committed_at"])).tz_convert("UTC"),
        ))
    commits = pd.DataFrame(records).sort_values("committed_at").reset_index(drop=True)
    commits.to_parquet(OUT, index=False)
    print(len(commits), "commits;", commits.is_merge.sum(), "merges;", commits.via_pr_any.sum(), "via PR")
    print(commits.maintainer_login.value_counts(dropna=False).head(TOP_LOGINS_SHOWN))
    unmapped = commits[commits.maintainer_login.isna()].groupby(["author_name", "author_email"]).size()
    print("heaviest unmapped authors:\n", unmapped.sort_values(ascending=False).head(TOP_UNMAPPED_SHOWN))


if __name__ == "__main__":
    main()
