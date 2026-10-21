import pytest

from webapp.sessions import SessionStore


class Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def test_create_and_validate():
    store = SessionStore()
    session = store.create("alice")
    assert store.validate(session.token) is session
    assert store.validate("unknown") is None


def test_tokens_are_long_and_distinct():
    store = SessionStore()
    tokens = {store.create("alice").token for _ in range(50)}
    assert len(tokens) == 50
    assert all(len(token) >= 32 for token in tokens)


def test_unused_session_expires():
    clock = Clock()
    store = SessionStore(idle_timeout=100, clock=clock)
    session = store.create("alice")
    clock.now = 100
    assert store.validate(session.token) is None
    assert len(store) == 0


def test_max_age_ends_a_session():
    clock = Clock()
    store = SessionStore(idle_timeout=100, max_age=50, clock=clock)
    session = store.create("alice")
    clock.now = 60
    assert store.validate(session.token) is None


def test_revoke_and_revoke_user():
    store = SessionStore()
    first = store.create("alice")
    store.create("alice")
    other = store.create("bob")
    assert store.revoke(first.token)
    assert not store.revoke(first.token)
    assert store.revoke_user("alice") == 1
    assert store.validate(other.token) is other


def test_bad_settings_are_rejected():
    with pytest.raises(ValueError):
        SessionStore(idle_timeout=0)
