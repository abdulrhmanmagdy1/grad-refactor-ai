"""The application: handlers that tie accounts, sessions, permissions and limits together."""

from __future__ import annotations

import logging
from collections.abc import Callable

from webapp.accounts import AccountError, AccountLocked, AccountService, User
from webapp.permissions import (
    PermissionDenied,
    Role,
    can_manage_user,
    has_permission,
    parse_role,
    require,
)
from webapp.ratelimit import RateLimiter
from webapp.routing import Handler, Request, Response, Router
from webapp.sessions import Session, SessionStore

log = logging.getLogger(__name__)

AuthenticatedHandler = Callable[[Request, User], Response]


def _error(status: int, message: str) -> Response:
    return Response(status, {"error": message})


def _public(user: User) -> dict[str, str]:
    return {
        "username": user.username,
        "role": user.role.value,
        "display_name": user.display_name,
    }


class WebApp:
    """Routes requests to handlers; all but register and login need a session."""

    def __init__(
        self,
        accounts: AccountService | None = None,
        sessions: SessionStore | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.accounts = accounts if accounts is not None else AccountService()
        self.sessions = sessions if sessions is not None else SessionStore()
        self.limiter = limiter if limiter is not None else RateLimiter(120, 60.0)
        self.router = Router()
        self.router.add("POST", "/register", self.register)
        self.router.add("POST", "/login", self.login)
        self.router.add("POST", "/logout", self.logout)
        self.router.add("GET", "/users/<username>", self._signed_in(self.show_user))
        self.router.add("PATCH", "/users/<username>", self._signed_in(self.update_user))
        self.router.add("DELETE", "/users/<username>", self._signed_in(self.delete_user))
        self.router.add("PUT", "/users/<username>/role", self._signed_in(self.change_role))
        self.router.add(
            "POST", "/users/<username>/password", self._signed_in(self.change_password)
        )

    def handle(self, request: Request) -> Response:
        """Rate-limit by client address, then dispatch.

        Errors raised by handlers are logged with the request line and raised
        again, so the server in front can answer 500.
        """
        if not self.limiter.allow(request.client_ip):
            return _error(429, "too many requests")
        try:
            return self.router.dispatch(request)
        except Exception:
            log.exception("unhandled error in %s %s", request.method, request.path)
            raise

    def current_session(self, request: Request) -> Session | None:
        """The live session named by an "Authorization: Bearer <token>" header."""
        header = request.header("Authorization")
        if header is not None:
            scheme, _, token = header.partition(" ")
            if scheme.lower() == "bearer":
                token = token.strip()
                if token:
                    session = self.sessions.validate(token)
                    if session is not None:
                        if self.accounts.get(session.username) is not None:
                            return session
        return None

    def _signed_in(self, handler: AuthenticatedHandler) -> Handler:
        """Wrap a handler so it only runs for a signed-in user, who is passed in."""

        def wrapper(request: Request) -> Response:
            session = self.current_session(request)
            actor = None if session is None else self.accounts.get(session.username)
            if actor is None:
                return _error(401, "login required")
            return handler(request, actor)

        return wrapper

    def register(self, request: Request) -> Response:
        username = str(request.body.get("username", ""))
        password = str(request.body.get("password", ""))
        try:
            user = self.accounts.register(username, password)
        except AccountError as exc:
            return _error(400, str(exc))
        return Response(201, _public(user))

    def login(self, request: Request) -> Response:
        username = str(request.body.get("username", ""))
        password = str(request.body.get("password", ""))
        try:
            user = self.accounts.login(username, password)
        except AccountLocked:
            return _error(423, "account locked, try again later")
        if user is None:
            return _error(401, "wrong username or password")
        session = self.sessions.create(user.username)
        return Response(200, {"token": session.token, "expires_at": session.expires_at})

    def logout(self, request: Request) -> Response:
        session = self.current_session(request)
        if session is None:
            return _error(401, "login required")
        self.sessions.revoke(session.token)
        return Response(204)

    def show_user(self, request: Request, actor: User) -> Response:
        if not has_permission(actor.role, "profile:read"):
            return _error(403, "not allowed")
        user = self.accounts.get(request.params["username"])
        if user is None:
            return _error(404, "no such user")
        return Response(200, _public(user))

    def update_user(self, request: Request, actor: User) -> Response:
        target = self.accounts.normalize(request.params["username"])
        if not can_manage_user(actor.username, actor.role, target):
            return _error(403, "not allowed")
        try:
            name = str(request.body.get("display_name", ""))
            user = self.accounts.update_profile(target, name)
        except AccountError as exc:
            return _error(400, str(exc))
        return Response(200, _public(user))

    def delete_user(self, request: Request, actor: User) -> Response:
        """Users may delete their own account; deleting another needs user:manage."""
        target = self.accounts.normalize(request.params["username"])
        if actor.username != target and actor.role is not Role.ADMIN:
            return _error(403, "not allowed")
        if not self.accounts.delete(target):
            return _error(404, "no such user")
        self.sessions.revoke_user(target)
        return Response(204)

    def change_role(self, request: Request, actor: User) -> Response:
        try:
            require(actor.role, "user:manage")
            role = parse_role(str(request.body.get("role", "")))
            user = self.accounts.set_role(request.params["username"], role)
        except PermissionDenied:
            return _error(403, "not allowed")
        except ValueError:
            return _error(400, "unknown role")
        except AccountError as exc:
            return _error(404, str(exc))
        return Response(200, _public(user))

    def change_password(self, request: Request, actor: User) -> Response:
        """Users change their own password; every other session of theirs ends."""
        if actor.username != self.accounts.normalize(request.params["username"]):
            return _error(403, "not allowed")
        old = str(request.body.get("old_password", ""))
        new = str(request.body.get("new_password", ""))
        try:
            self.accounts.change_password(actor.username, old, new)
        except AccountError as exc:
            return _error(400, str(exc))
        self.sessions.revoke_user(actor.username)
        session = self.sessions.create(actor.username)
        return Response(200, {"token": session.token})
