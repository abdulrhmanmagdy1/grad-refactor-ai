import pytest

from webapp.accounts import AccountError, AccountLocked, AccountService
from webapp.permissions import Role


class Clock:
    def __init__(self, now: float = 1_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def make_service(**kwargs) -> AccountService:
    return AccountService(iterations=1_000, **kwargs)


def test_register_stores_lower_case_names():
    service = make_service()
    user = service.register("  Alice ", "long enough password")
    assert user.username == "alice"
    assert user.role is Role.VIEWER
    assert service.get("ALICE") is user


def test_register_rejects_taken_and_invalid_names():
    service = make_service()
    service.register("alice", "long enough password")
    with pytest.raises(AccountError):
        service.register("Alice", "another long password")
    with pytest.raises(AccountError):
        service.register("a!", "long enough password")


def test_register_rejects_short_passwords():
    with pytest.raises(AccountError):
        make_service().register("bob", "short")


def test_login():
    service = make_service()
    service.register("alice", "long enough password")
    assert service.login("Alice", "long enough password").username == "alice"
    assert service.login("alice", "wrong password") is None
    assert service.login("nobody", "long enough password") is None


def test_account_locks_after_repeated_failures_and_unlocks_later():
    clock = Clock()
    service = make_service(max_failures=3, lockout_seconds=60, clock=clock)
    service.register("alice", "long enough password")
    for _ in range(3):
        assert service.login("alice", "wrong password") is None
    with pytest.raises(AccountLocked):
        service.login("alice", "long enough password")
    clock.now += 61
    assert service.login("alice", "long enough password") is not None


def test_change_password():
    service = make_service()
    service.register("alice", "long enough password")
    with pytest.raises(AccountError):
        service.change_password("alice", "not the password", "a new long password")
    service.change_password("alice", "long enough password", "a new long password")
    assert service.login("alice", "a new long password") is not None


def test_update_profile_collapses_whitespace():
    service = make_service()
    service.register("alice", "long enough password")
    user = service.update_profile("alice", "  Alice   Liddell ")
    assert user.display_name == "Alice Liddell"
    with pytest.raises(AccountError):
        service.update_profile("alice", "x" * 65)


def test_delete():
    service = make_service()
    service.register("alice", "long enough password")
    assert service.delete("ALICE")
    assert not service.delete("alice")
    assert service.all_users() == []
