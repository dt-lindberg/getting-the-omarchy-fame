"""The user's three PRs: predicted chances at each stage and where they are in the funnel now."""

import numpy as np
import pandas as pd

from analysis.core.common import DERIVED
from analysis.core.models import ENGAGEMENT_LOGGED, LOGGED, fit_effects, spec


def design_for(rows: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Design rows for the given model columns: log1p for count terms, as-is for the rest, constant 1."""
    cols = {}
    for name in columns:
        if name == "const":
            cols[name] = 1.0
        elif name in LOGGED or name in ENGAGEMENT_LOGGED:
            cols[name] = np.log1p(rows[name].astype(float))
        else:
            cols[name] = rows[name].astype(float)
    return pd.DataFrame(cols, index=rows.index)[columns]


def predict(df: pd.DataFrame, users: pd.DataFrame, column: str) -> pd.Series:
    """Probability for the user's PRs from the all-epochs model of one outcome (fitted without them)."""
    base = df[~df["is_user_pr"]]
    _, fit, _ = fit_effects(base, base[column], spec())
    return fit.predict(design_for(users, list(fit.params.index)))


def position(row: pd.Series) -> dict:
    """Plain description of where one PR stands now, from the event table."""
    ev = pd.read_parquet(DERIVED / "events.parquet", columns=["number", "ts", "type", "actor", "actor_role", "details"])
    ev = ev[ev["number"] == row["number"]]
    kinds = ev.groupby(["actor_role", "type"]).size().reset_index(name="n")
    return {"state": row["state"], "disposition": row["disp"], "created": row["created_at"].isoformat(),
            "maintainer_engagement": bool(row["eng"]), "maintainer_bulk_touch": bool(pd.notna(row["first_maintainer_touch"])),
            "events": kinds.to_dict("records"), "direct_competitors": int(row["direct_competitors"]),
            "rivals_open_at_creation": int(row["direct_competitors_open_at_creation"]),
            "lines_changed": int(row["lines_changed"]), "kind": row["kind"], "topic": row["topic"]}


def run(df: pd.DataFrame) -> dict:
    """User PR predictions and positions for the JSON."""
    users = df[df["is_user_pr"]]
    p_attention = predict(df, users, "engaged14")
    p_conversion = predict(df, users, "success_if_eng")
    return {int(n): {"title": users.loc[n, "title"], "p_engaged_14d_pp": float(p_attention[n] * 100),
                     "p_success_if_engaged_pp": float(p_conversion[n] * 100), "now": position(users.loc[n]),
                     "note": "Predictions from the all-epochs models; trained on 2025-2026 PRs, E4 behaviour is much quieter, so treat the first as an upper bound."}
            for n in users.index}
