"""Robustness: key effects with and without mass-closed PRs, and a time-based holdout."""

import pandas as pd
from sklearn.metrics import roc_auc_score

from analysis.stats import standardise
from analysis.models import fit_effects, spec
from sklearn.linear_model import LogisticRegression

HOLDOUT_START = pd.Timestamp("2026-08-14", tz="UTC")
OUTCOMES = {"attention": "engaged14", "conversion": "success_if_eng", "total": "success_f"}
VARIANTS = {"all_prs": lambda rows: rows, "without_2026-09-21_event": lambda rows: rows[~rows["mass_event"]],
            "without_any_mass_closed": lambda rows: rows[~rows["mass"]]}
# Settings for the holdout logistic regression (C is sklearn's default, kept explicit).
LOGISTIC_MAX_ITER = 2000
LOGISTIC_C = 1.0
DISPLAY_FAMILIES = {"presentation", "size", "author", "kind", "context"}


def mass_closure_sensitivity(df: pd.DataFrame) -> dict:
    """Compare effects under three treatments of mass-closed PRs.

    Args:
        df: Community PRs from load_core.

    How:
        Fits each outcome on all epochs and on Quattro only, with all PRs, without the 2026-09-21
        event and without any mass-closed PR; Quattro drops the E2 and E3 dummies.

    Returns:
        Per outcome and scope: sample sizes and the AME of each displayed term under each variant.
    """
    base = df[~df["is_user_pr"]]
    sensitivity = {}
    for stage, column in OUTCOMES.items():
        sensitivity[stage] = {}
        for scope in ["all", "Quattro"]:
            rows = base if scope == "all" else base[base["epoch"].isin(["E3", "E4"])]
            terms = spec() if scope == "all" else (spec()[0], [flag for flag in spec()[1] if flag not in ("ep_E2", "ep_E3")], spec()[2])
            table = {}
            for variant, keep in VARIANTS.items():
                part = keep(rows)
                result = fit_effects(part, part[column], terms)[0]
                for effect in result["effects"]:
                    if effect["family"] in DISPLAY_FAMILIES:
                        table.setdefault(effect["term"], {"term": effect["term"], "label": effect["label"]})[variant] = effect["ame_pp"]
                table.setdefault("_n", {})[variant] = {"n": result["n"], "events": result["events"]}
            sensitivity[stage][scope] = {"n": table.pop("_n"), "terms": list(table.values())}
    return sensitivity


def holdout(df: pd.DataFrame) -> dict:
    """Train on PRs opened before Quattro and score those after.

    Args:
        df: Community PRs from load_core.

    How:
        Plain logistic regression on the same features (one fit on the training rows, applied
        unchanged to the later rows). Epoch dummies are left out because the later period
        has none of the earlier ones. A low AUC means the earlier relationships do not carry over.

    Returns:
        The split date and, per outcome, sample sizes, observed and mean predicted rates and the AUC.
    """
    base = df[~df["is_user_pr"]]
    logged, binary, linear = spec(drop=("ep_E2", "ep_E3", "ep_E4"))
    design, _ = standardise(base, logged, binary, linear)
    train = (base["created_at"] < HOLDOUT_START).to_numpy()
    result = {"split": HOLDOUT_START.date().isoformat()}
    for stage, column in OUTCOMES.items():
        y = base[column]
        known = y.notna().to_numpy()
        x_tr, y_tr = design[train & known], y[train & known]
        x_te, y_te = design[~train & known], y[~train & known]
        mean, scale = x_tr.mean(), x_tr.std().replace(0, 1)
        model = LogisticRegression(max_iter=LOGISTIC_MAX_ITER, C=LOGISTIC_C).fit(((x_tr - mean) / scale).drop(columns="const"), y_tr)
        predicted = model.predict_proba(((x_te - mean) / scale).drop(columns="const"))[:, 1]
        auc = float(roc_auc_score(y_te, predicted)) if y_te.nunique() > 1 else None
        result[stage] = {"n_train": int(len(y_tr)), "n_test": int(len(y_te)), "observed_train_pp": float(y_tr.mean() * 100),
                         "observed_test_pp": float(y_te.mean() * 100), "predicted_test_pp": float(predicted.mean() * 100),
                         "auc_test": auc}
    return result


def run(df: pd.DataFrame) -> dict:
    """Collect the robustness results for the JSON.

    Args:
        df: Community PRs from load_core.

    How:
        Runs the mass-closure sensitivity and the time holdout.

    Returns:
        Dict with mass_closure, time_holdout and a note on what was skipped.
    """
    return {"mass_closure": mass_closure_sensitivity(df), "time_holdout": holdout(df),
            "skipped": "Within-author fixed-effects models were not run (token budget)."}
