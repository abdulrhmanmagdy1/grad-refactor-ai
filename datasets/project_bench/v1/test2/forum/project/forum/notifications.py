"""Notifications for mentions and replies, and each user's inbox."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from forum.posts import Post, Thread
from forum.text import excerpt
from forum.users import UserDirectory


@dataclass
class Notification:
    """Something a user should look at."""

    recipient: str
    kind: str
    post_id: int
    text: str
    read: bool = False


class Inbox:
    """Notifications of every user, oldest first."""

    def __init__(self) -> None:
        self._items: dict[str, list[Notification]] = {}

    def deliver(self, notification: Notification) -> None:
        """Add a notification to its recipient's inbox."""
        self._items.setdefault(notification.recipient.lower(), []).append(notification)

    def all(self, username: str) -> list[Notification]:
        """Every notification of ``username``."""
        return list(self._items.get(username.lower(), []))

    def unread(self, username: str) -> list[Notification]:
        """Notifications of ``username`` not read yet."""
        return [n for n in self._items.get(username.lower(), []) if not n.read]

    def mark_all_read(self, username: str) -> None:
        """Mark every notification of ``username`` as read."""
        for notification in self._items.get(username.lower(), []):
            notification.read = True

    def prune_read(self, username: str) -> int:
        """Delete the read notifications of ``username``; returns how many went."""
        items = self._items.get(username.lower(), [])
        removed = 0
        for notification in list(items):
            if notification.read:
                items.remove(notification)
                removed += 1
        return removed


def mention_jobs(post: Post, users: UserDirectory) -> list[Callable[[], Notification]]:
    """One deferred notification per user mentioned in ``post``.

    The jobs are run once the post is stored, so a post that fails to save
    notifies nobody. Unknown names and the author mentioning themselves are
    skipped.
    """
    jobs: list[Callable[[], Notification]] = []
    for name in post.mentions:
        user = users.find(name)
        if user is None or user.username.lower() == post.author.lower():
            continue
        jobs.append(
            lambda: Notification(
                user.username,
                "mention",
                post.post_id,
                f"{post.author} mentioned you: {excerpt(post.body)}",
            )
        )
    return jobs


def reply_notifications(thread: Thread, post: Post, already: set[str]) -> list[Notification]:
    """Tell earlier participants of ``thread`` about the reply ``post``.

    The author of the reply and anyone in ``already`` (lower-cased usernames,
    e.g. those mentioned in the post) are not notified again.
    """
    skip = already | {post.author.lower()}
    return [
        Notification(name, "reply", post.post_id, f"{post.author} replied in {thread.title}")
        for name in thread.participants()
        if name not in skip
    ]
