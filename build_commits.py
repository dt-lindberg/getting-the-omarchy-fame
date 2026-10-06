"""Build data/derived/commits.parquet from `git log origin/quattro` (read-only)."""
import os
import re
import subprocess
from pathlib import Path

import pandas as pd

from areas import area_of

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
CORE = {"dhh", "ryanrhughes", "spencerbull", "bjarneo", "ErikMelton", "birkskyum", "emirb"}
BOTS = {"omarchybot"}

PR_SUBJECT = re.compile(r"\(#(\d+)\)")
PR_MERGE = re.compile(r"^Merge pull request #(\d+)")
# 'Merge pull request #N from basecamp/dev' etc. are release/integration merges
INTEGRATION = re.compile(
    r"^Merge pull request #\d+ from (basecamp|omacom)/(dev|rc|master|main|quattro|omarchy-.*)$"
    r"|^Merge (remote-tracking )?branch")


def login_of(name: str, email: str):
    for login, name_re, email_re in LOGIN_RULES:
        if re.search(name_re, name or "") and re.search(email_re, email or "", re.I):
            return login
    return None


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True,
                          check=True, errors="replace").stdout


def parse_log() -> list[dict]:
    fmt = "\x1e%H\x1f%an\x1f%ae\x1f%cn\x1f%aI\x1f%cI\x1f%P\x1f%s"
    raw = git("log", "origin/quattro", "--diff-merges=first-parent", "--numstat",
              "--no-renames", f"--format={fmt}")
    rows = []
    for rec in raw.split("\x1e")[1:]:
        head, _, body = rec.partition("\n")
        sha, an, ae, cn, ad, cd, parents, subj = head.split("\x1f", 7)
        files, add, dele = [], [], []
        for line in body.splitlines():
            if not line.strip():
                continue
            a, d, path = line.split("\t", 2)
            files.append(path)
            add.append(0 if a == "-" else int(a))
            dele.append(0 if d == "-" else int(d))
        rows.append(dict(sha=sha, author_name=an, author_email=ae, committer_name=cn,
                         authored_at=ad, committed_at=cd, parents=parents.split(),
                         subject=subj, files=files, file_added=add, file_deleted=dele))
    return rows


def side_branches(rows: list[dict]) -> tuple[dict, dict, set]:
    """Map side-branch commits to their 'Merge pull request' number (any merge) and
    to the commit time of the first-parent merge that landed them on quattro."""
    chain = set(git("rev-list", "--first-parent", "origin/quattro").split())
    pr, landed = {}, {}
    for r in rows:
        if len(r["parents"]) != 2:
            continue
        m = PR_MERGE.match(r["subject"])
        if m and INTEGRATION.match(r["subject"]):
            m = None
        on_chain = r["sha"] in chain
        if not m and not on_chain:
            continue
        p1, p2 = r["parents"]
        for sha in git("rev-list", f"{p1}..{p2}").split():
            if on_chain:
                landed.setdefault(sha, r["committed_at"])
            if m:
                pr.setdefault(sha, int(m.group(1)))
    return pr, landed, chain


def main() -> None:
    rows = parse_log()
    side, landed, chain = side_branches(rows)
    recs = []
    for r in rows:
        m = PR_MERGE.match(r["subject"]) or PR_SUBJECT.search(r["subject"])
        subj_pr = int(m.group(1)) if m else None
        login = login_of(r["author_name"], r["author_email"])
        areas = sorted({area_of(p) for p in r["files"]})
        recs.append(dict(
            sha=r["sha"], author_name=r["author_name"], author_email=r["author_email"],
            committer_name=r["committer_name"],
            authored_at=pd.Timestamp(r["authored_at"]).tz_convert("UTC"),
            committed_at=pd.Timestamp(r["committed_at"]).tz_convert("UTC"),
            subject=r["subject"], pr_number=subj_pr,
            is_integration_merge=bool(INTEGRATION.match(r["subject"])), is_merge=len(r["parents"]) > 1,
            files=r["files"], areas=areas,
            lines_added=sum(r["file_added"]), lines_deleted=sum(r["file_deleted"]),
            file_added=r["file_added"], file_deleted=r["file_deleted"],
            maintainer_login=login, is_core=login in CORE, is_bot=login in BOTS,
            via_pr=subj_pr is not None,
            # also true for commits inside a merged PR branch
            via_pr_any=subj_pr is not None or r["sha"] in side,
            side_branch_pr=side.get(r["sha"]),
            # on_first_parent: landed directly on quattro; else arrived via a branch merge
            on_first_parent=r["sha"] in chain,
            landed_at=pd.Timestamp(landed.get(r["sha"], r["committed_at"])).tz_convert("UTC"),
        ))
    df = pd.DataFrame(recs).sort_values("committed_at").reset_index(drop=True)
    df.to_parquet(OUT, index=False)
    print(len(df), "commits;", df.is_merge.sum(), "merges;", df.via_pr_any.sum(), "via PR")
    print(df.maintainer_login.value_counts(dropna=False).head(12))
    un = df[df.maintainer_login.isna()].groupby(["author_name", "author_email"]).size()
    print("heaviest unmapped authors:\n", un.sort_values(ascending=False).head(10))


if __name__ == "__main__":
    main()
