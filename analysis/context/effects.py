"""Adjusted effect estimates for one outcome: the glue between data, controls and stats.

Used by the competition and creation-context modules so both report effects the same way.
"""

import pandas as pd

from analysis.context.data import CONTROL_BINARY, CONTROL_CONTINUOUS, CONTROL_LOGGED
from analysis.context.stats import fit_logit, marginal_effects, standardise


def adjusted_effects(df: pd.DataFrame, outcome: pd.Series, logged: list[str], binary: list[str],
                     linear: list[str] = (), drop: tuple[str, ...] = ()) -> dict:
    """Effects of the listed terms on a 0/1 outcome, adjusted for the shared controls.

    Args:
        df: Rows to model (community PRs).
        outcome: 0/1 per row, NaN rows are dropped.
        logged: Terms of interest entered as log1p (compared at +1 SD).
        binary: Terms of interest coded 0/1.
        linear: Terms of interest entered as they are (compared at +1 SD).
        drop: Controls to leave out because they measure the same thing as a term.

    How:
        Controls (size, direct competition, first PR, author record, epoch) are
        added unless they are themselves a term of interest. Intervals use author
        clusters. Returns n and events so thin cells are visible.

    Returns:
        {"n", "events", "effects": [...]}; effects is empty when the fit fails.
    """
    keep = outcome.notna()
    data, y = df[keep], outcome[keep].astype(float)
    interest = set(logged) | set(binary) | set(linear)
    skip = interest | set(drop)
    design, terms = standardise(
        data,
        logged + [c for c in CONTROL_LOGGED if c not in skip],
        binary + [c for c in CONTROL_BINARY if c not in skip],
        list(linear) + [c for c in CONTROL_CONTINUOUS if c not in skip],
    )
    result = {"n": int(len(y)), "events": int(y.sum()), "effects": []}
    fit = fit_logit(design, y, data["author"])
    if fit is not None:
        result["effects"] = marginal_effects(fit, design, terms, only=list(interest))
        result["base_rate_pp"] = float(y.mean() * 100)
    return result
