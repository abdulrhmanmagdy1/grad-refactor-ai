from fastapi.testclient import TestClient

from refactor_ai.api import app

client = TestClient(app)


def test_health_identifies_foundation():
    assert client.get("/health").json()["mode"] == "scaffold"


def test_analysis_does_not_execute_code(tmp_path):
    target = tmp_path / "must-not-exist"
    code = f"from pathlib import Path\nPath({str(target)!r}).write_text('executed')"
    result = client.post("/api/v1/analyze", json={"code": code})
    assert result.status_code == 200
    assert result.json()["syntax_valid"] is True
    assert not target.exists()


def test_invalid_syntax_and_empty_input():
    result = client.post("/api/v1/analyze", json={"code": "def broken("})
    assert result.json()["syntax_valid"] is False
    assert result.json()["error"]
    for value in ("", "  ", "x" * 20001):
        assert client.post("/api/v1/analyze", json={"code": value}).status_code == 422


def test_long_async_function():
    code = "async def work():\n" + "    x = 1\n" * 31
    result = client.post("/api/v1/analyze", json={"code": code}).json()
    assert result["findings"][0]["rule"] == "long-function"


def test_nesting_is_structural_not_indentation():
    nested = (
        "def f(x):\n    if x:\n        for i in x:\n"
        "            while i:\n                if i > 1:\n                    break"
    )
    result = client.post("/api/v1/analyze", json={"code": nested}).json()
    assert any(f["rule"] == "deep-nesting" for f in result["findings"])
    aligned = "x = (\n                    1\n)"
    assert client.post("/api/v1/analyze", json={"code": aligned}).json()["findings"] == []
