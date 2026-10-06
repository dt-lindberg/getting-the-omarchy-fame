"""Distil the analysis results into the two small JSON files the page draws.

page.json holds the aggregates behind each chart; dots.json holds one record per
community PR for the hero dot chart. Both live in data/results/.
"""
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "data" / "results"
PRS_TABLE = ROOT / "data" / "derived" / "prs.parquet"
LAUNCH = pd.Timestamp("2025-06-26", tz="UTC")
SECONDS_PER_DAY = 86_400
# Long titles are trimmed for the dot tooltip to keep the payload small.
TITLE_MAX_CHARS = 90

# Disposition -> one-letter outcome group shared by the flow chart, the bars and the dots.
OUTCOME_GROUP = {
    "merged": "M", "absorbed": "A", "superseded_duplicate": "S", "self_closed": "C",
    "mass_closed": "W", "bot_admin_closed": "W", "other_closed": "W", "maintainer_rejected": "R", "open": "O",
}
DECOMP_TERMS = {
    "lines_changed": "Bigger change (×5 lines)", "author_shrunk_rate": "Author's track record (+1 SD)",
    "first_pr": "Author's first PR", "touches_tests": "Touches test/", "docs_only": "Docs-only change",
    "kind_feature": "A feature (vs a bug fix)", "kind_security": "Security change", "kind_docs": "Docs change",
    "kind_refactor": "Refactor", "kind_performance": "Performance change",
    "direct_competitors_open_at_creation": "A rival PR already open", "dhh_focus_same_area_14d": "dhh active in the same area",
    "backlog_open_community": "Bigger open backlog", "has_measurements": "Description has measurements",
    "has_image": "Description has an image", "links_issue": "Links an issue", "has_headings": "Description has headings",
    "ai_marker": "Says it was AI-generated", "title_conventional_prefix": "fix:/feat: title prefix",
    "author_open_prs_at_creation": "Author has more PRs open",
}
KIND_METRICS = ("n", "engaged14", "success_if_engaged", "success_decided")


def sankey(analysis: dict) -> dict:
    """Collapse the attention -> disposition flows onto the page's outcome groups.

    Args:
        analysis: The full analysis.json contents.

    How:
        Sums link counts per (attention class, outcome group) pair.

    Returns:
        Attention classes and [attention, group, count] flows.
    """
    flows = {}
    for link in analysis["sankey"]["links"]:
        key = (link["attention"], OUTCOME_GROUP.get(link["outcome"], "W"))
        flows[key] = flows.get(key, 0) + link["n"]
    return {"attention": analysis["sankey"]["attention"], "flows": [[a, g, n] for (a, g), n in flows.items()]}


def dispositions(analysis: dict) -> list:
    """Outcome-group counts per era, with Quattro and Institution pooled as one era.

    Args:
        analysis: The full analysis.json contents.

    How:
        Regroups each epoch's disposition counts, then sums E3 and E4 into "Q"
        because the page treats everything from 2026-08-14 as Quattro.

    Returns:
        Rows for E1, E2, Q and all, each mapping outcome group to count.
    """
    rows = []
    for counts in analysis["dispositions"]["counts"]:
        groups = {}
        for disposition, n in counts.items():
            if disposition != "epoch":
                group = OUTCOME_GROUP.get(disposition, "W")
                groups[group] = groups.get(group, 0) + n
        rows.append({"epoch": counts["epoch"], **groups})
    quattro = {"epoch": "Q"}
    for row in rows:
        if row["epoch"] in ("E3", "E4"):
            for group, n in row.items():
                if group != "epoch":
                    quattro[group] = quattro.get(group, 0) + n
    by_epoch = {row["epoch"]: row for row in rows}
    return [by_epoch["E1"], by_epoch["E2"], quattro, by_epoch["all"]]


def decomposition(analysis: dict) -> list:
    """Attention, conversion and total effects for the features the page names.

    Args:
        analysis: The full analysis.json contents.

    How:
        Keeps only terms with a plain-English label in DECOMP_TERMS.

    Returns:
        One row per labelled term.
    """
    return [{"label": DECOMP_TERMS[r["term"]], "term": r["term"],
             "att": r.get("attention"), "conv": r.get("conversion"), "tot": r.get("total")}
            for r in analysis["decomposition"]["all"] if r["term"] in DECOMP_TERMS]


def kinds(analysis: dict) -> list:
    """Per-kind rates by era, reduced to the metrics the kind chart draws.

    Args:
        analysis: The full analysis.json contents.

    How:
        Copies KIND_METRICS for each era group; missing cells become empty.

    Returns:
        One row per kind, keyed by era group.
    """
    out = []
    for kind in analysis["kind_topic"]["kinds"]:
        row = {"kind": kind["label"]}
        for group in analysis["kind_topic"]["groups"]:
            cell = kind.get(group) or {}
            row[group] = {metric: cell.get(metric) for metric in KIND_METRICS}
        out.append(row)
    return out


def page_data(analysis: dict) -> dict:
    """Assemble everything the page's charts read from page.json.

    Args:
        analysis: The full analysis.json contents.

    How:
        Picks and reshapes only the results the published sections draw.

    Returns:
        The page.json contents.
    """
    feedback = analysis["feedback"]
    return {
        "headline": analysis["headline"],
        "sankey": sankey(analysis),
        "dispositions": dispositions(analysis),
        "decomposition": decomposition(analysis),
        "kinds": kinds(analysis),
        "topics": analysis["kind_topic"]["topics"],
        "feedback": {"kind": feedback["by_response_kind"]["all_decided"], "latency": feedback["by_latency"]["all_decided"]},
    }


def dots_data(prs: pd.DataFrame) -> dict:
    """One compact record per community PR since launch, oldest first.

    Args:
        prs: The funnel's per-PR table (data/derived/prs.parquet).

    How:
        Stores days since launch rather than timestamps, and positional rows
        rather than objects, to keep the inlined payload small.

    Returns:
        Launch date, field names and the rows.
    """
    community = prs[(prs["author_group"] == "community") & (prs["created_at"] >= LAUNCH)].sort_values("created_at")
    rows = [[
        int(pr.number),
        round((pr.created_at - LAUNCH).total_seconds() / SECONDS_PER_DAY, 2),
        OUTCOME_GROUP[pr.disposition],
        int(pd.notna(pr.h_maintainer_engagement_nobulk)),
        int(bool(pr.mass_close_event)),
        (pr.title or "")[:TITLE_MAX_CHARS],
        pr.topic or "",
    ] for pr in community.itertuples()]
    return {"t0": LAUNCH.date().isoformat(), "fields": ["n", "day", "g", "eng", "mass", "title", "topic"], "rows": rows}


def main() -> None:
    """Write data/results/page.json and data/results/dots.json.

    How:
        Reads analysis.json and the funnel's PR table, then writes both as compact JSON.
    """
    analysis = json.loads((RESULTS / "analysis.json").read_text())
    outputs = {"page.json": page_data(analysis), "dots.json": dots_data(pd.read_parquet(PRS_TABLE))}
    for name, payload in outputs.items():
        path = RESULTS / name
        path.write_text(json.dumps(payload, separators=(",", ":")))
        print(f"{path.relative_to(ROOT)} {path.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()
