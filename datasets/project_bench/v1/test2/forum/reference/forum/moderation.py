"""Bans, reports and thread moderation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from forum.posts import Post, Thread
from forum.users import Role, User, UserDirectory


@dataclass(frozen=True)
class Ban:
    """A ban on posting.

    It starts at ``start`` and ends at ``until`` (exclusive). A ban without an
    end date is permanent.
    """

    username: str
    reason: str
    issued_by: str
    start: datetime
    until: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        """Whether the ban applies at ``now``."""
        return self.start <= now and (self.until is None or now < self.until)


@dataclass(frozen=True)
class Report:
    """A user flagging a post for moderators."""

    post_id: int
    reporter: str
    reason: str


class Moderation:
    """Bans, thread locks and pins, and an audit log of moderator actions."""

    def __init__(self, users: UserDirectory) -> None:
        self._users = users
        self._bans: list[Ban] = []
        self.audit: list[str] = []

    def ban(
        self, actor: User, username: str, reason: str, now: datetime, days: int | None = None
    ) -> Ban:
        """Ban ``username`` for ``days`` days, or permanently when ``days`` is None.

        Only staff may ban, and only users with a lower role than their own.
        """
        target = self._users.get(username)
        if not actor.is_staff or actor.role <= target.role:
            raise PermissionError(f"{actor.username} cannot ban {target.username}")
        until = now + timedelta(days=days) if days is not None else None
        ban = Ban(target.username, reason, actor.username, now, until)
        self._bans.append(ban)
        self.audit.append(f"{now:%Y-%m-%d %H:%M} {actor.username} banned {target.username}")
        return ban

    def lift_bans(self, actor: User, username: str, now: datetime) -> int:
        """End every active ban of ``username`` at ``now``; returns how many ended."""
        if not actor.is_staff:
            raise PermissionError(f"{actor.username} cannot lift bans")
        lifted = 0
        for index, ban in enumerate(self._bans):
            if ban.username.lower() == username.lower() and ban.is_active(now):
                self._bans[index] = Ban(ban.username, ban.reason, ban.issued_by, ban.start, now)
                lifted += 1
        self.audit.append(f"{now:%Y-%m-%d %H:%M} {actor.username} lifted bans of {username}")
        return lifted

    def is_banned(self, username: str, now: datetime) -> bool:
        """Whether any ban of ``username`` is active at ``now``."""
        return any(
            b.username.lower() == username.lower() and b.is_active(now) for b in self._bans
        )

    def lock_thread(self, actor: User, thread: Thread, now: datetime) -> None:
        """Lock ``thread`` so that nobody can reply to it. Staff only."""
        if not actor.is_staff:
            raise PermissionError(f"{actor.username} cannot moderate threads")
        if self.is_banned(actor.username, now):
            raise PermissionError(f"{actor.username} is banned")
        if actor.role < Role.ADMIN and thread.author.lower() == actor.username.lower():
            raise PermissionError("moderators cannot moderate their own threads")
        thread.locked = True
        stamp = now.strftime("%Y-%m-%d %H:%M")
        self.audit.append(f"{stamp} {actor.username} locked thread {thread.thread_id}")

    def pin_thread(self, actor: User, thread: Thread, now: datetime) -> None:
        """Pin ``thread`` to the top of the board. Staff only."""
        if not actor.is_staff:
            raise PermissionError(f"{actor.username} cannot moderate threads")
        if self.is_banned(actor.username, now):
            raise PermissionError(f"{actor.username} is banned")
        if actor.role < Role.ADMIN and thread.author.lower() == actor.username.lower():
            raise PermissionError("moderators cannot moderate their own threads")
        thread.pinned = True
        stamp = now.strftime("%Y-%m-%d %H:%M")
        self.audit.append(f"{stamp} {actor.username} pinned thread {thread.thread_id}")

    def hide_reported(self, posts: list[Post], reports: list[Report], threshold: int) -> list[int]:
        """Hide every post reported by at least ``threshold`` different users.

        Authors reporting their own post do not count. Returns the ids of the
        posts hidden by this call.
        """
        hidden = []
        for post in posts:
            if not post.hidden:
                reporters = set()
                for report in reports:
                    if report.post_id == post.post_id:
                        if report.reporter.lower() != post.author.lower():
                            reporters.add(report.reporter.lower())
                if len(reporters) >= threshold:
                    post.hidden = True
                    hidden.append(post.post_id)
        return hidden
