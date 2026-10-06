"""Unpack the committed data snapshot into data/raw/ so the pipeline can run without refetching."""
import gzip
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "snapshot"
RAW = ROOT / "data" / "raw"
BASE = RAW / "base"

# The full PR timelines go to data/raw/; the earlier per-PR pull and its derived tables go to data/raw/base/.
TARGETS = {
    "timelines.jsonl.gz": RAW / "timelines.jsonl",
    "prs_open.jsonl.gz": BASE / "prs_open.jsonl",
    "prs_merged.jsonl.gz": BASE / "prs_merged.jsonl",
    "prs_closed.jsonl.gz": BASE / "prs_closed.jsonl",
    "prs_user.jsonl.gz": BASE / "prs_user.jsonl",
    "prs_v1_features.csv.gz": BASE / "prs.csv",
    "community_for_topics.jsonl.gz": BASE / "community_for_topics.jsonl",
}


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    for name, target in TARGETS.items():
        with gzip.open(SNAPSHOT / name, "rb") as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        print(f"{name} -> {target.relative_to(ROOT)}")
    shutil.copy(SNAPSHOT / "prs_fetch_meta.json", BASE / "fetch_meta.json")
    # The commit table from `git log origin/quattro`, so no local clone is needed (rebuild with build_commits.py).
    derived = ROOT / "data" / "derived"
    derived.mkdir(parents=True, exist_ok=True)
    shutil.copy(SNAPSHOT / "commits.parquet", derived / "commits.parquet")


if __name__ == "__main__":
    main()
