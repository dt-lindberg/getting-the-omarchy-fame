"""Twelve maintainer quotes that show how triage decisions are explained (public GitHub comments)."""

import re

import pandas as pd

from analysis.core.common import DERIVED

# PR number -> (phrase that identifies the comment, theme shown on the page).
VOICE_PICKS = {
    1343: ("too much for the default", "Default scope: keep the default install small"),
    921: ("really like nautilus", "Taste of the maintainer decides defaults"),
    4623: ("400-line change without any context", "Say what is fixed and why"),
    5394: ("too big for Omarchy itself", "Too big: ship it as an optional package"),
    3159: ("open the door to the default starship", "Avoiding a precedent"),
    3330: ("easy for us to add too much", "Complexity cost, even after the work was done"),
    1296: ("maintenance of keeping themes", "Maintenance burden"),
    2752: ("let's just merge this for now", "Merge now, tweak later"),
    12651: ("folded into the OpenCode collector", "Absorbed: credited in another PR"),
    7298: ("redesigned in #13770", "Overtaken by a redesign"),
    11149: ("Automated duplication check", "Duplicates: the earlier PR is kept"),
    9525: ("pulled back out of #14049", "Absorbed, then dropped"),
}
MAX_QUOTE_CHARS = 330


def run(df: pd.DataFrame) -> list[dict]:
    """The picked quotes with PR number, speaker, epoch, outcome and theme.

    How:
        Looks up each maintainer comment on the PR containing the identifying phrase;
        picks whose text cannot be found are skipped rather than invented.
    """
    ev = pd.read_parquet(DERIVED / "events.parquet", columns=["number", "ts", "type", "actor", "actor_role", "text"])
    ev = ev[(ev["type"] == "comment") & (ev["actor_role"] == "maintainer") & ev["number"].isin(VOICE_PICKS) & ev["text"].notna()]
    out = []
    for number, (phrase, theme) in VOICE_PICKS.items():
        hit = ev[(ev["number"] == number) & ev["text"].str.contains(re.escape(phrase), case=False)]
        if hit.empty:
            continue
        row, pr = hit.iloc[0], df.loc[number]
        out.append({"number": int(number), "speaker": row["actor"], "epoch": str(pr["epoch"]), "outcome": pr["disp"],
                    "theme": theme, "quote": re.sub(r"\s+", " ", row["text"]).strip()[:MAX_QUOTE_CHARS]})
    return out
