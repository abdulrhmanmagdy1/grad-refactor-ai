"""Analysis Agent: static inspection plus structured refactoring plans (FR02, Phase 3).

The agent performs two jobs without ever executing submitted code (NFR01):

1. ``analyze``       — run the deterministic AST detector suite.
2. ``build_plan``    — translate raw findings into an explicit ``AnalysisPlan``
   (primary smell, strategy, target symbols, risk, ordered steps) that the
   Refactoring Agent and the UI consume.
"""

import ast

from core.ast_analyzer import ASTAnalyzer
from core.schemas import AnalysisPlan, AnalysisResult, ASTFinding

# Deterministic mapping from detector rule to the selected strategy name.
STRATEGY_BY_RULE: dict[str, str] = {
    "long-function": "decompose-extract-helper",
    "deep-nesting": "flatten-guard-clauses",
    "high-complexity": "simplify-conditionals",
    "high-cognitive-complexity": "simplify-conditionals",
    "long-parameter-list": "introduce-parameter-object",
    "mutable-default-arg": "normalise-mutable-defaults",
    "broad-exception-catch": "narrow-exception-handling",
    "dead-code-or-unused": "remove-dead-code",
    "duplicate-code-blocks": "extract-shared-helper",
}

_GOAL_BY_RULE: dict[str, str] = {
    "long-function": "decompose over-long functions into cohesive helpers",
    "deep-nesting": "flatten deep control flow with guard clauses",
    "high-complexity": "reduce cyclomatic complexity of decision logic",
    "high-cognitive-complexity": "lower cognitive load of nested logic",
    "long-parameter-list": "group long parameter lists into a cohesive object",
    "mutable-default-arg": "replace mutable default arguments with None guards",
    "broad-exception-catch": "narrow broad exception handling",
    "dead-code-or-unused": "remove unreachable or unused code",
    "duplicate-code-blocks": "deduplicate structurally repeated blocks",
}

_STEP_BY_RULE: dict[str, str] = {
    "long-function": (
        "Extract independent statement runs from over-long functions into "
        "named helpers that receive exactly the locals they read."
    ),
    "deep-nesting": (
        "Collapse nested conditionals without else-branches into single "
        "short-circuited boolean conditions."
    ),
    "high-complexity": (
        "Simplify boolean decision logic so each branch has a single exit "
        "intent and complexity falls below the threshold."
    ),
    "high-cognitive-complexity": (
        "Reduce nesting depth and boolean chains so the function reads "
        "top-to-bottom without deep mental stacks."
    ),
    "long-parameter-list": (
        "Group related parameters into one cohesive structure while keeping "
        "the original call sites compatible."
    ),
    "mutable-default-arg": (
        "Replace the mutable default with None and restore a fresh container "
        "inside the function body."
    ),
    "broad-exception-catch": (
        "Catch the narrowest exception types and re-raise or log unexpected "
        "failures so errors stay visible."
    ),
    "dead-code-or-unused": (
        "Delete unreachable statements and unused local assignments without "
        "touching live code paths."
    ),
    "duplicate-code-blocks": (
        "Factor mirrored statement blocks into one shared helper invoked from every former copy."
    ),
}

_RISK_BY_RULE: dict[str, str] = {
    "long-function": "low",
    "deep-nesting": "low",
    "high-complexity": "low",
    "high-cognitive-complexity": "low",
    "duplicate-code-blocks": "low",
    "mutable-default-arg": "medium",
    "dead-code-or-unused": "medium",
    "broad-exception-catch": "medium",
    "long-parameter-list": "high",
}

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}

_MAX_TARGET_SYMBOLS = 8


class AnalysisAgent:
    """Agent responsible for static AST inspection and refactoring planning."""

    def __init__(self, analyzer: ASTAnalyzer | None = None) -> None:
        self.analyzer = analyzer or ASTAnalyzer()

    async def analyze(self, code: str) -> AnalysisResult:
        """Analyze Python code and return structured findings and structural metrics."""
        return self.analyzer.analyze(code)

    # ------------------------------------------------------------------ #
    # Goal + plan construction (Phase 3 reasoning)
    # ------------------------------------------------------------------ #
    def formulate_goal(self, findings: list[ASTFinding]) -> str:
        """Formulate a concise refactoring goal based on detected findings."""
        if not findings:
            return (
                "No critical code smells detected. Apply readability and formatting improvements."
            )

        rules = {finding.rule for finding in findings}
        goals = [_GOAL_BY_RULE[rule] for rule in _GOAL_BY_RULE if rule in rules]
        if not goals:
            goals.append("Address reported structural issues while preserving behaviour")
        return "Refactoring goal: " + "; ".join(goals) + "."

    def build_plan(self, code: str, analysis: AnalysisResult) -> AnalysisPlan:
        """Translate detector findings into an explicit, ordered refactoring plan."""
        findings = analysis.findings
        if not findings:
            return AnalysisPlan(
                primary_smell=None,
                refactoring_strategy="readability-cleanup",
                target_symbols=[],
                risk_level="low",
                step_by_step_plan=[
                    "Apply a conservative readability pass (documentation and "
                    "structure) without changing observable behaviour.",
                    "Re-check syntax validity and preserved top-level symbols.",
                    "Run sampled golden-equivalence tests against the original code.",
                ],
            )

        counts: dict[str, int] = {}
        first_seen: dict[str, int] = {}
        for index, finding in enumerate(findings):
            counts[finding.rule] = counts.get(finding.rule, 0) + 1
            first_seen.setdefault(finding.rule, index)

        ranked = sorted(counts, key=lambda rule: (-counts[rule], first_seen[rule]))
        primary = ranked[0]

        steps = [_STEP_BY_RULE.get(primary, "Address the primary smell without behaviour change.")]
        for rule in ranked[1:]:
            steps.append(
                _STEP_BY_RULE.get(rule, f"Address secondary finding '{rule}' conservatively.")
            )
        steps.append(
            "Verify caller compatibility, syntax validity, and sampled behavioural "
            "equivalence before accepting the candidate."
        )

        risk = "low"
        for finding in findings:
            rule_risk = _RISK_ORDER[_RISK_BY_RULE.get(finding.rule, "medium")]
            risk = risk if _RISK_ORDER[risk] >= rule_risk else _RISK_BY_RULE[finding.rule]

        return AnalysisPlan(
            primary_smell=primary,
            refactoring_strategy=STRATEGY_BY_RULE.get(primary, "conservative-refactor"),
            target_symbols=self._target_symbols(code, findings),
            risk_level=risk,
            step_by_step_plan=steps,
        )

    @staticmethod
    def _target_symbols(code: str, findings: list[ASTFinding]) -> list[str]:
        """Locate the functions/classes that contain the reported findings."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []
        finding_lines = [finding.line for finding in findings if finding.line]
        symbols: list[str] = []

        def visit(node: ast.AST, prefix: str) -> None:
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    start = child.lineno
                    end = getattr(child, "end_lineno", start)
                    if any(start <= line <= end for line in finding_lines):
                        symbols.append(prefix + child.name)
                    visit(child, prefix + child.name + ".")

        visit(tree, "")
        return symbols[:_MAX_TARGET_SYMBOLS]
