"""Size, files, areas and maintainer-edit columns for one PR."""

import pandas as pd

from areas import pr_areas_from_files

DOC_SUFFIXES = (".md",)
DOC_DIRS = ("manual/", "docs/")


def is_doc_path(path: str) -> bool:
    """Check whether a path is documentation.

    Args:
        path: File path relative to the repository root.

    How:
        Matches the DOC_DIRS prefixes and DOC_SUFFIXES endings.

    Returns:
        True for files under manual/ or docs/ and any markdown file.
    """
    return path.startswith(DOC_DIRS) or path.endswith(DOC_SUFFIXES)


def size_and_files(base_row: pd.Series) -> dict:
    """Size and file-derived columns from the base record.

    Args:
        base_row: Base PR row (additions, deletions, changed_files, paths, files_total).

    How:
        Paths cover only the first funnel.constants.FILE_LIST_CAP files; files_truncated marks incomplete lists.

    Returns:
        Column dictionary.
    """
    paths = list(base_row["paths"])
    return {
        "additions": base_row["additions"], "deletions": base_row["deletions"],
        "lines_changed": base_row["additions"] + base_row["deletions"],
        "changed_files": base_row["changed_files"], "files_truncated": base_row["files_total"] > len(paths),
        "touches_tests": any(path.startswith("test/") for path in paths),
        "touches_docs": any(is_doc_path(path) for path in paths),
        "docs_only": bool(paths) and all(is_doc_path(path) for path in paths),
        "areas": pr_areas_from_files(paths), "top_areas": pr_areas_from_files(paths, level="top"),
        "labels_now": list(base_row["labels"]),
    }


def maintainer_edits(events: pd.DataFrame) -> dict:
    """Whether maintainers rewrote the title or edited the body, with before/after titles.

    Args:
        events: One PR's events.

    How:
        Uses the first maintainer rename's previous title and the last one's new title.

    Returns:
        Column dictionary.
    """
    renames = events[(events["type"] == "renamed_title") & (events["actor_role"] == "maintainer")]
    return {
        "maintainer_renamed_title": len(renames) > 0,
        "title_before_rename": renames["details"].iloc[0] if len(renames) else None,
        "title_after_rename": renames["details2"].iloc[-1] if len(renames) else None,
        "maintainer_edited_body": bool(((events["type"] == "body_edit") & (events["actor_role"] == "maintainer")).any()),
    }
