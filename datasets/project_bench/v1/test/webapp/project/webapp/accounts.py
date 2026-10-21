"""User accounts: registration, login with lockout, profiles and passwords."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from webapp.passwords import (
    DEFAULT_ITERATIONS,
    hash_password,
    needs_rehash,
    verify_password,
)
from webapp.permissions import Role

USERNAME_PATTERN = re.compile(r"[a-z0-9_]{3,32}")


class AccountError(Exception):
    """A registration, profile change or password change was rejected."""


class AccountLocked(Exception):
    """Login refused because the account is locked after repeated failures."""


@dataclass
class User:
    username: str
    password_hash: str
    role: Role = Role.VIEWER
    display_name: str = ""
    failed_logins: int = 0
    locked_until: float = 0.0


class AccountService:
    """Keeps user accounts in memory.

    Usernames are case-insensitive and stored lower-case. After
    ``max_failures`` failed logins in a row an account is locked for
    ``lockout_seconds``; a successful login starts the count again from zero.
    """

    def __init__(
        self,
        *,
        max_failures: int = 5,
        lockout_seconds: float = 900.0,
        iterations: int = DEFAULT_ITERATIONS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._users: dict[str, User] = {}
        self._max_failures = max_failures
        self._lockout_seconds = lockout_seconds
        self._iterations = iterations
        self._clock = clock
        self._placeholder_hash = hash_password("placeholder password", iterations)

    @staticmethod
    def normalize(username: str) -> str:
        """The stored form of a username."""
        return username.strip().lower()

    def get(self, username: str) -> User | None:
        return self._users.get(self.normalize(username))

    def all_users(self) -> list[User]:
        return sorted(self._users.values(), key=lambda user: user.username)

    def register(self, username: str, password: str, role: Role = Role.VIEWER) -> User:
        """Create an account; AccountError for a bad or taken name or a weak password."""
        name = self.normalize(username)
        if not USERNAME_PATTERN.fullmatch(name):
            raise AccountError("usernames are 3-32 letters, digits or underscores")
        if name in self._users:
            raise AccountError("username already taken")
        if len(password) < 10:
            raise AccountError("passwords need at least 10 characters")
        user = User(name, hash_password(password, self._iterations), role)
        self._users[name] = user
        return user

    def login(self, username: str, password: str) -> User | None:
        """Return the user when the password is right and None when it is not.

        Raises AccountLocked while the account is locked. Unknown usernames
        cost as much time as wrong passwords, so timing does not reveal them.
        """
        user = self.get(username)
        if user is None:
            verify_password(password, self._placeholder_hash)
            return None
        now = self._clock()
        if user.locked_until > now:
            raise AccountLocked(user.username)
        if not verify_password(password, user.password_hash):
            user.failed_logins += 1
            if user.failed_logins >= self._max_failures:
                user.locked_until = now + self._lockout_seconds
                user.failed_logins = 0
            return None
        if needs_rehash(user.password_hash, self._iterations):
            user.password_hash = hash_password(password, self._iterations)
        return user

    def change_password(self, username: str, old_password: str, new_password: str) -> None:
        """Replace a password after checking the current one."""
        user = self.get(username)
        if user is None or not verify_password(old_password, user.password_hash):
            raise AccountError("current password is wrong")
        if len(new_password) < 10:
            raise AccountError("passwords need at least 10 characters")
        user.password_hash = hash_password(new_password, self._iterations)

    def update_profile(self, username: str, display_name: str) -> User:
        """Set the display name, with runs of whitespace collapsed to one space."""
        user = self.get(username)
        if user is None:
            raise AccountError("no such user")
        cleaned = " ".join(display_name.split())
        if len(cleaned) > 64:
            raise AccountError("display names are at most 64 characters")
        user.display_name = cleaned
        return user

    def set_role(self, username: str, role: Role) -> User:
        user = self.get(username)
        if user is None:
            raise AccountError("no such user")
        user.role = role
        return user

    def delete(self, username: str) -> bool:
        """Remove an account; False when there was none."""
        return self._users.pop(self.normalize(username), None) is not None
