"""Unit and isolation tests for Isolated Test Runner (FR04, NFR01, NFR02)."""

import os

from runner.sandbox import IsolatedRunner


def test_sandbox_passing_test():
    runner = IsolatedRunner(timeout_seconds=5.0)
    candidate = "def multiply(a, b):\n    return a * b\n"
    test_code = (
        "from solution import multiply\ndef test_multiply():\n    assert multiply(3, 4) == 12\n"
    )
    res = runner.run_test(candidate, test_code)
    assert res.success is True
    assert res.exit_code == 0
    assert res.timed_out is False
    assert res.duration_ms > 0


def test_sandbox_failing_test():
    runner = IsolatedRunner(timeout_seconds=5.0)
    candidate = "def multiply(a, b):\n    return a + b\n"
    test_code = (
        "from solution import multiply\ndef test_multiply():\n    assert multiply(3, 4) == 12\n"
    )
    res = runner.run_test(candidate, test_code)
    assert res.success is False
    assert res.exit_code != 0
    assert "assert 7 == 12" in (res.stdout + res.stderr)


def test_sandbox_timeout_enforcement():
    # Enforce strict 1.0 second timeout for runaway code
    runner = IsolatedRunner(timeout_seconds=1.0)
    candidate = "def infinite_loop():\n    while True:\n        pass\n"
    test_code = "from solution import infinite_loop\ndef test_infinite():\n    infinite_loop()\n"
    res = runner.run_test(candidate, test_code)
    assert res.success is False
    assert res.timed_out is True
    assert "timed out" in (res.error_message or "").lower()


def test_sandbox_isolated_environment():
    # Verify that secret environment variables from host are not leaked to sandbox
    os.environ["SECRET_HOST_TOKEN"] = "super-secret-key-12345"
    # This asserts isolation, not timeout enforcement (covered separately). A
    # 3s budget is too tight for Windows pytest startup alone, which can take
    # ~3s before the candidate is even imported.
    runner = IsolatedRunner(timeout_seconds=5.0)
    candidate = (
        "def get_secret():\n    import os\n    return os.environ.get('SECRET_HOST_TOKEN', 'none')\n"
    )
    test_code = (
        "from solution import get_secret\ndef test_no_leak():\n    assert get_secret() == 'none'\n"
    )
    res = runner.run_test(candidate, test_code)
    assert res.success is True
    assert res.exit_code == 0
