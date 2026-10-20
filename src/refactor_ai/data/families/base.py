"""Building blocks for team-authored template families.

A family is a function that receives a seeded ``random.Random`` and returns one
``Variant``: a realistic small function from one domain whose input checks are nested
conditionals. Families vary names, constants, docstrings, annotations, the order and
style of the checks (continue-when-valid pyramids, error-first ``else`` nesting, elif
chains), statements between the checks and the core logic. Parameter value pools are
chosen by hand so that every branch is reachable; the curation pipeline still measures
this and drops variants whose return and raise statements are not all exercised.

The families were written for this project by the coding agent on behalf of the team.
They contain no code copied from third-party sources.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from refactor_ai.data.codegen import indent, literal

_MISSING = object()
STYLES = ("ok", "bad", "elif")


@dataclass(frozen=True)
class Param:
    """A parameter and the pool of literal values used to generate test inputs."""

    name: str
    values: tuple
    annotation: str | None = None
    default: object = _MISSING
    kw_only: bool = False

    @property
    def has_default(self) -> bool:
        return self.default is not _MISSING

    def source(self, annotate: bool) -> str:
        text = self.name
        if annotate and self.annotation:
            text += f": {self.annotation}"
        if self.has_default:
            text += f"={literal(self.default)}"
        return text


@dataclass(frozen=True)
class Exit:
    """Statements that always end in a return or raise."""

    lines: tuple[str, ...]


def returns(expr: str | None = None, *before: str) -> Exit:
    return Exit((*before, "return" if expr is None else f"return {expr}"))


def raises(
    exception: str, message: str | None = None, *before: str, expr: str | None = None
) -> Exit:
    if expr is not None:
        call = f"{exception}({expr})"
    elif message is not None:
        call = f"{exception}({literal(message)})"
    else:
        call = exception
    return Exit((*before, f"raise {call}"))


@dataclass(frozen=True)
class Check:
    """One input check: ``ok`` lets processing continue, ``bad`` is its negation."""

    ok: str
    bad: str
    fail: Exit
    setup: tuple[str, ...] = ()


@dataclass
class Variant:
    name: str
    params: list[Param]
    checks: list[Check]
    core: list[str]
    styles: list[str]
    doc: str | None = None
    annotate: bool = False
    returns_annotation: str | None = None
    prelude: list[str] = field(default_factory=list)
    tail: list[str] = field(default_factory=list)
    extra_calls: list[tuple[tuple, dict]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if len(self.styles) != len(self.checks):
            raise ValueError("one style per check is required")
        if any(style not in STYLES for style in self.styles):
            raise ValueError(f"unknown style in {self.styles}")

    def signature(self) -> str:
        positional = [p.source(self.annotate) for p in self.params if not p.kw_only]
        keyword = [p.source(self.annotate) for p in self.params if p.kw_only]
        parts = positional + (["*", *keyword] if keyword else [])
        result = (
            f" -> {self.returns_annotation}" if self.annotate and self.returns_annotation else ""
        )
        return f"def {self.name}({', '.join(parts)}){result}:"

    def render(self) -> str:
        body: list[str] = []
        if self.doc:
            body.append(f'"""{self.doc}"""')
        body += self.prelude
        body += _render_checks(self.checks, self.styles, self.core)
        body += self.tail
        return "\n".join([self.signature(), *indent(body)]) + "\n"


def _render_checks(checks: list[Check], styles: list[str], inner: list[str]) -> list[str]:
    if not checks:
        return list(inner)
    first, style = checks[0], styles[0]
    lines = list(first.setup)
    if style == "elif":
        run = [first]
        index = 1
        while index < len(checks) and styles[index] == "elif" and not checks[index].setup:
            run.append(checks[index])
            index += 1
        rest = _render_checks(checks[index:], styles[index:], inner)
        for position, check in enumerate(run):
            lines.append(f"{'if' if position == 0 else 'elif'} {check.bad}:")
            lines += indent(check.fail.lines)
        lines.append("else:")
        lines += indent(rest)
        return lines
    rest = _render_checks(checks[1:], styles[1:], inner)
    if style == "ok":
        lines.append(f"if {first.ok}:")
        lines += indent(rest)
        lines.append("else:")
        lines += indent(first.fail.lines)
    else:
        lines.append(f"if {first.bad}:")
        lines += indent(first.fail.lines)
        lines.append("else:")
        lines += indent(rest)
    return lines


def pick(rng: random.Random, options):
    return options[rng.randrange(len(options))]


def maybe(rng: random.Random, probability: float) -> bool:
    return rng.random() < probability


def choose_styles(rng: random.Random, count: int, *, allow_elif: bool = True) -> list[str]:
    """Overall layout of the checks: pyramid, error-first nesting, elif chain or mixed."""
    roll = rng.random()
    if roll < 0.32:
        return ["ok"] * count
    if roll < 0.56:
        return ["bad"] * count
    if roll < 0.72 and allow_elif and count >= 2:
        return ["elif"] * count
    return [pick(rng, STYLES if allow_elif else ("ok", "bad")) for _ in range(count)]


@dataclass(frozen=True)
class Family:
    key: str
    category: str
    build: Callable[[random.Random], Variant]


FAMILIES: dict[str, Family] = {}


def family(key: str, category: str):
    """Register a template family under a stable key (used as its source group)."""

    def register(build: Callable[[random.Random], Variant]) -> Callable[[random.Random], Variant]:
        if key in FAMILIES:
            raise ValueError(f"duplicate family key {key}")
        FAMILIES[key] = Family(key=key, category=category, build=build)
        return build

    return register
