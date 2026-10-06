"""Stage 2 (converting attention) and the attention-versus-conversion split."""

import pandas as pd

from analysis.core.models import fit_by_group, prepare, spec, to_pre


def conversion_models(df: pd.DataFrame) -> dict:
    """P(success | engaged, decided) with the common features, and with engagement-time features.

    How:
        Only PRs with a maintainer engagement and a final decision count. The second
        model swaps presentation to the pre-attention version and adds who engaged,
        how substantive it was, the wait and what had happened before it.
    """
    common = fit_by_group(df, df["success_if_eng"], spec())
    pre = to_pre(prepare(df))
    extended = fit_by_group(pre, df["success_if_eng"], spec(extra=True))
    return {"common": common, "with_engagement": extended}


def total_success_model(df: pd.DataFrame) -> dict:
    """P(success) among all decided PRs with the same features (silent merges included)."""
    return fit_by_group(df, df["success_f"], spec())


def decomposition(attention: dict, conversion: dict, total: dict) -> dict:
    """Per group and term: effect on being engaged, on success once engaged, and on success overall.

    How:
        Joins the three models on term. Attention and conversion are different
        populations, so the two parts do not sum to the total; they show where a
        feature acts.
    """
    out = {}
    for group in attention:
        rows = {}
        for stage, model in [("attention", attention[group]), ("conversion", conversion[group]), ("total", total[group])]:
            for e in model["effects"]:
                if e["family"] == "control" or e["term"].startswith("ep_"):
                    continue
                rows.setdefault(e["term"], {"term": e["term"], "label": e["label"], "family": e["family"]})[stage] = {
                    "pp": e["ame_pp"], "lo": e["lo"], "hi": e["hi"]}
        out[group] = list(rows.values())
    return out


def run(df: pd.DataFrame, attention_model: dict) -> dict:
    """Stage 2 results and decomposition for the JSON."""
    models = conversion_models(df)
    total = total_success_model(df)
    return {"model": models["common"], "model_with_engagement": models["with_engagement"], "total_model": total,
            "decomposition": decomposition(attention_model, models["common"], total),
            "outcome": "success (merged or absorbed) among engaged PRs that are decided"}
