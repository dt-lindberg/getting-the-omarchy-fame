"""Paths, buckets and tunable thresholds for the feedback analysis (B)."""

import pandas as pd

from funnel.constants import DERIVED, DHH, MAINTAINERS, ROOT

RESULTS_DIR = ROOT / "data" / "results"
DOCS_DIR = ROOT / "docs"
RESULTS_FILE = RESULTS_DIR / "feedback.json"
FINDINGS_FILE = DOCS_DIR / "findings_feedback.md"

STUDY_START = pd.Timestamp("2025-06-26", tz="UTC")
# E3 is five days long and has four feedback episodes, so it is pooled with E4.
EPOCH_GROUP = {"E1": "E1", "E2": "E2", "E3": "Quattro", "E4": "Quattro"}
EPOCH_GROUPS = ["E1", "E2", "Quattro"]

# Response latency buckets in hours: (label, lower inclusive, upper exclusive).
LATENCY_BUCKETS = [("<6h", 0, 6), ("6-24h", 6, 24), ("1-3d", 24, 72), ("3-7d", 72, 168), (">7d", 168, float("inf"))]
# A PR closed sooner than this after feedback gave the author no real chance to respond.
LANDMARK_HOURS = (24, 168)

N_BOOT = 400
SEED = 20261006
SHORT_RESPONSE_H = 24

POSITIVE_PATTERN = (r"\b(lgtm|looks good|looks great|good to (?:go|merge)|will merge|ready to merge|ship it|"
                    r"nice work|great work|great job|approved)\b")
REQUEST_PATTERN = (r"\?|\b(please|could you|can you|would you|need to|needs to|should|have to|must|"
                   r"can't have|going to need)\b")

__all__ = ["DERIVED", "DHH", "MAINTAINERS"]
