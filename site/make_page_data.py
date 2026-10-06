"""Distil analysis.json into the compact shapes the page draws (site/page.json -> data/results/page.json)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
A = json.loads((ROOT / "data/results/analysis.json").read_text())

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


def sankey() -> dict:
    flows = {}
    for link in A["sankey"]["links"]:
        key = (link["attention"], OUTCOME_GROUP.get(link["outcome"], "W"))
        flows[key] = flows.get(key, 0) + link["n"]
    return {"attention": A["sankey"]["attention"], "flows": [[a, g, n] for (a, g), n in flows.items()]}


def quattro_incidence() -> dict:
    """Cumulative incidence of maintainer engagement for the pooled Quattro era (from 2026-08-14)."""
    import numpy as np
    import pandas as pd
    from lifelines import AalenJohansenFitter

    d = pd.read_parquet(ROOT / "data/derived/prs.parquet")
    c = d[(d.author_group == "community") & (d.created_at >= "2026-08-14")]
    fetched = pd.Timestamp(A["meta"]["fetched_at"])
    eng = c.h_maintainer_engagement_nobulk
    res = (c.resolved_at - c.created_at).dt.total_seconds() / 3600
    cen = (fetched - c.created_at).dt.total_seconds() / 3600
    # Engagement is the event; a decision without engagement competes with it; open PRs are censored.
    t = np.where(eng.notna(), eng, np.where(c.resolved_at.notna(), res, cen))
    e = np.where(eng.notna(), 1, np.where(c.resolved_at.notna(), 2, 0))
    aj = AalenJohansenFitter(calculate_variance=False).fit(np.maximum(t, 1e-3) / 24, e, event_of_interest=1)
    cif = aj.cumulative_density_.iloc[:, 0]
    days = A["attention"]["incidence"]["grid_days"]
    return {"n": int(len(c)), "engaged": [round(float(cif[cif.index <= g].iloc[-1]), 4) for g in days]}


def dispositions() -> list:
    rows = []
    for c in A["dispositions"]["counts"]:
        groups = {}
        for k, v in c.items():
            if k == "epoch":
                continue
            g = OUTCOME_GROUP.get(k, "W")
            groups[g] = groups.get(g, 0) + v
        rows.append({"epoch": c["epoch"], **groups})
    # Quattro and Institution are one era on the page: Quattro, from 2026-08-14.
    q = {"epoch": "Q"}
    for r in rows:
        if r["epoch"] in ("E3", "E4"):
            for k, v in r.items():
                if k != "epoch":
                    q[k] = q.get(k, 0) + v
    return [r for r in rows if r["epoch"] not in ("E3", "E4")][:2] + [q] + [r for r in rows if r["epoch"] == "all"]


def decomposition() -> list:
    out = []
    for r in A["decomposition"]["all"]:
        if r["term"] in DECOMP_TERMS:
            out.append({"label": DECOMP_TERMS[r["term"]], "term": r["term"],
                        "att": r.get("attention"), "conv": r.get("conversion"), "tot": r.get("total")})
    return out


def kinds() -> list:
    out = []
    for k in A["kind_topic"]["kinds"]:
        row = {"kind": k["label"]}
        for g in A["kind_topic"]["groups"]:
            cell = k.get(g) or {}
            row[g] = {m: cell.get(m) for m in ("n", "engaged14", "success_if_engaged", "success_decided")}
        out.append(row)
    return out


def artefacts() -> list:
    out = []
    for a in A["artefacts"]:
        allg = a.get("all") or {}
        out.append({"name": a["artefact"], "n": a["n_with"],
                    "with": (allg.get("with") or {}).get("pp"), "without": (allg.get("without") or {}).get("pp"),
                    "hours": (a.get("hours_before_decision") or {}).get("success", {}).get("median")})
    return out


def main() -> None:
    fb = A["feedback"]
    page = {
        "headline": A["headline"],
        "sankey": sankey(),
        "dispositions": dispositions(),
        "incidence": {**A["attention"]["incidence"], "Q": quattro_incidence()},
        "weekly": A["weekly"],
        "breakpoints": A["breakpoints"],
        "decomposition": decomposition(),
        "kinds": kinds(),
        "kind_groups": A["kind_topic"]["groups"],
        "topics_matrix": A["kind_topic"]["matrix"],
        "topics": A["kind_topic"]["topics"],
        "feedback": {"kind": fb["by_response_kind"]["all_decided"], "latency": fb["by_latency"]["all_decided"],
                     "adjusted": fb["adjusted"], "landmark": fb["landmark"], "last": fb["last_response_to_decision_hours"],
                     "cohort": fb["cohort"]},
        "artefacts": artefacts(),
        "rewrites": A["rewrites"],
        "voices": A["voices"],
        "mass": A["mass_close"],
        "competition": A["context"]["competition"],
        "dhh_focus": A["context"]["dhh_focus"],
        "user_prs": A["user_prs"],
        "robustness": A["robustness"]["time_holdout"],
    }
    (ROOT / "data/results/page.json").write_text(json.dumps(page, separators=(",", ":")))
    print("page.json", (ROOT / "data/results/page.json").stat().st_size // 1024, "KiB")


if __name__ == "__main__":
    main()
