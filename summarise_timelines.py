"""Compute statistics over data/raw/timelines.jsonl; write the README and issue list."""

from pathlib import Path

from timelines.report import render_readme, write_refs_csv
from timelines.summary import collect, log_span

RAW = Path(__file__).parent / "data" / "raw"


def main() -> None:
    """Run the statistics pass and write both output files."""
    result = collect(RAW / "timelines.jsonl")
    write_refs_csv(result["refs"], RAW / "referenced_issues.csv")
    distinct = len({number for number, _ in result["refs"]})
    readme = render_readme(result, distinct, log_span(RAW / "fetch.log"))
    (RAW / "timelines_README.md").write_text(readme)


if __name__ == "__main__":
    main()
