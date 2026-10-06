"""CLI: run the merged analysis and write data/results/analysis.json."""

import json
import warnings

from analysis.context.data import load_prs
from analysis.core import (artefacts, attention, context_effects, conversion, feedback, headline, kind_topic,
                           robustness, users, voices, weekly)
from analysis.core.common import RESULTS_FILE, load_core, round_sig

SCHEMA_NOTE = (
    "Population: community PRs opened since 2025-06-26. Attention = first maintainer engagement with bulk actions removed. "
    "Success = merged or absorbed. 'Quattro' pools E3 and E4. AME = average marginal effect in percentage points for +1 SD "
    "(count terms, on log scale) or 0 to 1 (flags), 95% interval clustered by author. Rates carry Wilson intervals.")


def build() -> dict:
    """Run every module and assemble the result dictionary (top-level keys as in the analysis plan)."""
    df = load_core()
    stage1 = attention.run(df)
    stage2 = conversion.run(df, stage1["model"])
    models = {"attention": stage1["model"], "conversion": stage2["model"], "total": stage2["total_model"]}
    top = headline.run(df, load_prs())
    rew = artefacts.run(df)
    weekly_out = weekly.run(df)
    return {
        "meta": {"schema": SCHEMA_NOTE, "fetched_at": top["headline"]["fetched_at"]},
        "headline": top["headline"], "sankey": top["sankey"], "dispositions": top["dispositions"], "mass_close": top["mass_close"],
        "attention": stage1, "conversion": {k: v for k, v in stage2.items() if k != "decomposition"},
        "decomposition": stage2["decomposition"], "kind_topic": kind_topic.run(df),
        "context": context_effects.run(df, models), "feedback": feedback.run(df),
        "artefacts": rew["artefacts"], "rewrites": rew["rewrites"], "voices": voices.run(df),
        "weekly": {k: weekly_out[k] for k in ("series", "labels", "epoch_starts", "note")},
        "breakpoints": weekly_out["breakpoints"], "robustness": robustness.run(df), "user_prs": users.run(df)}


def main() -> None:
    """Build the results and write them as compact JSON rounded to 3 significant figures."""
    warnings.filterwarnings("ignore")
    result = round_sig(build())
    RESULTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_FILE.write_text(json.dumps(result, separators=(",", ":")))
    print(f"wrote {RESULTS_FILE} ({RESULTS_FILE.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
