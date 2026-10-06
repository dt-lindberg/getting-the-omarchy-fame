"""Feature sets and the joint logit used for attention, conversion and total success.

One feature specification for all three outcomes so effects can be compared and
split into an attention part and a conversion part.
"""

import numpy as np
import pandas as pd

from analysis.stats import fit_logit, marginal_effects, standardise
from analysis.common import GROUPS, KINDS, in_group

# term -> (family, human label); family drives the page's grouping.
LOGGED = {
    "lines_changed": ("size", "Lines changed"), "changed_files": ("size", "Files changed"),
    "body_chars": ("presentation", "Description length"), "title_words": ("presentation", "Title length (words)"),
    "author_prior_prs": ("author", "Author's earlier PRs"), "author_open_prs_at_creation": ("author", "Author's other open PRs"),
    "backlog_open_community": ("context", "Open community backlog"), "arrivals_prev7d": ("context", "PRs opened in prior 7 days"),
    "maintainer_events_prev7d": ("context", "Maintainer activity, prior 7 days"),
    "dhh_focus_same_area_14d": ("context", "dhh working in same area, prior 14 days"),
    "core_commits_prev7d": ("context", "Core commits, prior 7 days"),
    "direct_competitors_open_at_creation": ("context", "Rival PRs already open"),
}
BINARY = {
    "touches_tests": ("size", "Touches tests"), "docs_only": ("size", "Docs only"),
    "has_image": ("presentation", "Screenshot or image"), "has_video": ("presentation", "Video"),
    "has_measurements": ("presentation", "Measurements"), "links_issue": ("presentation", "Links an issue"),
    "has_before_after": ("presentation", "Before / after"), "has_code_block": ("presentation", "Code block"),
    "has_headings": ("presentation", "Headings"), "ai_marker": ("presentation", "AI marker in text"),
    "has_repro_steps": ("presentation", "Repro steps"), "has_testing_section": ("presentation", "Testing section"),
    "title_conventional_prefix": ("presentation", "fix:/feat: title prefix"), "title_bracket_prefix": ("presentation", "[tag] title prefix"),
    "title_ends_period": ("presentation", "Title ends with a full stop"), "first_pr": ("author", "Author's first PR"),
    "weekend": ("context", "Opened at weekend"), "h06_12": ("context", "Opened 06-12 UTC"),
    "h12_18": ("context", "Opened 12-18 UTC"), "h18_24": ("context", "Opened 18-24 UTC"),
    **{f"kind_{k}": ("kind", f"Kind: {k}") for k in KINDS[1:]},
}
LINEAR = {"author_shrunk_rate": ("author", "Author's earlier success rate (shrunk)")}
COMPACT_TERMS = {"lines_changed", "body_chars", "has_image", "links_issue", "first_pr", "author_shrunk_rate",
                 "backlog_open_community", "dhh_focus_same_area_14d", "direct_competitors_open_at_creation",
                 "kind_feature", "ep_E2", "ep_E3", "ep_E4", "eng_by_dhh", "eng_substantive", "eng_hours_log",
                 "author_edited_pre_eng"}
MIN_FLAG_ROWS = 25
# Thin but workable with author-clustered intervals: below this many events (or non-events) per term the compact set is used.
MIN_EVENTS_PER_TERM = 4
EPOCH_DUMMIES = ["ep_E2", "ep_E3", "ep_E4"]
# Engagement-time features for the stage 2 variant; presentation columns switch to their _pre version.
ENGAGEMENT_BINARY = {"eng_by_dhh": ("engagement", "First engaged by dhh"),
                     "eng_substantive": ("engagement", "First engagement was a real comment or review")}
ENGAGEMENT_LOGGED = {"eng_hours_log": ("engagement", "Wait before first engagement"),
                     "bot_events_pre_eng": ("engagement", "Bot events before engagement"),
                     "community_pre_eng": ("engagement", "Community participants before engagement")}
ENGAGEMENT_EDIT = {"author_edited_pre_eng": ("engagement", "Author edited before engagement")}
LABELS = {**{k: v for k, v in LOGGED.items()}, **BINARY, **LINEAR, **ENGAGEMENT_BINARY, **ENGAGEMENT_LOGGED, **ENGAGEMENT_EDIT}


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Add the engagement-time columns used by the stage 2 variant (no look-ahead)."""
    out = df.copy()
    out["eng_hours_log"] = out["h_maintainer_engagement_nobulk"].fillna(0)
    out["bot_events_pre_eng"] = out["n_bot_events_pre_eng"]
    out["community_pre_eng"] = out["n_community_participants_pre_eng"]
    out["author_edited_pre_eng"] = (out["title_edits_author_pre_eng"] + out["body_edits_author_pre_eng"]) > 0
    for col in ["eng_by_dhh", "eng_substantive"]:
        out[col] = out[col].fillna(False).astype(bool)
    return out


def to_pre(frame: pd.DataFrame) -> pd.DataFrame:
    """Swap open-snapshot presentation columns for their pre-attention versions."""
    out = frame.copy()
    for col in [c for c in BINARY if f"{c}_pre" in out.columns] + ["body_chars", "title_words"]:
        out[col] = out[f"{col}_pre"]
    return out


def spec(extra: bool = False, drop: tuple[str, ...] = ()) -> tuple[list, list, list]:
    """Term lists (logged, binary, linear), optionally with the engagement features."""
    logged = list(LOGGED) + (list(ENGAGEMENT_LOGGED) if extra else [])
    binary = list(BINARY) + EPOCH_DUMMIES + (list(ENGAGEMENT_BINARY) + list(ENGAGEMENT_EDIT) if extra else [])
    linear = list(LINEAR)
    keep = lambda names: [n for n in names if n not in drop]
    return keep(logged), keep(binary), keep(linear)


def fit_effects(df: pd.DataFrame, outcome: pd.Series, terms: tuple[list, list, list]):
    """Fit one clustered logit and return (summary dict, fit, design) for the rows with an outcome.

    Args:
        df: Rows to model.
        outcome: 0/1 with NaN for rows to skip.
        terms: (logged, binary, linear) names.

    How:
        Epoch dummies that are constant inside the rows drop out automatically. If the
        full fit does not converge or gives undefined intervals (too few events for so
        many terms), the compact term set is used instead and the result says so.
    """
    keep = outcome.notna()
    data, y = df[keep], outcome[keep].astype(float)
    out = {"n": int(len(y)), "events": int(y.sum()), "base_pp": float(y.mean() * 100) if len(y) else None, "effects": []}
    minority = min(y.sum(), (1 - y).sum())
    candidates = [("full", terms), ("compact", compact(terms))]
    if minority < MIN_EVENTS_PER_TERM * sum(len(t) for t in terms):
        candidates = candidates[1:]
    for label, current in candidates:
        design, steps = standardise(data, *prune_rare(data, current))
        fit = fit_logit(design, y, data["author"])
        if fit is None or not fit.mle_retvals.get("converged", False):
            continue
        rows = marginal_effects(fit, design, steps)
        if any(not np.isfinite(r["lo"]) for r in rows):
            continue
        out["spec"] = label
        for row in rows:
            family, name = LABELS.get(row["term"], ("control", row["term"]))
            out["effects"].append({**row, "family": family, "label": name})
        return out, fit, design
    return out, None, None


def prune_rare(data: pd.DataFrame, terms: tuple[list, list, list]) -> tuple[list, list, list]:
    """Drop flags with fewer than MIN_FLAG_ROWS rows on either side; they cannot be estimated reliably."""
    logged, binary, linear = terms
    ok = [b for b in binary if min(data[b].sum(), (~data[b].astype(bool)).sum()) >= MIN_FLAG_ROWS]
    return logged, ok, linear


def compact(terms: tuple[list, list, list]) -> tuple[list, list, list]:
    """The compact term set: only terms from the full list that are also in COMPACT_TERMS."""
    return tuple([t for t in names if t in COMPACT_TERMS] for names in terms)


def fit_by_group(df: pd.DataFrame, outcome: pd.Series, terms: tuple[list, list, list]) -> dict:
    """fit_effects for the user-free rows of each epoch group (E1, E2, Quattro, all)."""
    base = df[~df["is_user_pr"]]
    out = {}
    for group in GROUPS:
        rows = in_group(base, group)
        # E3 and E4 dummies sum to one inside the pooled group, so E3 is its reference.
        used = terms if group != "Quattro" else (terms[0], [b for b in terms[1] if b != "ep_E3"], terms[2])
        out[group] = fit_effects(rows, outcome.loc[rows.index], used)[0]
    return out
