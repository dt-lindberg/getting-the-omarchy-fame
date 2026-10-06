"""Checks of the funnel's pure rules: substantive text, epochs, classification, no look-ahead."""

import pandas as pd

from funnel.context import author_history
from funnel.disposition import SUPERSEDED_RE, classify
from funnel.identity import epoch_of
from funnel.text_rules import is_substantive_text


def test_substantive_text_ignores_courtesies():
    assert not is_substantive_text("Thanks!")
    assert not is_substantive_text("lgtm")
    assert not is_substantive_text("any update on this?")
    assert is_substantive_text("This breaks the Hyprland config on reload.")


def test_epoch_boundaries():
    assert epoch_of(pd.Timestamp("2025-06-25T23:59Z")) == "E0"
    assert epoch_of(pd.Timestamp("2025-06-26T00:00Z")) == "E1"
    assert epoch_of(pd.Timestamp("2026-08-18T23:59Z")) == "E3"
    assert epoch_of(pd.Timestamp("2026-08-19T00:00Z")) == "E4"


def test_superseded_wording():
    assert SUPERSEDED_RE.search("Closing in favor of #123")
    assert SUPERSEDED_RE.search("1702cf0be already fixes this crash")
    assert not SUPERSEDED_RE.search("Not a fit for Omarchy.")


def test_classify_precedence():
    row = pd.Series({"merged": False, "state": "closed", "closed_by_role": "author"})
    flags = {"absorbed": False, "duplicate_evidence": True, "mass_closed": True}
    assert classify(row, flags) == "self_closed"
    row["closed_by_role"] = "maintainer"
    assert classify(row, flags) == "superseded_duplicate"
    flags["duplicate_evidence"] = False
    assert classify(row, flags) == "mass_closed"


def test_author_history_counts_only_resolved_successes_before_creation():
    times = pd.to_datetime(["2026-01-01", "2026-01-10", "2026-01-20"], utc=True)
    table = pd.DataFrame({
        "author": ["a", "a", "a"], "author_group": ["community"] * 3, "created_at": times,
        "resolved_at": pd.to_datetime(["2026-01-15", None, None], utc=True),
        "success": [True, False, False]}, index=[1, 2, 3])
    history = author_history(table)
    # PR 2 is created before PR 1 is resolved, so it sees no prior success.
    assert history["author_prior_success"].tolist() == [0, 0, 1]
    assert history["author_prior_prs"].tolist() == [0, 1, 2]
    assert history["author_open_prs_at_creation"].tolist() == [0, 1, 1]
