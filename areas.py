"""Shared code-area scheme for commits and PR file lists.

Scheme (fine level, one string per file):
  bin/*, migrations/*, manual/*, applications/*, themes/*  -> "bin", "migrations", ...
  test/*                                                   -> "test"
  config/<x>/..., default/<x>/..., install/<x>/...         -> "config/<x>" etc.
  files directly under config/default/install, install.sh,
  boot.sh                                                  -> "config", "default", "install"
  shell/plugins/<name>/...                                 -> "shell/<name>"
  other shell/* (Ui, Commons, services, shell.qml)         -> "shell/core"
  docs/*, agents/*, plans/*                                -> "docs"
  .github/*, dotfiles, AGENTS.md, CLAUDE.md                -> "meta"
  README, LICENSE, version, icon/logo, etc.                -> "root"
  anything else                                            -> its top-level directory
Top level (coarse) is the first path component of the fine area.
"""

_ONE_LEVEL = {"bin", "migrations", "manual", "applications", "themes", "test", "etc"}
_TWO_LEVEL = {"config", "default", "install"}
_DOCS = {"docs", "agents", "plans"}
_ROOT_FILES = {"README.md", "LICENSE", "version", "icon.png", "icon.txt", "logo.svg", "logo.txt"}
_META_FILES = {"AGENTS.md", "CLAUDE.md"}


def area_of(path: str) -> str:
    parts = path.split("/")
    top = parts[0]
    if len(parts) == 1:
        if top in ("install.sh", "boot.sh"):
            return "install"
        if top in _ROOT_FILES:
            return "root"
        if top.startswith(".") or top in _META_FILES:
            return "meta"
        return "root"
    if top in _ONE_LEVEL:
        return top
    if top in _TWO_LEVEL:
        return f"{top}/{parts[1]}" if len(parts) >= 3 else top
    if top == "shell":
        if len(parts) >= 4 and parts[1] == "plugins":
            return f"shell/{parts[2]}"
        return "shell/core"
    if top in _DOCS:
        return "docs"
    if top.startswith("."):
        return "meta"
    return top


def top_of(area: str) -> str:
    return area.split("/")[0]


def pr_areas_from_files(paths, level: str = "fine") -> list[str]:
    """Sorted unique areas for a PR's file list (level 'fine' or 'top')."""
    areas = {area_of(p) for p in paths if p}
    if level == "top":
        areas = {top_of(a) for a in areas}
    return sorted(areas)
