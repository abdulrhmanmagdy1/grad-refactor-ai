import itertools

import pytest

from refactor_ai.tasks import guard_clauses as gc

SHIPPING = '''def shipping_cost(weight, express):
    """Return the shipping cost."""
    if weight > 0:
        if express:
            return weight * 3
        else:
            return weight * 2
    else:
        raise ValueError("weight must be positive")
'''

GRADE = """def grade(score):
    if score >= 0:
        if score <= 100:
            if score >= 90:
                result = 'A'
            elif score >= 70:
                result = 'B'
            else:
                result = 'C'
            return result
        else:
            return None
    else:
        return None
"""

ELIF_CHAIN = """def classify(x, y):
    if x is None:
        return 'missing'
    elif y:
        if x > 10:
            return 'big'
        else:
            return 'small'
    else:
        return 'other'
"""

FLAT = """def sign(x):
    if x > 0:
        return 1
    elif x < 0:
        return -1
    return 0
"""


def call(code, *args):
    namespace = {}
    exec(compile(code, "<trusted-test-fixture>", "exec"), namespace)  # trusted literals only
    func = next(v for k, v in namespace.items() if not k.startswith("__"))
    try:
        return ("return", func(*args))
    except Exception as exc:  # noqa: BLE001 - behavior comparison includes exception type
        return ("raise", type(exc).__name__)


@pytest.mark.parametrize(
    ("code", "inputs"),
    [
        (SHIPPING, itertools.product([-2, 0, 1, 5.5], [True, False])),
        (GRADE, [(s,) for s in (-5, 0, 50, 69, 70, 89, 90, 100, 101)]),
        (ELIF_CHAIN, itertools.product([None, 0, 5, 11], [True, False, 0])),
    ],
)
def test_transformation_preserves_behavior_and_reduces_nesting(code, inputs):
    target = gc.to_guard_clauses(code)
    assert target is not None
    for args in inputs:
        assert call(code, *args) == call(target, *args), args
    assert gc.code_nesting_depth(target) < gc.code_nesting_depth(code)
    assert gc.rubric(code, target).passed, gc.rubric(code, target).reasons
    assert gc.check_input(code).supported


def test_shipping_guard_is_inverted_and_docstring_kept():
    target = gc.to_guard_clauses(SHIPPING)
    assert target == (
        "def shipping_cost(weight, express):\n"
        '    """Return the shipping cost."""\n'
        "    if weight <= 0:\n"
        "        raise ValueError('weight must be positive')\n"
        "    if express:\n"
        "        return weight * 3\n"
        "    return weight * 2\n"
    )


def test_depth_counts_elif_as_flat_and_else_if_as_nested():
    assert gc.code_nesting_depth(FLAT) == 1
    nested = (
        "def f(x):\n    if x:\n        return 1\n    else:\n"
        "        if x is None:\n            return 2\n        return 3\n"
    )
    assert gc.code_nesting_depth(nested) == 2


def test_flat_function_has_no_opportunity():
    check = gc.check_input(FLAT)
    assert not check.supported
    assert check.reasons == ["no_opportunity"]


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("def f(:\n    pass\n", "syntax_error"),
        ("x = 1\n", "not_single_function"),
        ("import os\ndef f():\n    return 1\n", "not_single_function"),
        ("async def f(x):\n    return x\n", "async_function"),
        ("@cache\ndef f(x):\n    return x\n", "decorated_function"),
        ("def f(x):\n    yield x\n", "generator_function"),
        ("def f(x):\n    def g():\n        return 1\n    return g\n", "nested_definition"),
        ("def f(x):\n    import os\n    return x\n", "imports_present"),
        ("def f(x):\n    global y\n    return x\n", "global_or_nonlocal"),
        (
            "def f(x):\n    try:\n        return 1\n    except Exception:\n        return 2\n",
            "try_or_with_present",
        ),
        ("def f(x):\n    print(x)\n    return x\n", "denied_call:print"),
        ("def f(x):\n    return x.__class__\n", "dunder_access"),
    ],
)
def test_out_of_scope_inputs_are_rejected_with_reason(code, reason):
    check = gc.check_input(code)
    assert not check.supported
    assert reason in check.reasons
    assert gc.reason_text(reason)


def test_too_long_input():
    code = "def f(x):\n" + "    x = x + 1\n" * 70 + "    return x\n"
    assert "too_long" in gc.check_input(code).reasons


def test_negation_is_exact_or_wrapped():
    import ast

    def neg(src):
        return ast.unparse(gc.negate(ast.parse(src, mode="eval").body))

    assert neg("x == y") == "x != y"
    assert neg("x in items") == "x not in items"
    assert neg("not ok") == "ok"
    assert neg("x > 0") == "x <= 0"
    assert neg("-1.5 <= x") == "-1.5 > x"
    assert neg("a < b") == "not a < b"  # unknown operand types: no ordering flip
    assert neg("a and b") == "not (a and b)"
    assert neg("0 < x < 10") == "not 0 < x < 10"


def test_rubric_reports_each_failure():
    result = gc.rubric(SHIPPING, SHIPPING)
    assert not result.passed
    assert result.checks["nesting_reduced"] is False
    renamed = gc.to_guard_clauses(SHIPPING).replace("def shipping_cost", "def cost")
    assert gc.rubric(SHIPPING, renamed).checks["same_name"] is False
    broken = gc.rubric(SHIPPING, "def broken(:\n")
    assert not broken.passed and broken.checks["parses_as_single_function"] is False
    added = gc.to_guard_clauses(SHIPPING).replace("return weight * 3", "return round(weight * 3)")
    assert gc.rubric(SHIPPING, added).checks["no_new_calls"] is False


def test_opportunities_have_valid_lines():
    check = gc.check_input(GRADE)
    assert check.opportunities
    total = len(GRADE.splitlines())
    for item in check.opportunities:
        assert 1 <= item.start_line <= item.end_line <= total


def test_same_code_ignores_formatting():
    assert gc.same_code("def f(x):\n    return (x)\n", "def f(x):  # comment\n    return x\n")
    assert not gc.same_code("def f(x):\n    return x\n", "def f(x):\n    return -x\n")


ELIF_ONLY = """def label(kind, size):
    note = 'small'
    if size > 10:
        note = 'large'
    elif kind == 'box':
        return 'box'
    else:
        if size < 0:
            return 'negative'
    return note
"""


def test_elif_collapse_alone_is_not_an_opportunity():
    # Only ast.unparse's "else: if" -> "elif" lowers the depth; no guard clause exists.
    check = gc.check_input(ELIF_ONLY)
    assert not check.supported
    assert check.reasons == ["no_opportunity"]
    assert not gc.rubric(ELIF_ONLY, gc.to_guard_clauses(ELIF_ONLY)).checks["has_guard_clause"]


def test_trailing_elif_is_not_counted_as_a_guard_clause():
    chain = "def f(a, b):\n    if a:\n        x = 1\n    elif b:\n        return 2\n    return 3\n"
    assert not gc._has_guard_clause(gc.parse_function(chain)[0].body)


def test_long_input_is_rejected_before_any_recursive_analysis():
    code = "def f(a):\n if a:0\n" + " elif a:0\n" * 1200 + " return 1\n"
    assert gc.check_input(code).reasons == ["too_long"]
