"""Automatic golden-baseline test synthesizer (Phase 4, FR04, NFR06).

Infers argument value sets from type annotations, default values, and
operation usage, then emits trusted pytest source that asserts the refactored
candidate returns results identical to the original implementation on sampled
inputs (golden-baseline equivalence testing).

Honesty note (NFR06): these are sampled equivalence checks, not a proof of
full semantic equivalence. Behaviour on inputs outside the sampled space is
not verified. Non-deterministic and file/network-touching functions are never
sampled; they are skipped with a recorded reason.
"""

import ast
from typing import Any

_MAX_FUNCTIONS = 4
_CASES_PER_FUNCTION = 2
_MAX_PARAMETERS = 6
_MAX_SOURCE_CHARS = 18_000

_STRING_METHODS = {
    "lower",
    "upper",
    "strip",
    "lstrip",
    "rstrip",
    "split",
    "rsplit",
    "splitlines",
    "startswith",
    "endswith",
    "replace",
    "format",
    "join",
    "title",
    "casefold",
    "capitalize",
    "center",
    "count",
    "find",
    "index",
    "zfill",
    "encode",
    "isdigit",
    "isalpha",
}

_LIST_METHODS = {
    "append",
    "extend",
    "insert",
    "pop",
    "remove",
    "sort",
    "reverse",
    "clear",
    "copy",
}

_DICT_METHODS = {
    "keys",
    "values",
    "items",
    "get",
    "popitem",
    "setdefault",
    "update",
    "fromkeys",
}

# APIs that make two calls produce different results or touch the host system:
# sampling them would produce dishonest failures instead of real signal.
# This list matches *bare calls* only, so a parameter that happens to share a
# name (for example `seed`) never disables sampling by itself.
_SKIPPED_CALL_NAMES = {
    "input",
    "open",
    "id",
    "randint",
    "randrange",
    "uniform",
    "choice",
    "choices",
    "shuffle",
    "sample",
    "getrandbits",
    "uuid1",
    "uuid4",
}

# Modules whose calls are never sampled (non-determinism or host access).
# Deterministic attributes remain fine because the attribute-name check below
# only blocks the host-touching members (now/system/urandom/...).
_SKIPPED_MODULES = {"random", "secrets", "time", "uuid"}

_SKIPPED_ATTR_NAMES = {
    "now",
    "today",
    "utcnow",
    "time",
    "perf_counter",
    "monotonic",
    "urandom",
    "system",
    "popen",
    "getrandom",
}

_CANDIDATES: dict[str, list[Any]] = {
    "int": [2, 7],
    "float": [2.5, -1.0],
    "bool": [True, False],
    "str": ["ab", "xyz"],
    "list": [[1, 2], [3]],
    "list[int]": [[1, 2], [3]],
    "list[str]": [["a", "b"], ["c"]],
    "list[float]": [[1.5, 2.5], [3.5]],
    "dict": [{"a": 1}, {"b": 2}],
    "dict[str, int]": [{"a": 1}, {"b": 2}],
    "dict[str, str]": [{"a": "x"}, {"b": "y"}],
    "set": [{1, 2}, {3}],
    "tuple": [(1, 2), (3,)],
}

_GENERATED_HEADER = '''"""Golden-baseline equivalence tests (NFR06).

Synthesized by AutoTestSynthesizer. Each test calls the refactored `solution`
module and the trusted `reference.py` baseline with the same sampled inputs
and asserts identical observable results (values, failed exception types,
generator/async-generator item sequences).
"""

import asyncio
import copy
import importlib.util
import itertools
import types
from pathlib import Path


def _load(module_name):
    path = Path(__file__).with_name(module_name + ".py")
    spec = importlib.util.spec_from_file_location("sandboxed_" + module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_solution = _load("solution")
_reference = _load("reference")


def _collect_async(agen, limit=10):
    async def consume():
        items = []
        async for item in agen:
            items.append(repr(item))
            if len(items) >= limit:
                break
        return items

    return asyncio.run(consume())


def _normalize(result):
    if isinstance(result, types.CoroutineType):
        return ("awaited", _normalize(asyncio.run(result)))
    if isinstance(result, types.AsyncGeneratorType):
        return ("async_generator", _collect_async(result))
    if isinstance(result, types.GeneratorType):
        return ("generator", [repr(item) for item in itertools.islice(result, 10)])
    return ("value", repr(result))


def _invoke(function, args, kwargs):
    try:
        return _normalize(function(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001 - equivalence compares failure types
        return ("error", type(exc).__name__)


def _compare(name, args, kwargs):
    solution_fn = getattr(_solution, name, None)
    assert solution_fn is not None, f"solution is missing function {name!r}"
    reference_fn = getattr(_reference, name)
    # Fresh argument objects per invocation: a function that mutates its
    # argument must not observe state left behind by the other invocation.
    solution_result = _invoke(solution_fn, copy.deepcopy(args), copy.deepcopy(kwargs))
    reference_result = _invoke(reference_fn, copy.deepcopy(args), copy.deepcopy(kwargs))
    assert solution_result == reference_result, (
        f"{name}({args!r}, {kwargs!r}) diverged: "
        f"solution={solution_result!r} reference={reference_result!r}"
    )
'''


def _annotation_kind(annotation: ast.expr | None) -> str | None:
    """Map a type annotation to a candidate-set key."""
    if annotation is None:
        return None
    text = ast.unparse(annotation).strip().replace("typing.", "")
    text = text.replace(" ", "")
    # Unwrap Optional[...] / A | None unions to their first real member.
    if "|" in text or "Optional[" in text:
        parts = text.replace("Optional[", "").rstrip("]").split("|")
        for part in parts:
            part = part.strip()
            if part and part != "None":
                return _annotation_kind_from_text(part)
        return None
    return _annotation_kind_from_text(text)


def _annotation_kind_from_text(text: str) -> str | None:
    if text in _CANDIDATES:
        return text
    base = text.split("[")[0].strip()
    if base in ("int", "Integer"):
        return "int"
    if base in ("float", "Decimal"):
        return "float"
    if base in ("str", "String"):
        return "str"
    if base == "bool":
        return "bool"
    if base in ("list", "List", "Sequence", "Iterable"):
        return "list"
    if base in ("dict", "Dict", "Mapping"):
        return "dict"
    if base in ("set", "Set"):
        return "set"
    if base in ("tuple", "Tuple"):
        return "tuple"
    return None


def _literal_default(expr: ast.expr) -> Any:
    """Return a JSON-safe literal value for a default, or a sentinel."""
    try:
        value = ast.literal_eval(expr)
    except (ValueError, SyntaxError):
        return _NO_LITERAL
    if value is None:
        return _NO_LITERAL
    if isinstance(value, (bool, int, float, str, list, dict, tuple, set)):
        return value
    return _NO_LITERAL


_NO_LITERAL = object()


def _kind_for_value(value: Any) -> str | None:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, set):
        return "set"
    if isinstance(value, tuple):
        return "tuple"
    return None


def _alternate_value(kind: str, value: Any) -> Any:
    if kind == "bool":
        return not value
    if kind == "int":
        return value + 3
    if kind == "float":
        return value + 1.5
    if kind == "str":
        text = str(value)
        return text + "_alt" if text else "alt"
    if kind == "list":
        return [*value, 0] if isinstance(value, list) else [0]
    if kind == "dict":
        merged = dict(value) if isinstance(value, dict) else {}
        merged["__alt__"] = 1
        return merged
    if kind == "set":
        return {99} if isinstance(value, set) else {99}
    if kind == "tuple":
        return (*value, 9) if isinstance(value, tuple) else (9,)
    return value


def _usage_kind(func: ast.AST, param: str) -> str | None:
    """Infer a candidate kind from how the body uses the parameter."""
    hints: list[str] = []
    for node in ast.walk(func):
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == param
        ):
            index = node.slice
            if isinstance(index, ast.Constant) and isinstance(index.value, int):
                hints.append("list")
            elif isinstance(index, ast.Constant) and isinstance(index.value, str):
                hints.append("dict")
        elif isinstance(node, ast.For) and (
            isinstance(node.iter, ast.Name) and node.iter.id == param
        ):
            hints.append("list")
        elif (
            isinstance(node, ast.BinOp)
            and isinstance(node.left, ast.Name)
            and node.left.id == param
        ):
            if (
                isinstance(node.op, ast.Add)
                and isinstance(node.right, ast.Constant)
                and isinstance(node.right.value, str)
            ):
                hints.append("str")
            elif isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Mod, ast.Div)):
                hints.append("int")
        elif (
            isinstance(node, ast.BinOp)
            and isinstance(node.right, ast.Name)
            and node.right.id == param
        ):
            if (
                isinstance(node.op, ast.Mult)
                and isinstance(node.left, ast.Constant)
                and isinstance(node.left.value, str)
            ):
                hints.append("str")
            elif isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Mod, ast.Div)):
                hints.append("int")
        elif (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Name)
            and node.left.id == param
        ):
            for comparator in node.comparators:
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                    hints.append("str")
                elif isinstance(comparator, ast.Constant) and isinstance(
                    comparator.value, (int, float)
                ):
                    hints.append("int")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == param
        ):
            method = node.func.attr
            if method in _STRING_METHODS:
                hints.append("str")
            elif method in _LIST_METHODS:
                hints.append("list")
            elif method in _DICT_METHODS:
                hints.append("dict")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "len"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == param
        ):
            hints.append("list")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in ("int", "float", "complex", "Decimal")
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == param
        ):
            # `int(text)` implies the text-like case, which also exercises
            # the function's error paths with our string candidates.
            hints.append("str")

    for kind in ("dict", "list", "str", "int", "float"):
        if kind in hints:
            return kind
    return None


def _uses_skipped_api(func: ast.AST) -> str | None:
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name) and callee.id in _SKIPPED_CALL_NAMES:
            return f"calls non-deterministic or host-touching API {callee.id}()"
        if isinstance(callee, ast.Attribute):
            if callee.attr in _SKIPPED_ATTR_NAMES:
                return f"calls time-dependent or host-touching API .{callee.attr}()"
            if isinstance(callee.value, ast.Name) and callee.value.id in _SKIPPED_MODULES:
                return f"calls non-deterministic API {callee.value.id}.{callee.attr}()"
    return None


class AutoTestSynthesizer:
    """Builds golden-baseline pytest source comparing candidate vs original."""

    def __init__(
        self,
        max_functions: int = _MAX_FUNCTIONS,
        cases_per_function: int = _CASES_PER_FUNCTION,
        max_source_chars: int = _MAX_SOURCE_CHARS,
    ) -> None:
        self.max_functions = max_functions
        self.cases_per_function = cases_per_function
        self.max_source_chars = max_source_chars

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def synthesize(self, code: str) -> tuple[str | None, dict[str, Any]]:
        """Return (pytest_source_or_None, metadata)."""
        metadata: dict[str, Any] = {
            "synthesized": False,
            "functions_tested": [],
            "cases": 0,
            "skipped": {},
        }
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            metadata["skipped"]["<module>"] = f"module does not parse: {exc.msg}"
            return None, metadata

        blocks: list[str] = []
        for statement in tree.body:
            if len(blocks) >= self.max_functions:
                break
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            name = statement.name
            if name.startswith("_"):
                metadata["skipped"][name] = "private function"
                continue

            reason = self._skip_reason(statement)
            if reason is not None:
                metadata["skipped"][name] = reason
                continue

            block, case_count = self._build_test_block(statement)
            if block is None:
                metadata["skipped"][name] = "no samplable arguments"
                continue
            if len("\n".join(blocks)) + len(block) + len(_GENERATED_HEADER) > self.max_source_chars:
                metadata["skipped"][name] = "generated source size cap reached"
                continue
            blocks.append(block)
            metadata["functions_tested"].append(name)
            metadata["cases"] += case_count

        if not blocks:
            return None, metadata

        source = _GENERATED_HEADER + "\n\n" + "\n\n".join(blocks) + "\n"
        metadata["synthesized"] = True
        return source, metadata

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _skip_reason(self, func: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
        args = func.args
        if args.vararg or args.kwarg:
            return "variadic signature (*args/**kwargs) cannot be sampled"
        parameter_count = len(args.posonlyargs) + len(args.args) + len(args.kwonlyargs)
        if parameter_count > _MAX_PARAMETERS:
            return "too many parameters to sample honestly"
        return _uses_skipped_api(func)

    def _build_test_block(
        self, func: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> tuple[str | None, int]:
        case_values = self._parameter_cases(func)
        if not case_values:
            # Zero-argument function: a single call is a valid golden sample.
            return (
                f"def test_golden_{func.name}_case_0():\n    _compare({func.name!r}, [], {{}})",
                1,
            )
        case_count = min(
            self.cases_per_function, min(len(values) for values in case_values.values())
        )
        if case_count <= 0:
            return None, 0

        lines: list[str] = []
        for case_index in range(case_count):
            args: list[Any] = []
            kwargs: dict[str, Any] = {}
            for name, values in case_values.items():
                value = values[case_index % len(values)]
                if name in self._kwonly_names(func):
                    kwargs[name] = value
                else:
                    args.append(value)
            lines.append(f"def test_golden_{func.name}_case_{case_index}():")
            lines.append(f"    _compare({func.name!r}, {args!r}, {kwargs!r})")
        return "\n".join(lines), case_count

    @staticmethod
    def _kwonly_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
        return {arg.arg for arg in func.args.kwonlyargs}

    def _parameter_cases(
        self, func: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> dict[str, list[Any]]:
        args = func.args
        positional = list(args.posonlyargs) + list(args.args)
        defaults = list(args.defaults)
        default_offset = len(positional) - len(defaults)
        default_map: dict[str, ast.expr] = {}
        for index, default in enumerate(defaults):
            default_map[positional[default_offset + index].arg] = default
        for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=False):
            if default is not None:
                default_map[arg.arg] = default

        result: dict[str, list[Any]] = {}
        for arg in args.posonlyargs + args.args + args.kwonlyargs:
            result[arg.arg] = self._values_for_parameter(func, arg, default_map.get(arg.arg))
        return result

    def _values_for_parameter(
        self,
        func: ast.FunctionDef | ast.AsyncFunctionDef,
        arg: ast.arg,
        default: ast.expr | None,
    ) -> list[Any]:
        # 1) Explicit annotation wins: it is the strongest public contract.
        kind = _annotation_kind(arg.annotation)
        if kind is not None and kind in _CANDIDATES:
            return list(_CANDIDATES[kind])

        # 2) Literal default values are real, executable examples.
        if default is not None:
            literal = _literal_default(default)
            if literal is not _NO_LITERAL:
                default_kind = _kind_for_value(literal)
                if default_kind is not None:
                    return [literal, _alternate_value(default_kind, literal)]

        # 3) Usage-based inference from the body.
        usage_kind = _usage_kind(func, arg.arg)
        if usage_kind is not None and usage_kind in _CANDIDATES:
            return list(_CANDIDATES[usage_kind])

        # 4) Honest fallback: small integers. Any value type keeps the
        #    equivalence comparison valid (error types are compared too).
        return list(_CANDIDATES["int"])
