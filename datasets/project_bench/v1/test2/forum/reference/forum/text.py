"""Mentions and HTML rendering of posts.

Everything a user typed is escaped before it is placed in HTML.
"""

from __future__ import annotations

import html
import re
from collections.abc import Callable

from forum import posts
from forum.users import User

MENTION_RE = re.compile(r"(?<![\w@])@([A-Za-z0-9_]{3,20})\b")


def extract_mentions(body: str) -> list[str]:
    """Usernames mentioned as ``@name``, lower-cased, each once, in order."""
    seen: dict[str, None] = {}
    for match in MENTION_RE.finditer(body):
        seen.setdefault(match.group(1).lower(), None)
    return list(seen)


def render_body(body: str, is_known: Callable[[str], bool]) -> str:
    """HTML for a post body.

    The text is escaped, blank lines separate paragraphs, single line breaks
    become ``<br>``, and mentions of known users become profile links.
    """

    def link(match: re.Match[str]) -> str:
        name = match.group(1)
        if not is_known(name):
            return match.group(0)
        return f'<a class="mention" href="/u/{name.lower()}">@{name}</a>'

    escaped = html.escape(body.strip())
    paragraphs = [p for p in re.split(r"\n\s*\n", escaped) if p.strip()]
    rendered = [MENTION_RE.sub(link, p).replace("\n", "<br>") for p in paragraphs]
    return "".join(f"<p>{p}</p>" for p in rendered)


def was_edited(post: posts.Post) -> bool:
    """True when the post changed after the grace period that follows posting."""
    return post.edited_at is not None and post.edited_at - post.created_at > posts.EDIT_GRACE


def render_post(post: posts.Post, author: User, is_known: Callable[[str], bool]) -> str:
    """HTML for one post: the author's name, the time, an edited marker and the body."""
    stamp = post.created_at.strftime("%Y-%m-%d %H:%M")
    marker = ' <span class="edited">(edited)</span>' if was_edited(post) else ""
    return (
        f'<article class="post" id="post-{post.post_id}">'
        f'<header><span class="author">{html.escape(author.display_name)}</span>'
        f" <time>{stamp}</time>{marker}</header>"
        f"{render_body(post.body, is_known)}</article>"
    )


def excerpt(body: str, limit: int = 80) -> str:
    """Plain-text start of a body for notifications, cut at a word and ending in '...'."""
    flat = " ".join(body.split())
    if len(flat) <= limit:
        return flat
    cut = flat[: limit - 3].rsplit(" ", 1)[0]
    return cut + "..."
