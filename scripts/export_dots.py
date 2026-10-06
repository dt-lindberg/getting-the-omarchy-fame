"""Export one compact record per community PR for the page's dot chart."""
import json
from pathlib import Path

import pandas as pd

GROUP = {
    "merged": "M", "absorbed": "A", "superseded_duplicate": "S", "self_closed": "C",
    "mass_closed": "W", "bot_admin_closed": "W", "other_closed": "W",
    "maintainer_rejected": "R", "open": "O",
}


def main() -> None:
    prs = pd.read_parquet("data/derived/prs.parquet")
    com = prs[(prs.author_group == "community") & (prs.created_at >= "2025-06-26")].copy()
    com = com.sort_values("created_at")
    t0 = pd.Timestamp("2025-06-26", tz="UTC")
    rows = []
    for r in com.itertuples():
        # Days since launch keeps the payload small; titles are trimmed for the tooltip.
        rows.append([
            int(r.number),
            round((r.created_at - t0).total_seconds() / 86400, 2),
            GROUP[r.disposition],
            int(pd.notna(r.h_maintainer_engagement_nobulk)),
            int(bool(r.mass_close_event)),
            int(bool(r.is_user_pr)),
            (r.title or "")[:90],
            r.topic or "",
        ])
    out = {"t0": "2025-06-26", "fields": ["n", "day", "g", "eng", "mass", "you", "title", "topic"], "rows": rows}
    Path("site/dots.json").write_text(json.dumps(out, separators=(",", ":")))
    print(len(rows), "rows,", Path("site/dots.json").stat().st_size // 1024, "KiB")


if __name__ == "__main__":
    main()
