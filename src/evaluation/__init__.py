"""Evaluation harness and benchmark comparisons."""

__all__ = ["BenchmarkCase", "EvaluationHarness"]


def __getattr__(name: str):
    """Lazy re-exports so `python -m evaluation.harness` runs without re-import warnings."""
    if name in __all__:
        from evaluation import harness

        return getattr(harness, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
