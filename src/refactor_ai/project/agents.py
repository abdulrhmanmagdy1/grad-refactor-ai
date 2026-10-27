"""Prompts and output parsers of the project review agents (prompt version project-v5).

Seven model roles, each with its own prompt and a strict parser:

- bug finder: suspected bugs in one function;
- quality and security reviewer: problems in one window of a file;
- architecture reviewer: problems in the project's structure, from the project map only;
- finding checker: is one suspected problem real?
- spec tester: pytest tests of what a function is documented to do, and its checker,
  which says whether a failing one shows a wrong function or a wrong test;
- fixer: the whole corrected function for one finding;
- fix reviewer: does the fix address the finding and change nothing else?

Every finding a model reports must quote the code line it is about; the coordinator drops
findings whose quote does not match the file. Outputs are JSON (the fixer returns a code
block and an explanation line). Parsers repair only what is mechanical: a Markdown fence
around the JSON, text before or after it, and a list cut off by the token limit (complete
items are kept). They never ask the model again.
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field

from refactor_ai.contracts import ChatMessage
from refactor_ai.task_format import parse_refactor_output

PROMPT_VERSION = "project-v5"
# How much of the project README the finders see as the description of intended behavior.
MAX_DESCRIPTION = 800
SEVERITIES = ("high", "medium", "low")
MAX_TEXT = 400

FINDER_SYSTEM = (
    "You are a careful senior Python reviewer. Report only problems that you can point to in "
    "the code you are shown, never guesses. Answer with JSON only."
)
FIXER_SYSTEM = (
    "You fix exactly one problem in one Python function. Change only what the fix needs and "
    "keep everything else as it is."
)
REVIEWER_SYSTEM = (
    "You are a strict Python code reviewer. You judge one claim at a time and answer with "
    "JSON only."
)

BUG_PATTERNS = (
    "code that does not do what its docstring, its name or the project description says: "
    "compare every condition, boundary and formula with the documented behavior",
    "a value that should be updated (a counter, a list of open items, a total) but is not",
    "a wrong variable, field or attribute used in a calculation",
    "conditions that test the wrong thing (`is` instead of `==`, inverted tests, off-by-one "
    "boundaries)",
    "a list or dict changed while a loop iterates over it",
    "mutable default arguments that keep state between calls",
    "functions created in a loop that use the loop variable later",
    "variables used before they are set, or computed and never used",
    "missing or wrong return values on some paths",
    "exceptions swallowed silently or raised with the wrong type",
    "wrong operator, argument order or unit",
)


def numbered(code: str, first_line: int) -> str:
    """Code with its file line numbers on the left, as the agents see it."""
    lines = code.rstrip("\n").splitlines()
    width = len(str(first_line + len(lines)))
    return "\n".join(f"{first_line + i:>{width}} | {line}" for i, line in enumerate(lines))


def _description(description: str | None) -> str:
    if not description:
        return ""
    text = description.strip()[:MAX_DESCRIPTION]
    return f"Project description (from its README):\n{text}\n\n"


ELSEWHERE = (
    "Names the code uses but that are not shown (functions, classes, constants, imports) are "
    "defined elsewhere in the project: never report them as undefined or missing."
)


def _known(known: list[str]) -> str:
    if not known:
        return "Already reported: nothing."
    return "Already reported (do not repeat these):\n" + "\n".join(f"- {k}" for k in known)


def bug_messages(
    qualname: str, code: str, first_line: int, known: list[str], description: str | None = None
) -> list[ChatMessage]:
    patterns = "\n".join(f"- {p}" for p in BUG_PATTERNS)
    user = (
        f"{_description(description)}"
        f"Find real bugs in the Python function `{qualname}`. File line numbers are on the left.\n"
        f"Look for:\n{patterns}\n{ELSEWHERE}\n{_known(known)}\n\n"
        'Return JSON: {"findings": [{"line": <line number>, "code": "<the exact code on that '
        'line>", "problem": "<one sentence>", "severity": "high|medium|low"}]}\n'
        'Report at most 3 bugs. If there is no real bug, return {"findings": []}. Do not report '
        "style, naming or missing documentation.\n\n"
        f"```python\n{numbered(code, first_line)}\n```"
    )
    return [
        ChatMessage(role="system", content=FINDER_SYSTEM),
        ChatMessage(role="user", content=user),
    ]


def quality_messages(
    file: str, code: str, first_line: int, known: list[str], description: str | None = None
) -> list[ChatMessage]:
    user = (
        f"{_description(description)}"
        f"Review lines {first_line} to {first_line + code.count(chr(10))} of `{file}` for "
        "security and code-quality problems. File line numbers are on the left.\n"
        "Security: unsafe eval/exec, shell commands built from input, SQL built with string "
        "formatting, file paths built from input without checking that they stay inside the "
        "intended folder, secrets in the code or compared with == instead of a constant-time "
        "comparison, tokens or passwords made with the random module, a missing permission or "
        "ownership check, unsafe deserialization, disabled certificate checks.\n"
        "Quality: functions doing several unrelated things, copy-pasted logic, error handling "
        "that hides failures, magic numbers that should be named, misleading names.\n"
        f"{ELSEWHERE}\n{_known(known)}\n\n"
        'Return JSON: {"findings": [{"line": <line number>, "code": "<the exact code on that '
        'line>", "category": "security|quality", "problem": "<one sentence>", '
        '"recommendation": "<one sentence>", "severity": "high|medium|low"}]}\n'
        'Report at most 4 problems. If there is none, return {"findings": []}.\n\n'
        f"```python\n{numbered(code, first_line)}\n```"
    )
    return [
        ChatMessage(role="system", content=FINDER_SYSTEM),
        ChatMessage(role="user", content=user),
    ]


def architecture_messages(project_map: str, known: list[str]) -> list[ChatMessage]:
    user = (
        "Assess the architecture of this Python project from its module map: dependencies "
        "between modules, cycles, modules with too many responsibilities, layering, coupling "
        "and missing separation of concerns.\n"
        f"{_known(known)}\n\n{project_map}\n\n"
        'Return JSON: {"summary": "<two or three sentences>", "issues": [{"title": "<short>", '
        '"modules": ["<module name from the map>"], "problem": "<one sentence>", '
        '"recommendation": "<one sentence>", "severity": "high|medium|low"}]}\n'
        "Report at most 4 issues, each about modules named in the map."
    )
    return [
        ChatMessage(role="system", content=FINDER_SYSTEM),
        ChatMessage(role="user", content=user),
    ]


def check_messages(title: str, problem: str, code: str, first_line: int) -> list[ChatMessage]:
    user = (
        f"A reviewer claims this problem: {title}. {problem}\n"
        "Is it a real problem in the code below? First compare what the code does with what "
        "its docstring and names say it should do, then decide. Answer not_a_problem if the "
        "claim is wrong, is about code that is not shown, or is only a matter of style.\n\n"
        f"```python\n{numbered(code, first_line)}\n```\n\n"
        'Return JSON: {"reason": "<what the code does and what it should do, one or two '
        'sentences>", "verdict": "real|not_a_problem|unsure"}'
    )
    return [
        ChatMessage(role="system", content=REVIEWER_SYSTEM),
        ChatMessage(role="user", content=user),
    ]


TESTER_SYSTEM = (
    "You write pytest tests that check what Python code is documented to do. You take the "
    "expected results from the documentation, never from the code."
)


def spec_test_messages(
    module: str,
    qualname: str,
    source: str,
    description: str | None = None,
    api: str | None = None,
) -> list[ChatMessage]:
    """Tests of the behavior that `qualname`'s docstring, name and the README promise."""
    related = (
        "Project modules it uses (signatures only; build their objects with these):\n"
        f"```python\n{api.rstrip()}\n```\n\n"
        if api
        else ""
    )
    user = (
        f"{_description(description)}"
        f"{related}"
        f"Module `{module}`:\n```python\n{source.rstrip()}\n```\n\n"
        f"Write at most 3 pytest test functions for `{qualname}`, each checking one behavior "
        "that its docstring, its name or the project description promises, including the "
        "edge cases they mention (limits, empty inputs, inclusive or exclusive bounds). "
        "Take every expected value from the documentation, not from the code: when the code "
        "and the documentation disagree, the test expects what the documentation says. "
        f"Import what you need from `{module}`. Use only the standard library and pytest "
        "(tmp_path for files); no network and no other processes. Name the tests "
        "test_spec_1, test_spec_2 and test_spec_3. Return one ```python code block with the "
        "imports and the tests, nothing else."
    )
    return [
        ChatMessage(role="system", content=TESTER_SYSTEM),
        ChatMessage(role="user", content=user),
    ]


def spec_repair_messages(qualname: str, test_code: str, failures: str) -> list[ChatMessage]:
    """The tester's second try when its tests called the code wrongly."""
    user = (
        f"Your tests for `{qualname}` could not check it: they call the code the wrong way.\n\n"
        f"Tests:\n```python\n{test_code.rstrip()}\n```\n\nErrors:\n{failures.strip()}\n\n"
        "Fix how the tests import, build and call things, using the signatures you were "
        "shown. Keep each test's name and its expected values, which come from the "
        "documentation. Return one ```python code block with the imports and the tests."
    )
    return [
        ChatMessage(role="system", content=TESTER_SYSTEM),
        ChatMessage(role="user", content=user),
    ]


def spec_check_messages(
    qualname: str,
    test_code: str,
    failure: str,
    code: str,
    first_line: int,
    description: str | None = None,
) -> list[ChatMessage]:
    """Is the code wrong, or the test written from its documentation?"""
    user = (
        f"{_description(description)}"
        f"A test written from the documentation of `{qualname}` fails.\n\n"
        f"Test:\n```python\n{test_code.rstrip()}\n```\n\nFailure:\n{failure.strip()}\n\n"
        f"Code:\n```python\n{numbered(code, first_line)}\n```\n\n"
        "Decide which one is wrong. code_wrong: the code does not do what its docstring, "
        "name or the documentation say, and the test expects the documented behavior. "
        "test_wrong: the test expects something the documentation does not promise, or sets "
        "things up wrongly. A value, format or message that the docstring and the project "
        "description do not state (or plainly imply) is the test's guess: test_wrong. First "
        "say what the documentation promises and what the code does.\n"
        'Return JSON: {"reason": "<one or two sentences>", '
        '"verdict": "code_wrong|test_wrong|unsure"}'
    )
    return [
        ChatMessage(role="system", content=REVIEWER_SYSTEM),
        ChatMessage(role="user", content=user),
    ]


def architecture_check_messages(title: str, problem: str, project_map: str) -> list[ChatMessage]:
    user = (
        f"A reviewer claims this architecture problem: {title}. {problem}\n"
        "Is it a real problem of this project, judged from its module map below? Answer "
        "not_a_problem if the claim is wrong, generic, about standard-library imports, or "
        "about modules that are small and simple.\n\n"
        f"{project_map}\n\n"
        'Return JSON: {"reason": "<one sentence>", "verdict": "real|not_a_problem|unsure"}'
    )
    return [
        ChatMessage(role="system", content=REVIEWER_SYSTEM),
        ChatMessage(role="user", content=user),
    ]


def fix_messages(title: str, explanation: str, line: int | None, code: str) -> list[ChatMessage]:
    where = f" (line {line} of the file)" if line else ""
    user = (
        f"Problem{where}: {title}. {explanation}\n\n"
        f"Function:\n```python\n{code.rstrip()}\n```\n\n"
        "Return the whole corrected function in one ```python code block, then one line that "
        'starts with "Explanation:". Keep the function name and parameters unless the problem '
        "is in them. Keep every other condition, check and output as it is. Leave imports "
        "where they are (an import inside the function stays there); only if the fix needs a "
        "new name, put the new import line before the function in the same code block. Do not "
        "add comments or other functions."
    )
    return [
        ChatMessage(role="system", content=FIXER_SYSTEM),
        ChatMessage(role="user", content=user),
    ]


def fix_review_messages(title: str, explanation: str, diff: str) -> list[ChatMessage]:
    user = (
        f"Problem to fix: {title}. {explanation}\n\n"
        f"Proposed change (unified diff of one function):\n```diff\n{diff.rstrip()}\n```\n\n"
        "Accept only if the change fixes this problem and changes nothing else about what the "
        "function does for other inputs. Reject if it does not fix the problem, adds new "
        "behavior, removes or changes a condition, check or output that the problem does not "
        "mention, moves an import, or breaks callers.\n"
        'Return JSON: {"reasons": ["<one sentence>"], "verdict": "accept|reject|uncertain"}'
    )
    return [
        ChatMessage(role="system", content=REVIEWER_SYSTEM),
        ChatMessage(role="user", content=user),
    ]


# --- parsing -------------------------------------------------------------------------


def _objects(text: str) -> list[str]:
    """Every complete top-level JSON object in the text, in order (string-aware)."""
    found, depth, start, in_string, escaped = [], 0, -1, False, False
    for i, char in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            if depth == 0:
                start = i
            depth += 1
        elif char == "}" and depth:
            depth -= 1
            if depth == 0:
                found.append(text[start : i + 1])
    return found


def extract_json(text: str) -> dict | None:
    """The first JSON object in a model output; tolerates fences and surrounding text."""
    cleaned = re.sub(r"```(?:json)?", "", text or "")
    try:
        value = json.loads(cleaned.strip())
        if isinstance(value, dict):
            return value
    except ValueError:
        pass
    for candidate in _objects(cleaned):
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _salvage_items(text: str, key: str) -> list[dict]:
    """Complete objects inside a list cut off by the token limit: {"key": [{...}, {...}, {"""
    marker = re.search('"' + re.escape(key) + r'"\s*:\s*\[', text or "")
    if marker is None:
        return []
    items = []
    for candidate in _objects(text[marker.end() :]):
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            items.append(value)
    return items


def _text(value, limit: int = MAX_TEXT) -> str | None:
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())
    return value[: limit - 3] + "..." if len(value) > limit else value or None


def _severity(value) -> str:
    return value if value in SEVERITIES else "medium"


@dataclass
class Parsed:
    items: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)
    error: str | None = None
    repaired: bool = False


def parse_findings(text: str, *, categories: tuple[str, ...] | None = None) -> Parsed:
    """Findings with line, code, problem and severity (and category when asked)."""
    data = extract_json(text)
    repaired = False
    if data is None or not isinstance(data.get("findings"), list):
        items = _salvage_items(text, "findings")
        if not items and data is None:
            return Parsed(error="unparseable_output")
        repaired = True
    else:
        items = data["findings"]
    findings = []
    for item in items:
        if not isinstance(item, dict):
            continue
        line, code, problem = (
            item.get("line"),
            _text(item.get("code"), 300),
            _text(item.get("problem")),
        )
        if isinstance(line, str) and line.strip().isdigit():
            line = int(line.strip())
        if not isinstance(line, int) or isinstance(line, bool) or not code or not problem:
            continue
        finding = {
            "line": line,
            "code": code,
            "problem": problem,
            "severity": _severity(item.get("severity")),
            "recommendation": _text(item.get("recommendation")),
        }
        if categories is not None:
            category = item.get("category")
            if category not in categories:
                continue
            finding["category"] = category
        findings.append(finding)
    return Parsed(items=findings, repaired=repaired)


def parse_architecture(text: str) -> Parsed:
    data = extract_json(text)
    repaired = False
    if data is None or not isinstance(data.get("issues"), list):
        items = _salvage_items(text, "issues")
        if not items and data is None:
            return Parsed(error="unparseable_output")
        repaired = True
        summary = _text((data or {}).get("summary"), 600)
    else:
        items = data["issues"]
        summary = _text(data.get("summary"), 600)
    issues = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title, problem = _text(item.get("title"), 120), _text(item.get("problem"))
        modules = item.get("modules")
        if not title or not problem or not isinstance(modules, list):
            continue
        issues.append(
            {
                "title": title,
                "problem": problem,
                "modules": [m for m in modules if isinstance(m, str)][:10],
                "recommendation": _text(item.get("recommendation")),
                "severity": _severity(item.get("severity")),
            }
        )
    return Parsed(items=issues, extra={"summary": summary}, repaired=repaired)


def parse_verdict(text: str, allowed: tuple[str, ...]) -> Parsed:
    """A verdict from `allowed` with its reasons; error when no allowed verdict is given."""
    data = extract_json(text)
    if data is None:
        match = re.search(r'"verdict"\s*:\s*"([a-z_]+)"', text or "")
        if match is None or match.group(1) not in allowed:
            return Parsed(error="unparseable_output")
        return Parsed(extra={"verdict": match.group(1), "reasons": []}, repaired=True)
    verdict = data.get("verdict")
    if verdict not in allowed:
        return Parsed(error="invalid_verdict")
    reasons = data.get("reasons")
    if reasons is None and data.get("reason") is not None:
        reasons = [data.get("reason")]
    reasons = (
        [r for r in (_text(r) for r in (reasons or [])) if r][:5]
        if isinstance(reasons, list)
        else []
    )
    return Parsed(extra={"verdict": verdict, "reasons": reasons})


_OPEN_FENCE = re.compile(r"```[a-zA-Z0-9_-]*[ \t]*\n")
_EXPLANATION_LINE = re.compile(r"^[ \t]*Explanation:", re.MULTILINE)


def parse_fix(text: str) -> Parsed:
    """The fixer's corrected function and explanation (the refactor-v2 output format).

    One more repair than the function mode: a code block that is never closed ends at the
    "Explanation:" line (or at the end of the output).
    """
    parsed = parse_refactor_output(text)
    if parsed.error == "unterminated_code_block":
        opening = _OPEN_FENCE.search(text)
        if opening is not None:
            rest = text[opening.end() :]
            label = _EXPLANATION_LINE.search(rest)
            code = rest[: label.start()] if label else rest
            explanation = rest[label.end() :].strip() if label else None
            if code.strip():
                return Parsed(
                    extra={"code": code.rstrip() + "\n", "explanation": _text(explanation)},
                    repaired=True,
                )
    if parsed.error or not parsed.code:
        return Parsed(error=parsed.error or "no_code_block")
    return Parsed(extra={"code": parsed.code, "explanation": _text(parsed.explanation)})


_CODE_BLOCK = re.compile(r"```[a-zA-Z0-9_-]*[ \t]*\n(.*?)(?:```|\Z)", re.DOTALL)
MAX_SPEC_TESTS = 3


def parse_spec_tests(text: str) -> Parsed:
    """The tester's code block: imports and up to three top-level test functions.

    Anything else at the top level (helpers, fixtures, classes) is kept, since tests may
    need it; only the first three test functions are kept, so the tests a fix must pass
    stay few and named.
    """
    match = _CODE_BLOCK.search(text or "")
    code = match.group(1) if match else ""
    if not code.strip():
        return Parsed(error="no_code_block")
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return Parsed(error="does_not_parse")
    tests = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test")
    ]
    if not tests:
        return Parsed(error="no_tests")
    extra = tests[MAX_SPEC_TESTS:]
    tree.body = [node for node in tree.body if node not in extra]
    names = [node.name for node in tests[:MAX_SPEC_TESTS]]
    if len(set(names)) != len(names):
        return Parsed(error="duplicate_test_names")
    return Parsed(extra={"code": ast.unparse(tree) + "\n", "tests": names}, repaired=bool(extra))


# Exceptions that show a test calling the code the wrong way, not the code being wrong.
MISUSE_ERRORS = (
    "TypeError",
    "AttributeError",
    "NameError",
    "ImportError",
    "ModuleNotFoundError",
    "fixture '",
)


def misuse(message: str) -> bool:
    """Whether a failing spec test failed by calling the code wrongly."""
    head = message.strip().splitlines()[0] if message.strip() else ""
    return any(head.startswith(error) or f" {error}" in head for error in MISUSE_ERRORS)


def drop_tests(code: str, names: set[str]) -> str:
    """The test file without the named test functions."""
    tree = ast.parse(code)
    tree.body = [
        node
        for node in tree.body
        if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names)
    ]
    return ast.unparse(tree) + "\n"


def spec_test_source(code: str, name: str) -> str:
    """The source of one test function in a test file."""
    tree = ast.parse(code)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(code, node) or ""
    return ""


def normalize_code(text: str) -> str:
    """Code without any whitespace, so a quote matches however the model spaced it."""
    return "".join(text.split())


def quote_matches(quote: str, lines: list[str], line: int, slack: int = 1) -> int | None:
    """The file line (1-based) within `slack` of `line` whose code the quote matches."""
    wanted = normalize_code(quote)
    if not wanted:
        return None
    for candidate in sorted(range(line - slack, line + slack + 1), key=lambda n: abs(n - line)):
        if not 1 <= candidate <= len(lines):
            continue
        actual = normalize_code(lines[candidate - 1])
        if not actual:
            continue
        if wanted == actual or (len(wanted) >= 6 and wanted in actual):
            return candidate
        if len(actual) >= 6 and actual in wanted and len(wanted) <= len(actual) + 40:
            return candidate
    return None
