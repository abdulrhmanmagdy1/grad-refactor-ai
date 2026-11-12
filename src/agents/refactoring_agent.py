"""Refactoring Agent: provider-backed transformation under agentic constraints (FR03, Phase 3).

The agent owns the refactoring *contract*: a role system prompt, the analysis
plan, the specific findings, and — on retries — the Review Agent's
``ReviewCritique``. The provider itself stays fully decoupled (ADR08) and may
be the deterministic mock, the smart AST engine, a local Ollama model, or a
LoRA-adapted local model.
"""

from typing import Any

from core.schemas import ASTFinding
from models.base import BaseModelProvider
from models.prompting import REFACTORING_SYSTEM_PROMPT

# Backwards-compatible alias: the canonical text lives in models.prompting so
# training and inference cannot drift from the agent role prompt.
SYSTEM_PROMPT = REFACTORING_SYSTEM_PROMPT


class RefactoringAgent:
    """Agent responsible for proposing code refactorings via a decoupled provider."""

    def __init__(self, provider: BaseModelProvider) -> None:
        self.provider = provider

    async def refactor(
        self,
        code: str,
        findings: list[ASTFinding],
        retry_feedback: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Generate a refactored candidate.

        ``options`` carries the Analysis Agent plan (``analysis_plan``) and,
        on retries, the Review Agent critique (``review_critique``); both are
        forwarded to the provider prompt builder.
        """
        opts = dict(options or {})
        if retry_feedback:
            opts["retry_feedback"] = retry_feedback
            opts.setdefault("review_critique", retry_feedback)
        opts.setdefault("system_prompt", SYSTEM_PROMPT)

        return await self.provider.generate_refactoring(code, findings, opts)

    async def explain(
        self,
        original_code: str,
        refactored_code: str,
        diff: str,
    ) -> str:
        """Provide a rationale grounded in measured before/after metrics."""
        return await self.provider.explain_changes(original_code, refactored_code, diff)
