"""Robustness: key effects with and without mass-closed PRs, and a time-based holdout."""

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from analysis.context.stats import standardise
from analysis.core.common import GROUPS
from analysis.core.models import fit_effects, spec
from sklearn.linear_model import LogisticRegression

HOLDOUT_START = pd.Timestamp("2026-08-14", tz="UTC")
OUTCOMES = {"attention": "engaged14", "conversion": "success_if_eng", "total": "success_f"}
VARIANTS = {"all_prs": lambda d: d, "without_2026-09-21_event": lambda d: d[~d["mass_event"]], "without_any_mass_closed": lambda d: d[~d["mass"]]}
DISPLAY_FAMILIES = {"presentation", "size", "author", "kind", "context"}


def mass_closure_sensitivity(df: pd.DataFrame) -> dict:
    """AMEs (all epochs, then Quattro only) for each outcome under the three mass-closure treatments."""
    base = df[~df["is_user_pr"]]
    out = {}
    for stage, column in OUTCOMES.items():
        out[stage] = {}
        for scope in ["all", "Quattro"]:
            rows = base if scope == "all" else base[base["epoch"].isin(["E3", "E4"])]
            terms = spec() if scope == "all" else (spec()[0], [b for b in spec()[1] if b not in ("ep_E2", "ep_E3")], spec()[2])
            table = {}
            for variant, keep in VARIANTS.items():
                part = keep(rows)
                result = fit_effects(part, part[column], terms)[0]
                for e in result["effects"]:
                    if e["family"] in DISPLAY_FAMILIES:
                        table.setdefault(e["term"], {"term": e["term"], "label": e["label"]})[variant] = e["ame_pp"]
                table.setdefault("_n", {})[variant] = {"n": result["n"], "events": result["events"]}
            out[stage][scope] = {"n": table.pop("_n"), "terms": list(table.values())}
    return out


def holdout(df: pd.DataFrame) -> dict:
    """Train on PRs opened before Quattro, score those after: AUC, mean predicted and observed rate.

    How:
        Plain logistic regression on the same features (one fit on the training rows, applied
        unchanged to the later rows). Epoch dummies are left out because the later period
        has none of the earlier ones. A low AUC means the earlier relationships do not carry over.
    """
    base = df[~df["is_user_pr"]]
    logged, binary, linear = spec(drop=("ep_E2", "ep_E3", "ep_E4"))
    design, _ = standardise(base, logged, binary, linear)
    train = (base["created_at"] < HOLDOUT_START).to_numpy()
    out = {"split": HOLDOUT_START.date().isoformat()}
    for stage, column in OUTCOMES.items():
        y = base[column]
        known = y.notna().to_numpy()
        x_tr, y_tr = design[train & known], y[train & known]
        x_te, y_te = design[~train & known], y[~train & known]
        mean, scale = x_tr.mean(), x_tr.std().replace(0, 1)
        model = LogisticRegression(max_iter=2000, C=1.0).fit(((x_tr - mean) / scale).drop(columns="const"), y_tr)
        p = model.predict_proba(((x_te - mean) / scale).drop(columns="const"))[:, 1]
        auc = float(roc_auc_score(y_te, p)) if y_te.nunique() > 1 else None
        out[stage] = {"n_train": int(len(y_tr)), "n_test": int(len(y_te)), "observed_train_pp": float(y_tr.mean() * 100),
                      "observed_test_pp": float(y_te.mean() * 100), "predicted_test_pp": float(p.mean() * 100), "auc_test": auc}
    return out


def run(df: pd.DataFrame) -> dict:
    """Robustness results for the JSON."""
    return {"mass_closure": mass_closure_sensitivity(df), "time_holdout": holdout(df),
            "skipped": "Within-author fixed-effects models were not run (token budget)."}
