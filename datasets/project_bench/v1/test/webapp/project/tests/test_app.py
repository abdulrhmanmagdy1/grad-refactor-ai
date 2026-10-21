import pytest

from webapp.accounts import AccountService
from webapp.app import WebApp
from webapp.permissions import Role
from webapp.ratelimit import RateLimiter
from webapp.routing import Request
from webapp.sessions import SessionStore

PHRASE = "long enough password"
NEW_PHRASE = "a different long password"
WRONG = "nope nope nope"


@pytest.fixture
def app() -> WebApp:
    return WebApp(
        accounts=AccountService(iterations=1_000),
        sessions=SessionStore(),
        limiter=RateLimiter(limit=1_000, window=60),
    )


def call(app: WebApp, method: str, path: str, bearer: str | None = None, **body):
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    return app.handle(Request(method, path, headers=headers, body=body))


def sign_up(app: WebApp, username: str, role: Role = Role.VIEWER) -> str:
    app.accounts.register(username, PHRASE, role)
    response = call(app, "POST", "/login", username=username, password=PHRASE)
    assert response.status == 200
    return response.body["token"]


def test_register_then_login(app):
    response = call(app, "POST", "/register", username="Alice", password=PHRASE)
    assert response.status == 201
    assert response.body["username"] == "alice"
    login = call(app, "POST", "/login", username="alice", password=PHRASE)
    assert login.status == 200
    assert login.body["token"]


def test_bad_login_is_401(app):
    app.accounts.register("alice", PHRASE)
    response = call(app, "POST", "/login", username="alice", password=WRONG)
    assert response.status == 401


def test_profile_needs_a_session(app):
    app.accounts.register("alice", PHRASE)
    assert call(app, "GET", "/users/alice").status == 401
    assert call(app, "GET", "/users/alice", bearer="made-up").status == 401


def test_show_user(app):
    token = sign_up(app, "alice")
    sign_up(app, "bob")
    response = call(app, "GET", "/users/bob", bearer=token)
    assert response.status == 200
    assert response.body == {"username": "bob", "role": "viewer", "display_name": ""}
    assert call(app, "GET", "/users/nobody", bearer=token).status == 404


def test_users_edit_only_their_own_profile(app):
    alice = sign_up(app, "alice")
    sign_up(app, "bob")
    own = call(app, "PATCH", "/users/alice", bearer=alice, display_name="Alice L")
    assert own.status == 200
    assert own.body["display_name"] == "Alice L"
    other = call(app, "PATCH", "/users/bob", bearer=alice, display_name="Bob")
    assert other.status == 403


def test_admin_changes_roles(app):
    admin = sign_up(app, "root", Role.ADMIN)
    viewer = sign_up(app, "alice")
    assert call(app, "PUT", "/users/alice/role", bearer=viewer, role="admin").status == 403
    response = call(app, "PUT", "/users/alice/role", bearer=admin, role="Editor")
    assert response.status == 200
    assert app.accounts.get("alice").role is Role.EDITOR
    assert call(app, "PUT", "/users/alice/role", bearer=admin, role="god").status == 400


def test_delete_own_account(app):
    alice = sign_up(app, "alice")
    sign_up(app, "bob")
    assert call(app, "DELETE", "/users/bob", bearer=alice).status == 403
    assert call(app, "DELETE", "/users/alice", bearer=alice).status == 204
    assert app.accounts.get("alice") is None
    assert call(app, "GET", "/users/bob", bearer=alice).status == 401


def test_admin_deletes_other_accounts(app):
    admin = sign_up(app, "root", Role.ADMIN)
    sign_up(app, "bob")
    assert call(app, "DELETE", "/users/bob", bearer=admin).status == 204
    assert call(app, "DELETE", "/users/bob", bearer=admin).status == 404


def test_logout_ends_the_session(app):
    token = sign_up(app, "alice")
    assert call(app, "POST", "/logout", bearer=token).status == 204
    assert call(app, "GET", "/users/alice", bearer=token).status == 401


def test_change_password_issues_a_new_token(app):
    old_token = sign_up(app, "alice")
    response = call(
        app,
        "POST",
        "/users/alice/password",
        bearer=old_token,
        old_password=PHRASE,
        new_password=NEW_PHRASE,
    )
    assert response.status == 200
    assert call(app, "GET", "/users/alice", bearer=old_token).status == 401
    assert call(app, "GET", "/users/alice", bearer=response.body["token"]).status == 200
