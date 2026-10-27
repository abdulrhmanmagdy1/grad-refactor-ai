"""Forum users and their roles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

USERNAME_RE = re.compile(r"[A-Za-z0-9_]{3,20}")


class Role(IntEnum):
    """What a user may do; a higher role may do everything a lower one can."""

    MEMBER = 1
    MODERATOR = 2
    ADMIN = 3


@dataclass
class User:
    """A registered user.

    ``username`` is the unique handle used in mentions; ``display_name`` is
    free text chosen by the user and shown next to their posts.
    """

    username: str
    display_name: str
    joined: datetime
    role: Role = Role.MEMBER

    @property
    def is_staff(self) -> bool:
        """Moderators and admins."""
        return self.role >= Role.MODERATOR


class UserDirectory:
    """All users, looked up by username without regard to case."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    def add(self, user: User) -> User:
        """Register a user; usernames are unique ignoring case."""
        if not USERNAME_RE.fullmatch(user.username):
            raise ValueError("usernames are 3 to 20 letters, digits or underscores")
        key = user.username.lower()
        if key in self._users:
            raise ValueError(f"username {user.username} is taken")
        self._users[key] = user
        return user

    def find(self, username: str) -> User | None:
        """The user with this username, or None."""
        return self._users.get(username.lower())

    def get(self, username: str) -> User:
        """The user with this username; raises KeyError when there is none."""
        user = self.find(username)
        if user is None:
            raise KeyError(f"unknown user {username}")
        return user

    def __contains__(self, username: object) -> bool:
        return isinstance(username, str) and username.lower() in self._users

    def staff(self) -> list[User]:
        """Moderators and admins, by username."""
        return sorted((u for u in self._users.values() if u.is_staff), key=lambda u: u.username)
