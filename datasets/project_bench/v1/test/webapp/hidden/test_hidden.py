import logging
import random
from types import SimpleNamespace

import pytest

from webapp.accounts import AccountLocked, AccountService
from webapp.app import WebApp
from webapp.ratelimit import RateLimiter
from webapp.routing import Request, Response
from webapp.sessions import SessionStore

PHRASE = "long enough password"
WRONG = "not the right one"


def _broken_handler(request: Request) -> Response:
    raise RuntimeError("boom")


# --- seeded issues -------------------------------------------------------------


def test_B1_limiter_rejects_the_request_after_the_limit():
    limiter = RateLimiter(limit=3, window=60, clock=lambda: 0.0)
    assert [limiter.allow("1.2.3.4") for _ in range(4)] == [True, True, True, False]


def test_B2_using_a_session_extends_its_idle_expiry():
    clock = SimpleNamespace(now=0.0)
    store = SessionStore(idle_timeout=100, clock=lambda: clock.now)
    session = store.create("alice")
    clock.now = 90
    assert store.validate(session.token) is not None
    clock.now = 150
    assert store.validate(session.token) is not None


def test_B3_successful_login_resets_the_failure_count():
    service = AccountService(max_failures=3, iterations=1_000, clock=lambda: 1_000.0)
    service.register("alice", PHRASE)
    for _ in range(2):
        assert service.login("alice", WRONG) is None
    assert service.login("alice", PHRASE) is not None
    for _ in range(2):
        assert service.login("alice", WRONG) is None
    assert service.login("alice", PHRASE) is not None


def test_S1_session_tokens_do_not_follow_the_random_module_state():
    random.seed(20261021)
    first = SessionStore().create("alice").token
    random.seed(20261021)
    second = SessionStore().create("alice").token
    assert first != second


# --- behaviour that must keep working -----------------------------------------


def test_keep_limiter_allows_exactly_the_limit():
    limiter = RateLimiter(limit=3, window=60, clock=lambda: 0.0)
    assert all(limiter.allow("a") for _ in range(3))
    assert limiter.allow("b")


def test_keep_limiter_lets_a_client_back_in_after_the_window():
    clock = SimpleNamespace(now=0.0)
    limiter = RateLimiter(limit=2, window=10, clock=lambda: clock.now)
    for _ in range(5):
        limiter.allow("a")
    clock.now = 10
    assert limiter.allow("a")


def test_keep_idle_session_expires():
    clock = SimpleNamespace(now=0.0)
    store = SessionStore(idle_timeout=100, clock=lambda: clock.now)
    session = store.create("alice")
    clock.now = 100
    assert store.validate(session.token) is None


def test_keep_session_cannot_outlive_max_age():
    clock = SimpleNamespace(now=0.0)
    store = SessionStore(idle_timeout=100, max_age=250, clock=lambda: clock.now)
    session = store.create("alice")
    last = session
    for now in (90, 180, 260):
        clock.now = now
        last = store.validate(session.token)
    assert last is None


def test_keep_purge_expired_drops_only_expired_sessions():
    clock = SimpleNamespace(now=0.0)
    store = SessionStore(idle_timeout=100, clock=lambda: clock.now)
    old = [store.create("old") for _ in range(3)]
    clock.now = 50
    fresh = store.create("fresh")
    clock.now = 120
    assert store.purge_expired() == 3
    assert len(store) == 1
    assert all(store.validate(s.token) is None for s in old)
    assert store.validate(fresh.token) is not None


def test_keep_tokens_are_distinct_and_header_safe():
    store = SessionStore()
    tokens = [store.create("alice").token for _ in range(20)]
    assert len(set(tokens)) == 20
    for token in tokens:
        assert len(token) >= 20
        assert token == token.strip()
        assert " " not in token


def test_keep_lockout_after_consecutive_failures():
    service = AccountService(max_failures=3, iterations=1_000, clock=lambda: 1_000.0)
    service.register("alice", PHRASE)
    for _ in range(3):
        service.login("alice", WRONG)
    with pytest.raises(AccountLocked):
        service.login("alice", PHRASE)


def test_keep_handler_errors_are_logged_and_raised_again(caplog):
    app = WebApp(
        accounts=AccountService(iterations=1_000),
        limiter=RateLimiter(limit=100, window=60),
    )
    app.router.add("GET", "/broken", _broken_handler)
    with caplog.at_level(logging.ERROR, logger="webapp.app"):
        with pytest.raises(RuntimeError):
            app.handle(Request("GET", "/broken"))
    assert any("/broken" in record.getMessage() for record in caplog.records)


def test_keep_app_flow_with_login_and_logout():
    app = WebApp(
        accounts=AccountService(iterations=1_000),
        limiter=RateLimiter(limit=100, window=60),
    )
    app.accounts.register("alice", PHRASE)
    body = {"username": "alice", "password": PHRASE}
    login = app.handle(Request("POST", "/login", body=body))
    auth = {"Authorization": "Bearer " + login.body["token"]}
    assert app.handle(Request("GET", "/users/alice", headers=auth)).status == 200
    assert app.handle(Request("POST", "/logout", headers=auth)).status == 204
    assert app.handle(Request("GET", "/users/alice", headers=auth)).status == 401


def test_keep_app_answers_429_over_the_limit():
    app = WebApp(
        accounts=AccountService(iterations=1_000),
        limiter=RateLimiter(limit=2, window=60, clock=lambda: 0.0),
    )
    statuses = [app.handle(Request("GET", "/nowhere")).status for _ in range(5)]
    assert statuses[:2] == [404, 404]
    assert statuses[-1] == 429
