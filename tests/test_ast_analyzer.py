"""Unit tests for AST Analysis Engine (FR02, NFR01)."""

import pytest

from core.ast_analyzer import ASTAnalyzer, analyze
from core.exceptions import InvalidSyntaxError


def test_clean_short_function():
    code = "def add(a, b):\n    return a + b\n"
    result = analyze(code)
    assert result.syntax_valid is True
    assert result.findings == []
    assert result.metrics["functions_count"] == 1
    assert result.metrics["async_functions_count"] == 0
    assert result.metrics["total_cyclomatic_complexity"] == 1


def test_long_sync_function():
    lines = ["def process_items():"] + ["    x = 1" for _ in range(35)]
    code = "\n".join(lines)
    result = analyze(code)
    assert result.syntax_valid is True
    # The fixture also contains an unused local (`x`), which the dead-code
    # detector now reports; assert the long-function finding specifically.
    long_findings = [f for f in result.findings if f.rule == "long-function"]
    assert len(long_findings) == 1
    assert long_findings[0].node_type == "FunctionDef"
    assert long_findings[0].line == 1
    assert "36 lines" in long_findings[0].message
    assert any(f.rule == "dead-code-or-unused" for f in result.findings)


def test_long_async_function():
    lines = ["async def fetch_batch():"] + ["    await task()" for _ in range(32)]
    code = "\n".join(lines)
    result = analyze(code)
    assert result.syntax_valid is True
    assert len(result.findings) == 1
    assert result.findings[0].rule == "long-function"
    assert result.findings[0].node_type == "AsyncFunctionDef"
    assert result.metrics["async_functions_count"] == 1


def test_deep_nesting_detection():
    # 4 levels of control blocks: if -> for -> while -> if
    code = """
def nested_logic(data):
    if data:
        for item in data:
            while item.has_next():
                if item.is_valid():
                    item.process()
"""
    result = analyze(code)
    assert result.syntax_valid is True
    nesting_findings = [f for f in result.findings if f.rule == "deep-nesting"]
    assert len(nesting_findings) == 1
    assert nesting_findings[0].line == 6
    assert nesting_findings[0].node_type == "If"


def test_nesting_resets_in_inner_function():
    # An inner function should reset the nesting context
    code = """
def outer():
    if True:
        if True:
            def inner():
                if True:
                    if True:
                        return 1
            return inner()
"""
    result = analyze(code)
    assert result.syntax_valid is True
    # In neither outer nor inner does control block depth exceed 3
    assert not any(f.rule == "deep-nesting" for f in result.findings)


def test_cyclomatic_complexity_calculation():
    code = """
def complex_fn(a, b, c, d):
    if a:
        pass
    if b:
        pass
    while c:
        pass
    for i in range(10):
        pass
    try:
        pass
    except ValueError:
        pass
    except KeyError:
        pass
    res = [x for x in range(10) if x > 2 if x < 8]
    val = 1 if d else 2
    if a and b and c:
        pass
    return res
"""
    analyzer = ASTAnalyzer(complexity_threshold=5)
    result = analyzer.analyze(code)
    assert result.syntax_valid is True
    comp_findings = [f for f in result.findings if f.rule == "high-complexity"]
    assert len(comp_findings) == 1
    assert comp_findings[0].node_type == "FunctionDef"
    assert "cyclomatic complexity" in comp_findings[0].message


def test_invalid_syntax_error():
    analyzer = ASTAnalyzer()
    with pytest.raises(InvalidSyntaxError) as exc_info:
        analyzer.parse_safely("def broken_func(:\n    return 42")
    assert "SyntaxError" in str(exc_info.value)

    # analyze() returns graceful failure
    res = analyzer.analyze("def broken_func(:\n    return 42")
    assert res.syntax_valid is False
    assert res.findings == []
    assert res.error is not None
