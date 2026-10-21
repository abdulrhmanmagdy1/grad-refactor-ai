"""Login sessions identified by bearer tokens, with sliding expiry."""

from __future__ import annotations

import random
import string
import time
from collections.abc import Callable
from dataclasses import dataclass

TOKEN_ALPHABET = string.ascii_letters + string.digits
TOKEN_LENGTH = 40


@dataclass
class Session:
    token: str
    username: str
    created_at: float
    expires_at: float


class SessionStore:
    """Sessions kept in memory.

    A session expires ``idle_timeout`` seconds after it was last used: each
    successful ``validate`` moves the expiry to ``idle_timeout`` seconds after
    that call. No session lives longer than ``max_age`` seconds in total.
    """

    def __init__(
        self,
        idle_timeout: float = 1800.0,
        max_age: float = 43200.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if idle_timeout <= 0 or max_age <= 0:
            raise ValueError("idle_timeout and max_age must be positive")
        self._sessions: dict[str, Session] = {}
        self._idle_timeout = idle_timeout
        self._max_age = max_age
        self._clock = clock

    def __len__(self) -> int:
        return len(self._sessions)

    def _new_token(self) -> str:
        generator = random.SystemRandom()
        return "".join(generator.choices(TOKEN_ALPHABET, k=TOKEN_LENGTH))

    def create(self, username: str) -> Session:
        """Start a session for a user and return it."""
        now = self._clock()
        session = Session(self._new_token(), username, now, now + self._idle_timeout)
        self._sessions[session.token] = session
        return session

    def _is_expired(self, session: Session, now: float) -> bool:
        too_old = now - session.created_at >= self._max_age
        return too_old or now >= session.expires_at

    def validate(self, token: str) -> Session | None:
        """Return the live session for a token, or None; using it extends it."""
        session = self._sessions.get(token)
        if session is None:
            return None
        now = self._clock()
        if self._is_expired(session, now):
            del self._sessions[token]
            return None
        session.expires_at = now + self._idle_timeout
        return session

    def revoke(self, token: str) -> bool:
        """End one session; False when the token was unknown."""
        return self._sessions.pop(token, None) is not None

    def revoke_user(self, username: str) -> int:
        """End every session of one user and return how many there were."""
        tokens = [t for t, s in self._sessions.items() if s.username == username]
        for token in tokens:
            del self._sessions[token]
        return len(tokens)

    def purge_expired(self) -> int:
        """Drop every expired session and return how many were dropped."""
        now = self._clock()
        removed = 0
        for token, session in list(self._sessions.items()):
            if self._is_expired(session, now):
                del self._sessions[token]
                removed += 1
        return removed
