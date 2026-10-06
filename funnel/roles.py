"""Who is a maintainer, a bot, the PR author or community, in one place."""

from funnel.constants import BOT_LOGINS, DHH, MAINTAINERS


def normalise_login(login: str | None) -> str:
    """Strip the `[bot]` suffix and map missing users to `ghost`.

    Args:
        login: Raw login from the API, possibly None for deleted accounts.

    How:
        Reactions report `greptile-apps[bot]` while timeline actors report
        `greptile-apps`; stripping makes both match.

    Returns:
        Normalised login.
    """
    if not login:
        return "ghost"
    return login[: -len("[bot]")] if login.endswith("[bot]") else login


def is_bot(login: str) -> bool:
    """True for known automation accounts and any `copilot*` account."""
    lowered = login.lower()
    return lowered in BOT_LOGINS or lowered.startswith("copilot")


def author_group(login: str) -> str:
    """Classify a PR author as dhh, bot, core or community."""
    if login == DHH:
        return "dhh"
    if is_bot(login):
        return "bot"
    return "core" if login in MAINTAINERS else "community"


def actor_role(actor: str, pr_author: str) -> str:
    """Role of an actor relative to one PR: author, maintainer, bot or community.

    Args:
        actor: Normalised actor login.
        pr_author: Normalised login of the PR's author.

    How:
        The PR author always counts as author, even for maintainers and bots.

    Returns:
        One of the four role names.
    """
    if actor == pr_author:
        return "author"
    if actor in MAINTAINERS:
        return "maintainer"
    return "bot" if is_bot(actor) else "community"
