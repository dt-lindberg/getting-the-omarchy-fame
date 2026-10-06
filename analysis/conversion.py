"""Stage 2 (converting attention) and the attention-versus-conversion split."""

import pandas as pd

from analysis.models import fit_by_group, prepare, spec, to_pre


def conversion_models(df: pd.DataFrame) -> dict:
    """Model P(success | engaged, decided) with the common features, and with engagement-time features.

    Args:
        df: Community PRs from load_core.

    How:
        Only PRs with a maintainer engagement and a final decision count. The second
        model swaps presentation to the pre-attention version and adds who engaged,
        how substantive it was, the wait and what had happened before it.

    Returns:
        Dict with the `common` and `with_engagement` models per epoch group.
    """
    common = fit_by_group(df, df["success_if_eng"], spec())
    pre_attention = to_pre(prepare(df))
    extended = fit_by_group(pre_attention, df["success_if_eng"], spec(extra=True))
    return {"common": common, "with_engagement": extended}


def total_success_model(df: pd.DataFrame) -> dict:
    """Model P(success) among all decided PRs with the same features (silent merges included).

    Args:
        df: Community PRs from load_core.

    How:
        Fits the common feature set on the success outcome of all decided PRs.

    Returns:
        Effects summary per epoch group.
    """
    return fit_by_group(df, df["success_f"], spec())


def decomposition(attention: dict, conversion: dict, total: dict) -> dict:
    """Join each term's effect on being engaged, on success once engaged, and on success overall.

    Args:
        attention: Attention model per epoch group.
        conversion: Conversion model per epoch group.
        total: Total-success model per epoch group.

    How:
        Joins the three models on term. Attention and conversion are different
        populations, so the two parts do not sum to the total; they show where a
        feature acts.

    Returns:
        Per epoch group, one entry per term with its effect (pp and interval) in each stage.
    """
    by_group = {}
    for group in attention:
        rows = {}
        for stage, model in [("attention", attention[group]), ("conversion", conversion[group]), ("total", total[group])]:
            for effect in model["effects"]:
                if effect["family"] == "control" or effect["term"].startswith("ep_"):
                    continue
                rows.setdefault(effect["term"], {"term": effect["term"], "label": effect["label"], "family": effect["family"]})[stage] = {
                    "pp": effect["ame_pp"], "lo": effect["lo"], "hi": effect["hi"]}
        by_group[group] = list(rows.values())
    return by_group


def run(df: pd.DataFrame, attention_model: dict) -> dict:
    """Collect the stage 2 results and decomposition for the JSON.

    Args:
        df: Community PRs from load_core.
        attention_model: Stage 1 model per epoch group.

    How:
        Fits the conversion and total models, then decomposes effects across the three.

    Returns:
        Dict with the models, decomposition and an outcome description.
    """
    models = conversion_models(df)
    total = total_success_model(df)
    return {"model": models["common"], "model_with_engagement": models["with_engagement"], "total_model": total,
            "decomposition": decomposition(attention_model, models["common"], total),
            "outcome": "success (merged or absorbed) among engaged PRs that are decided"}
