"""Request and response types and a path router with named placeholders."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_PLACEHOLDER = re.compile(r"<([A-Za-z_][A-Za-z0-9_]*)>")


@dataclass
class Request:
    """An incoming request, already parsed by the server in front of the app."""

    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    client_ip: str = "127.0.0.1"
    params: dict[str, str] = field(default_factory=dict)

    def header(self, name: str) -> str | None:
        """Look up a header by name, ignoring case as HTTP does."""
        wanted = name.lower()
        for key, value in self.headers.items():
            if key.lower() == wanted:
                return value
        return None


@dataclass
class Response:
    """What a handler returns: a status code, a JSON-ready body and headers."""

    status: int
    body: dict[str, Any] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)


Handler = Callable[[Request], Response]


@dataclass(frozen=True)
class Route:
    """One registered route: a method, its path template and the compiled pattern."""

    method: str
    template: str
    pattern: re.Pattern[str]
    handler: Handler


def compile_template(template: str) -> re.Pattern[str]:
    """Compile a template such as "/users/<name>" into a regular expression.

    Each placeholder becomes a named group that matches one non-empty path
    segment; the rest of the template must match literally.
    """
    if not template.startswith("/"):
        raise ValueError(f"route templates start with '/': {template!r}")
    pieces: list[str] = []
    position = 0
    for match in _PLACEHOLDER.finditer(template):
        pieces.append(re.escape(template[position : match.start()]))
        pieces.append(f"(?P<{match.group(1)}>[^/]+)")
        position = match.end()
    pieces.append(re.escape(template[position:]))
    return re.compile("".join(pieces))


class Router:
    """Maps a method and a path to the handler registered for them."""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(self, method: str, template: str, handler: Handler) -> None:
        """Register a handler; the same method and template twice is an error."""
        method = method.upper()
        for route in self._routes:
            if route.method == method and route.template == template:
                raise ValueError(f"duplicate route: {method} {template}")
        pattern = compile_template(template)
        self._routes.append(Route(method, template, pattern, handler))

    def dispatch(self, request: Request) -> Response:
        """Call the handler whose template matches the whole path and the method.

        Placeholder values are put in ``request.params``. A path that matches
        only under other methods gets 405 with an Allow header; a path that
        matches no template gets 404.
        """
        method = request.method.upper()
        allowed: set[str] = set()
        for route in self._routes:
            match = route.pattern.fullmatch(request.path)
            if match is None:
                continue
            if route.method != method:
                allowed.add(route.method)
                continue
            request.params = match.groupdict()
            return route.handler(request)
        if allowed:
            headers = {"Allow": ", ".join(sorted(allowed))}
            return Response(405, {"error": "method not allowed"}, headers)
        return Response(404, {"error": "not found"})
