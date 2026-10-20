"""Deterministic test-only provider. Its output is never model inference.

Default behavior per role: analysis reports the static task findings, refactor applies
the deterministic AST transformation, and review returns a placeholder accept. Every
explanation and reason is prefixed with FAKE so it cannot be mistaken for a model.
Tests can script exact responses or errors per role instead.
"""

from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterable

from refactor_ai.contracts import (
    GenerationRequest,
    GenerationResult,
    ModelReference,
    ProviderError,
    ProviderErrorCode,
    ProviderInfo,
    ProviderMode,
    Role,
)
from refactor_ai.providers.base import failed_result
from refactor_ai.task_format import extract_submitted_code, render_refactor_completion
from refactor_ai.tasks import guard_clauses

FAKE_MODEL = ModelReference(model_id="fake-provider", model_revision="fake-v1")
FAKE_PREFIX = "FAKE PROVIDER (not a model):"

ScriptItem = str | ProviderError | Callable[[GenerationRequest], str]


class FakeProvider:
    def __init__(
        self,
        script: dict[Role, Iterable[ScriptItem]] | None = None,
        delay_s: float = 0.0,
    ) -> None:
        self._script: dict[Role, deque[ScriptItem]] = defaultdict(deque)
        for role, items in (script or {}).items():
            self._script[Role(role)].extend(items)
        self._delay_s = delay_s
        self._lock = threading.Lock()
        self.calls: list[GenerationRequest] = []

    @property
    def mode(self) -> ProviderMode:
        return ProviderMode.FAKE

    def info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_mode=ProviderMode.FAKE,
            model_id=FAKE_MODEL.model_id,
            model_revision=FAKE_MODEL.model_revision,
            device="none",
            ready=True,
            detail="Deterministic test provider. Outputs are not language-model inference.",
        )

    def close(self) -> None:
        return None

    def generate(self, request: GenerationRequest) -> GenerationResult:
        started = time.perf_counter()
        with self._lock:
            self.calls.append(request)
            item = self._script[request.role].popleft() if self._script[request.role] else None
        if self._delay_s:
            if self._delay_s > request.config.timeout_s:
                time.sleep(request.config.timeout_s)
                return failed_result(
                    self.mode,
                    ProviderErrorCode.TIMEOUT,
                    f"Generation exceeded {request.config.timeout_s:.1f} s",
                    time.perf_counter() - started,
                )
            time.sleep(self._delay_s)
        if isinstance(item, ProviderError):
            return failed_result(self.mode, item.code, item.message, time.perf_counter() - started)
        if callable(item):
            text = item(request)
        elif isinstance(item, str):
            text = item
        else:
            text = self._default(request)
        return GenerationResult(
            text=text,
            provider_mode=self.mode,
            model=FAKE_MODEL.model_copy(update={"use_adapter": request.use_adapter}),
            elapsed_s=time.perf_counter() - started,
            prompt_tokens=sum(len(m.content.split()) for m in request.messages),
            completion_tokens=len(text.split()),
            finish_reason="stop",
        )

    def _default(self, request: GenerationRequest) -> str:
        prompt = request.messages[-1].content
        code = extract_submitted_code(prompt) or ""
        if request.role is Role.ANALYSIS:
            check = guard_clauses.check_input(code)
            return json.dumps(
                {
                    "supported_task": check.supported,
                    "findings": [
                        {
                            "type": guard_clauses.FINDING_TYPE,
                            "start_line": item.start_line,
                            "end_line": item.end_line,
                            "reason": f"{FAKE_PREFIX} {item.reason}",
                        }
                        for item in check.opportunities
                    ],
                    "unsupported_reason": None if check.supported else check.describe(),
                }
            )
        if request.role is Role.REFACTOR:
            transformed = guard_clauses.to_guard_clauses(code) or code
            return render_refactor_completion(
                f"{FAKE_PREFIX} deterministic AST transformation used for testing.",
                transformed,
            )
        return json.dumps(
            {
                "verdict": "accept",
                "reasons": [f"{FAKE_PREFIX} placeholder review; no model judged this code."],
                "suggested_correction": None,
            }
        )
