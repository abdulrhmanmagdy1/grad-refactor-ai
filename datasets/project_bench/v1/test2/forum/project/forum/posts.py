"""Threads, posts and the rules for editing a post."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from forum import text
from forum.users import User

EDIT_WINDOW = timedelta(minutes=15)
"""How long after posting authors may still edit their own post."""

EDIT_GRACE = timedelta(minutes=2)
"""Edits made this soon after posting are not marked as edited."""


@dataclass
class Post:
    """One message in a thread."""

    post_id: int
    thread_id: int
    author: str
    body: str
    created_at: datetime
    edited_at: datetime | None = None
    hidden: bool = False

    @property
    def mentions(self) -> list[str]:
        """Usernames mentioned in the body, each once, in order of appearance."""
        return text.extract_mentions(self.body)


@dataclass
class Thread:
    """A discussion: a title and its posts, oldest first."""

    thread_id: int
    title: str
    author: str
    created_at: datetime
    locked: bool = False
    pinned: bool = False
    posts: list[Post] = field(default_factory=list)

    def visible_posts(self) -> list[Post]:
        """Posts that were not hidden by moderation."""
        return [p for p in self.posts if not p.hidden]

    def participants(self) -> list[str]:
        """Authors of visible posts, each once, in the order they first posted."""
        seen: dict[str, None] = {}
        for post in self.visible_posts():
            seen.setdefault(post.author.lower(), None)
        return list(seen)


def can_edit(user: User, post: Post, now: datetime) -> bool:
    """Whether ``user`` may edit ``post`` at ``now``.

    Staff may edit any post at any time. Authors may edit their own post until
    EDIT_WINDOW has passed since it was created; nobody else may edit it.
    """
    if user.is_staff:
        return True
    if user.username.lower() != post.author.lower():
        return False
    return (now - post.created_at).seconds < EDIT_WINDOW.total_seconds()


def edit(user: User, post: Post, body: str, now: datetime) -> Post:
    """Replace the body of ``post`` if ``user`` may edit it; records the edit time."""
    if not can_edit(user, post, now):
        raise PermissionError(f"{user.username} cannot edit post {post.post_id}")
    if not body.strip():
        raise ValueError("a post cannot be empty")
    post.body = body
    post.edited_at = now
    return post
