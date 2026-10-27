"""Project review mode, deterministic part: intake, index, project rules and static scan."""

from __future__ import annotations

import ast
import io
import stat
import textwrap
import zipfile
from pathlib import Path

import pytest

from refactor_ai.project import rules, static
from refactor_ai.project.index import (
    build_index,
    complexity,
    module_level_imports,
    module_names,
    project_map,
    reaches,
)
from refactor_ai.project.models import Category, Severity
from refactor_ai.project.workspace import (
    MAX_PYTHON_FILES,
    IntakeError,
    extract_project,
    open_workspace,
)


def make_zip(files: dict[str, str | bytes], **infos: zipfile.ZipInfo) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
        for info in infos.values():
            archive.writestr(info, b"x = 1\n")
    return buffer.getvalue()


def code(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


TRAPS = code(
    '''
    def process_user_sessions(sessions, discount_rate=0.1, session_cache={}):
        """Process user sessions."""
        valid_sessions = []
        multiplier = 2
        tier_multipliers = []
        for level in range(1, 4):
            tier_multipliers.append(lambda x: x * level * discount_rate)
        for session in sessions:
            if session.get("status") == "expired":
                sessions.remove(session)
                continue
            session_code = "SESSION_" + str(discount_rate * 100)
            if session.get("code") is session_code:
                session_cache[session.get("id")] = True
            points = session.get("points", 0)
            if points > 500:
                valid_sessions.append(tier_multipliers[0](points))
            else:
                multiplier = multiplier + 1
        return valid_sessions, session_cache
    '''
)

SHIPPING = code(
    """
    def shipping_cost(weight, express):
        if weight > 0:
            if express:
                return weight * 3
            else:
                return weight * 2
        else:
            raise ValueError("weight must be positive")
    """
)


@pytest.fixture
def sample(tmp_path) -> Path:
    # The project files are text for the scanner to read; nothing here is executed.
    files = {
        "shop/core/__init__.py": "from shop.core import billing\n\n\ndef helper():\n"
        "    return billing.total()\n",
        "shop/core/billing.py": "import os\n\nimport shop.core\n\n\ndef total():\n"
        '    os.system("echo " + "x")\n    return eval("1+1")\n',
        "shop/core/sessions.py": TRAPS + "\n\n" + SHIPPING,
        "shop/README.md": "# Shop\n",
        "shop/.venv/lib/site.py": "x = 1\n",
        "shop/assets/logo.png": b"\x89PNG",
    }
    return tmp_path / "ws", make_zip(files)


# --- intake ---------------------------------------------------------------------------


def test_extract_keeps_allowed_files_and_skips_the_rest(sample):
    destination, data = sample
    workspace = extract_project(data, destination)
    assert workspace.python_files == [
        "shop/core/__init__.py",
        "shop/core/billing.py",
        "shop/core/sessions.py",
    ]
    assert "shop/README.md" in workspace.files
    assert {"path": "shop/assets/logo.png", "reason": "file type is not reviewed"} in (
        workspace.skipped
    )
    assert not (destination / "shop" / ".venv").exists()
    assert workspace.read("shop/core/sessions.py").startswith("def process_user_sessions")
    reopened = open_workspace(destination)
    assert reopened.python_files == workspace.python_files


@pytest.mark.parametrize(
    "name",
    ["/etc/passwd.py", "C:/Windows/x.py", "../escape.py", "a/../../escape.py", "a\\..\\..\\b.py"],
)
def test_unsafe_entries_are_refused(tmp_path, name):
    with pytest.raises(IntakeError) as raised:
        extract_project(make_zip({name: "x = 1\n", "ok.py": "y = 2\n"}), tmp_path / "ws")
    assert raised.value.code == "unsafe_entry"
    assert not (tmp_path / "escape.py").exists()


def test_links_and_encrypted_entries_are_refused(tmp_path):
    link = zipfile.ZipInfo("link.py")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(IntakeError, match="link"):
        extract_project(make_zip({"a.py": "x = 1\n"}, link=link), tmp_path / "one")
    # zipfile cannot write encrypted entries, so set the flag in the central directory.
    data = bytearray(make_zip({"secret.py": "x = 1\n"}))
    central = data.find(b"PK\x01\x02")
    data[central + 8] |= 0x1
    with pytest.raises(IntakeError, match="encrypted"):
        extract_project(bytes(data), tmp_path / "two")


def test_duplicate_names_differing_in_case_are_refused(tmp_path):
    with pytest.raises(IntakeError, match="twice"):
        extract_project(make_zip({"App.py": "a = 1\n", "app.py": "b = 2\n"}), tmp_path / "ws")


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"not a zip", "not_a_zip"),
        (make_zip({"README.md": "# no code\n"}), "no_python_files"),
        (make_zip({f"m{i}.py": "x = 1\n" for i in range(MAX_PYTHON_FILES + 1)}), "too_many_files"),
        (b"x" * 5_000_001, "too_large"),
    ],
    ids=["not-a-zip", "no-python", "too-many-files", "too-large"],
)
def test_unusable_uploads_have_stable_codes(tmp_path, data, code):
    with pytest.raises(IntakeError) as raised:
        extract_project(data, tmp_path / "ws")
    assert raised.value.code == code and raised.value.message


def test_python_size_limit(tmp_path):
    big = "x = 1\n" * 150_000  # 900 kB each, two files exceed 1.5 MB
    with pytest.raises(IntakeError, match="Python files hold"):
        extract_project(make_zip({"a.py": big, "b.py": big}), tmp_path / "ws")


# --- index ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("relative", "packages", "expected"),
    [
        ("app.py", set(), ("app", False, [])),
        ("src/pkg/__init__.py", {"src/pkg"}, ("pkg", True, ["src.pkg"])),
        ("src/pkg/mod.py", {"src/pkg"}, ("pkg.mod", False, ["src.pkg.mod"])),
        ("shop/core/billing.py", {"shop/core"}, ("core.billing", False, ["shop.core.billing"])),
        ("wrapper/tool.py", set(), ("tool", False, ["wrapper.tool"])),
        ("a/b/c.py", {"a", "a/b"}, ("a.b.c", False, [])),
    ],
)
def test_module_names(relative, packages, expected):
    assert module_names(relative, packages) == expected


def test_index_resolves_imports_cycles_and_metrics(sample):
    destination, data = sample
    index = build_index(extract_project(data, destination))
    assert set(index.modules) == {"core", "core.billing", "core.sessions"}
    assert index.modules["core"].imports == {"core.billing"}
    assert index.modules["core.billing"].imports == {"core"}  # through the alias shop.core
    assert index.modules["core.billing"].external_imports == {"os"}
    assert index.cycles == [["core", "core.billing"]]
    assert index.fan_in["core"] == 1 and index.fan_out["core.billing"] == 1
    functions = {f.qualname: f for f in index.functions}
    assert functions["process_user_sessions"].complexity == 6
    assert functions["shipping_cost"].nesting == 2 and functions["shipping_cost"].lines == 8
    summary = index.summary()
    assert summary["python_files"] == 3 and summary["import_cycles"] == 1
    assert summary["test_files"] == 0
    text = project_map(index)
    assert "Import cycles: core -> core.billing" in text and "External imports: os" in text


def test_relative_imports_methods_tests_duplicates_and_parse_errors(tmp_path):
    body = "    total = 0\n    for item in items:\n        total += item\n" * 2
    files = {
        "pkg/__init__.py": "",
        "pkg/a.py": "from . import b\nfrom .b import helper\n\n\nclass Cart:\n"
        "    def add(self, item):\n        return item\n",
        "pkg/b.py": f"def helper(items):\n{body}    return total\n\n\n"
        f"def copy(items):\n{body}    return total\n",
        "pkg/sub/__init__.py": "from .. import a\n",
        "tests/test_a.py": "from pkg.a import Cart\n\n\ndef test_add():\n"
        "    assert Cart().add(1)\n",
        "broken.py": "def oops(:\n",
    }
    index = build_index(extract_project(make_zip(files), tmp_path / "ws"))
    assert index.modules["pkg.a"].imports == {"pkg", "pkg.b"}
    assert index.modules["pkg.sub"].imports == {"pkg", "pkg.a"}
    # tests/ has no __init__.py, so the module is test_a (with the alias tests.test_a).
    assert index.modules["test_a"].is_test and index.has_tests
    assert index.modules["test_a"].imports == {"pkg.a"}
    methods = [f for f in index.functions if f.is_method]
    assert [f.qualname for f in methods] == ["Cart.add"]
    assert [[f.qualname for f in group] for group in index.duplicates] == [["helper", "copy"]]
    assert index.modules["broken"].parse_error.startswith("SyntaxError")


def test_module_level_imports_and_reachability(tmp_path):
    files = {
        "pkg/__init__.py": "",
        "pkg/a.py": "import pkg.b\n",
        "pkg/b.py": "def later():\n    from pkg import c\n",
        "pkg/c.py": "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from pkg import a\n"
        "else:\n    from . import b\n\n\nclass Holder:\n    from .a import b as _b\n",
    }
    index = build_index(extract_project(make_zip(files), tmp_path / "ws"))
    c = index.modules["pkg.c"]
    source = files["pkg/c.py"]
    # TYPE_CHECKING imports and imports inside functions do not run when the module loads;
    # class bodies do; `from . import b` also loads the package itself.
    assert module_level_imports(source, c, index.modules) == {"pkg", "pkg.b", "pkg.a"}
    assert module_level_imports(files["pkg/b.py"], index.modules["pkg.b"], index.modules) == set()
    assert module_level_imports("def (", c, index.modules) == set()
    assert reaches(index, "pkg.a", "pkg.c")  # a -> b -> c (the import inside a function counts)
    assert not reaches(index, "pkg", "pkg.a") and not reaches(index, "missing", "pkg.a")


def test_complexity_counts_decisions_and_boolean_operators():
    tree = ast.parse(
        code(
            """
            def f(a, b, items):
                if a and b or not a:
                    return [x for x in items if x if x > 1]
                while a:
                    try:
                        a -= 1
                    except ValueError:
                        pass
                return 1 if b else 2
            """
        )
    )
    assert complexity(tree.body[0]) == 1 + 1 + 2 + 3 + 1 + 1 + 1


# --- project rules ----------------------------------------------------------------------


def hits(source: str) -> list[tuple[str, int]]:
    return [(hit.rule, hit.line) for hit in rules.check(ast.parse(code(source)))]


def test_rules_find_the_traps():
    assert hits(TRAPS) == [
        ("iterated-list-mutated", 10),
        ("identity-comparison-of-computed-value", 13),
        ("value-never-used", 19),
    ]


def test_iterated_list_rule_cases():
    assert hits("for x in xs:\n    xs.append(x)\n") == [("iterated-list-mutated", 2)]
    assert hits("for x in xs:\n    del xs[0]\n") == [("iterated-list-mutated", 2)]
    assert hits("for x in list(xs):\n    xs.remove(x)\n") == []
    assert hits("for x in xs:\n    ys.remove(x)\n") == []


def test_identity_rule_cases():
    flagged = "def f(a, b):\n    key = f'{a}'\n    return b is key\n"
    assert hits(flagged) == [("identity-comparison-of-computed-value", 3)]
    assert hits("def f(a):\n    return a is None or a is not True\n") == []
    assert hits("def f(a, b):\n    return a is b\n") == []
    assert hits("def f(a):\n    return a is str(a)\n") == [
        ("identity-comparison-of-computed-value", 2)
    ]


def test_value_never_used_rule_cases():
    assert hits("def f():\n    n = 0\n    n += 1\n") == [("value-never-used", 3)]
    assert hits("def f():\n    n = 0\n    n = n + 1\n    return n\n") == []
    assert hits("def f(n):\n    n = n + 1\n") == []  # an argument
    assert hits("def f():\n    global n\n    n = n + 1\n") == []
    closure = "def f():\n    n = 0\n    def g():\n        return n\n    n = n + 1\n    return g\n"
    assert hits(closure) == []


# --- static scan ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        (None, (Category.BUG, Severity.HIGH)),
        ("B006", (Category.BUG, Severity.HIGH)),
        ("B018", (Category.BUG, Severity.MEDIUM)),
        ("PLE0101", (Category.BUG, Severity.HIGH)),
        ("S307", (Category.SECURITY, Severity.HIGH)),
        ("S311", (Category.SECURITY, Severity.LOW)),
        ("S324", (Category.SECURITY, Severity.MEDIUM)),
        ("E722", (Category.QUALITY, Severity.MEDIUM)),
        ("F401", (Category.QUALITY, Severity.LOW)),
        # flake8-simplify codes start with S too; they are not security rules.
        ("SIM102", (Category.QUALITY, Severity.LOW)),
    ],
)
def test_classify_ruff(rule, expected):
    assert static.classify_ruff(rule) == expected


def test_scan_finds_bugs_security_architecture_and_refactorings(sample):
    destination, data = sample
    workspace = extract_project(data, destination)
    findings, warnings = static.scan(workspace, build_index(workspace))
    assert warnings == []
    by_source = {(f.source, f.line_start): f for f in findings}
    expected = {
        ("static:ruff:B006", 1),
        ("static:ruff:B023", 7),
        ("static:rule:iterated-list-mutated", 10),
        ("static:rule:identity-comparison-of-computed-value", 13),
        ("static:rule:value-never-used", 19),
        ("static:ruff:S605", 7),
        ("static:ruff:S307", 8),
        ("static:index:import-cycle", None),
        ("static:index:no-tests", None),
        ("static:task:guard_clauses", 23),
    }
    assert expected <= set(by_source)
    assert by_source[("static:ruff:B006", 1)].symbol == "process_user_sessions"
    assert by_source[("static:ruff:B006", 1)].fixable
    cycle = by_source[("static:index:import-cycle", None)]
    assert cycle.category is Category.ARCHITECTURE and not cycle.fixable
    assert "core -> core.billing -> core" in cycle.explanation
    guard = by_source[("static:task:guard_clauses", 23)]
    assert guard.category is Category.REFACTORING and "from 2 to 1" in guard.explanation


def test_index_thresholds(tmp_path):
    branches = "".join(f"    if x == {i}:\n        y += {i}\n" for i in range(12))
    deep = code(
        """
        def deep(a):
            if a:
                for b in a:
                    while b:
                        if b:
                            b -= 1
        """
    )
    files = {
        "big.py": f"def branchy(x):\n    y = 0\n{branches}    return y\n\n\n{deep}\n\n"
        "def many(a, b, c, d, e, f, g):\n    return a\n",
    }
    workspace = extract_project(make_zip(files), tmp_path / "ws")
    found = {f.source: f for f in static.index_findings(build_index(workspace))}
    assert found["static:index:high-complexity"].symbol == "branchy"
    assert found["static:index:deep-nesting"].symbol == "deep"
    assert found["static:index:many-parameters"].symbol == "many"


def test_ruff_problems_become_warnings(tmp_path, monkeypatch):
    workspace = extract_project(make_zip({"a.py": "x = 1\n"}), tmp_path / "ws")

    def fail(*args, **kwargs):
        raise OSError("no ruff")

    monkeypatch.setattr(static.subprocess, "run", fail)
    findings, warnings = static.scan(workspace, build_index(workspace))
    assert warnings == ["ruff could not run: OSError", "mypy could not run: OSError"]
    assert all(not f.source.startswith("static:ruff") for f in findings)


def test_mypy_reports_defects_and_skips_annotation_noise(tmp_path):
    from refactor_ai.project import typecheck

    files = {
        "app/__init__.py": "",
        "app/shop.py": code(
            """
            from dataclasses import dataclass


            @dataclass
            class Item:
                name: str
                price: float


            def total(items: list[Item]) -> float:
                return sum(item.cost for item in items)


            def label(item: Item | None) -> str:
                return item.name.upper()


            def loose(value):
                return value + 1
            """
        ),
        "tests/test_shop.py": "def test_x():\n    assert True\n",
    }
    workspace = extract_project(make_zip(files), tmp_path / "ws")
    index = build_index(workspace)
    assert typecheck.checked_files(index) == ["app/__init__.py", "app/shop.py"]
    errors, problem = typecheck.run_mypy(workspace.root, typecheck.checked_files(index))
    assert problem is None
    findings = typecheck.mypy_findings(errors, index)
    sources = sorted(f.source for f in findings)
    assert sources == ["static:mypy:attr-defined", "static:mypy:union-attr"]
    attr = next(f for f in findings if f.source.endswith("attr-defined"))
    assert attr.symbol == "total" and attr.fixable and attr.category is Category.BUG
    assert attr.line_start == 11 and "does not have" in attr.explanation
    fixed = files["app/shop.py"].replace("item.cost", "item.price")
    after, _ = typecheck.run_mypy(
        workspace.root, typecheck.checked_files(index), {"app/shop.py": fixed}
    )
    assert [e["code"] for e in after] == ["union-attr"]
    assert typecheck.in_span(after, "app/shop.py", 14, 15) == after


def test_api_stub_and_related_api(tmp_path):
    from refactor_ai.project.index import api_stub, related_api

    models = code(
        """
        from dataclasses import dataclass

        RATE = 0.25


        @dataclass
        class Loan:
            loan_id: str
            days: int = 14

            def late(self, today: int) -> bool:
                return today > self.days


        def helper(x, *, scale=2):
            return x * scale
        """
    )
    stub = api_stub(models)
    assert "@dataclass\nclass Loan:\n    loan_id: str\n    days: int = 14" in stub
    assert "    def late(self, today: int) -> bool: ..." in stub
    assert "def helper(x, *, scale=2): ..." in stub and "RATE = 0.25" in stub
    assert "return" not in stub and api_stub("def (:") == ""
    files = {
        "lib/__init__.py": "",
        "lib/models.py": models,
        "lib/desk.py": "from lib.models import Loan\n\n\ndef lend():\n    return Loan('a')\n",
    }
    workspace = extract_project(make_zip(files), tmp_path / "ws")
    index = build_index(workspace)
    related = related_api(index, workspace, "lib.desk")
    assert related.startswith("# lib\n") or "# lib.models\n" in related
    assert "class Loan:" in related and related_api(index, workspace, "missing") == ""


def test_project_files_cannot_run_code_through_the_static_tools(tmp_path):
    marker = tmp_path / "pwned"
    payload = f"open({str(marker)!r}, 'a').write('x')\n"
    files = {
        "mypy.py": payload,
        "ruff.py": payload,
        "evil_plugin.py": payload + "def plugin(version):\n    return None\n",
        "mypy.ini": "[mypy]\nplugins = evil_plugin\n",
        "pyproject.toml": "[tool.mypy]\nplugins = ['evil_plugin']\n",
        "-config-file=mypy.ini.py": "x = 1\n",
        "app/__init__.py": "",
        "app/shop.py": "def total(items: list[int]) -> int:\n    return sum(items) + 'a'\n",
    }
    workspace = extract_project(make_zip(files), tmp_path / "ws")
    index = build_index(workspace)
    findings, warnings = static.scan(workspace, index)
    assert not marker.exists()
    assert not [w for w in warnings if "could not run" in w or "failed" in w]
    assert any(f.source == "static:mypy:operator" for f in findings)
