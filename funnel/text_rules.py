"""Presentation features from a PR title and body, plus the 'substantive text' rule.

Regexes are copied from the earlier omarchy-pr-stats study (pr_features/text.py) so
this project does not depend on it.
"""

import re

CONVENTIONAL_TYPES = (
    "fix|feat|feature|chore|docs|doc|refactor|perf|style|test|tests|build|ci|revert|"
    "bugfix|hotfix|security|deps|wip"
)
CONVENTIONAL_RE = re.compile(rf"^\s*(?:{CONVENTIONAL_TYPES})(?:\([^)]*\))?!?\s*:", re.I)
BRACKET_RE = re.compile(r"^\s*\[[^\]]+\]")
BARE_IMAGE_RE = re.compile(
    r"https?://\S+\.(?:png|jpe?g|gif|webp|bmp)\b|user-images\.githubusercontent\.com", re.I
)
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)")
HTML_IMAGE_RE = re.compile(r"<img\b[^>]*?\bsrc=[\"']([^\"']+)", re.I)
ASSET_URL_RE = re.compile(r"https://github\.com/user-attachments/assets/[\w-]+")
VIDEO_EXT_RE = re.compile(r"https?://\S+\.(?:mp4|mov|webm)\b|<video\b", re.I)
MEASUREMENT_RE = re.compile(
    r"(?<![\w.])\d+(?:[.,]\d+)?\s?(?:ms|s|sec|MiB|MB|GB|KB|fps|×)(?![A-Za-z])"
    r"|\d+(?:[.,]\d+)?\s?%"
    r"|\d+(?:\.\d+)?\s?x\s+(?:faster|slower|smaller|less|more)",
    re.I,
)
LINKS_ISSUE_RE = re.compile(
    r"\b(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?)\b\s*:?\s*(?:[\w.-]+/[\w.-]+)?#\d+", re.I
)
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s", re.M)
BEFORE_AFTER_ADJACENT_RE = re.compile(r"\bbefore\b\s*(?:/|&|-|vs\.?|and)?\s*\bafter\b", re.I)
BEFORE_LABEL_RE = re.compile(r"^\W*before\b[^\n]{0,20}$", re.I | re.M)
AFTER_LABEL_RE = re.compile(r"^\W*after\b[^\n]{0,20}$", re.I | re.M)
AI_MARKER_RE = re.compile(
    r"claude|codex|copilot|chatgpt|openai|gemini|🤖|ai[- ](?:assisted|generated)|\bllm\b", re.I
)
REPRO_RE = re.compile(
    r"steps to reproduce|to reproduce|reproduc\w*|repro steps|how to reproduce|^\s*1[.)]\s", re.I | re.M
)
TESTING_RE = re.compile(
    r"^\s{0,3}(?:#{1,6}\s*|\*\*)?(?:how (?:was it |i |to )?tested|testing|test plan|tested|tests?)\b"
    r"|\b(?:i|was|have|been) tested\b|\btested (?:on|with|by|locally)\b",
    re.I | re.M,
)

# Matches text that is only a courtesy, ping or reaction, not content.
TRIVIAL_RE = re.compile(
    r"^(?:lgtm|looks good(?: to me)?|thanks?(?: you)?(?: so much| a lot)?(?: for (?:the|your) \w+)?|thx|ty|nice|great|cool|"
    r"awesome|\+1|bump|ping|up|any (?:update|news|progress)s?(?: on this| here)?|friendly reminder|merged|done|ok(?:ay)?|"
    r"yes|no|\+\+)\W*$",
    re.I,
)
SENTENCE_SPLIT_RE = re.compile(r"[.!?\n]+")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
URL_RE = re.compile(r"https?://\S+")
MENTION_RE = re.compile(r"@[\w-]+")
MIN_SENTENCE_WORDS = 3


def image_and_video_flags(body: str) -> tuple[bool, bool]:
    """Detect screenshots and videos in a description.

    Args:
        body: PR description markdown.

    How:
        Extension-less user-attachments URLs are images when embedded with image
        syntax and videos when pasted bare, which is how GitHub inserts uploads.

    Returns:
        (has_image, has_video).
    """
    embedded = MD_IMAGE_RE.findall(body) + HTML_IMAGE_RE.findall(body)
    assets = set(ASSET_URL_RE.findall(body))
    embedded_assets = {asset for asset in assets if any(asset in url for url in embedded)}
    has_image = bool(embedded) or bool(BARE_IMAGE_RE.search(body))
    has_video = bool(VIDEO_EXT_RE.search(body)) or bool(assets - embedded_assets)
    return has_image, has_video


def has_before_after(body: str) -> bool:
    """Detect a before/after comparison in a description.

    Args:
        body: PR description markdown.

    How:
        Matches adjacent wording ("before/after", "before vs after") or separate
        Before and After label lines.

    Returns:
        True when either form is present.
    """
    if BEFORE_AFTER_ADJACENT_RE.search(body):
        return True
    return bool(BEFORE_LABEL_RE.search(body) and AFTER_LABEL_RE.search(body))


def presentation_features(title: str, body: str) -> dict:
    """All presentation columns for one title and body (no suffix).

    Args:
        title: PR title at the chosen snapshot.
        body: PR body at the chosen snapshot.

    How:
        Pure regex rules; the caller adds any column suffix.

    Returns:
        Column dictionary.
    """
    has_image, has_video = image_and_video_flags(body)
    stripped = title.strip()
    return {
        "body_chars": len(body),
        "has_image": has_image,
        "has_video": has_video,
        "has_measurements": bool(MEASUREMENT_RE.search(body)),
        "links_issue": bool(LINKS_ISSUE_RE.search(body)),
        "has_before_after": has_before_after(body),
        "has_code_block": "```" in body,
        "has_headings": bool(HEADING_RE.search(body)),
        "ai_marker": bool(AI_MARKER_RE.search(body)),
        "has_repro_steps": bool(REPRO_RE.search(body)),
        "has_testing_section": bool(TESTING_RE.search(body)),
        "title_words": len(stripped.split()),
        "title_conventional_prefix": bool(CONVENTIONAL_RE.match(stripped)),
        "title_bracket_prefix": bool(BRACKET_RE.match(stripped)),
        "title_ends_period": stripped.endswith("."),
    }


def is_substantive_text(text: str) -> bool:
    """True when the text has at least one non-trivial sentence.

    Args:
        text: Comment or review body.

    How:
        Drops HTML comments, quoted lines, URLs and @mentions, then looks for a
        sentence of at least three words that is not a courtesy ('thanks', 'lgtm').

    Returns:
        Whether the text carries content.
    """
    cleaned = HTML_COMMENT_RE.sub(" ", text)
    cleaned = "\n".join(line for line in cleaned.splitlines() if not line.lstrip().startswith(">"))
    cleaned = MENTION_RE.sub(" ", URL_RE.sub(" ", cleaned))
    for sentence in SENTENCE_SPLIT_RE.split(cleaned):
        words = re.findall(r"[^\W\d_]+", sentence)
        if len(words) >= MIN_SENTENCE_WORDS and not TRIVIAL_RE.match(sentence.strip()):
            return True
    return False
