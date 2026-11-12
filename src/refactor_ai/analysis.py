"""Static heuristics only. Never execute submitted code (NFR01)."""

from core.ast_analyzer import analyze as core_analyze
from core.schemas import AnalysisResult
from core.schemas import ASTFinding as Finding

__all__ = ["Finding", "AnalysisResult", "analyze"]


def analyze(code: str) -> AnalysisResult:
    """Analyze code statically using AST heuristics."""
    return core_analyze(code)
