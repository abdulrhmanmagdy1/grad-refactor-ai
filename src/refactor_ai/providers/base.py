"""Model-provider interface shared by the base model, the adapted model and the fake."""

from __future__ import annotations

from typing import Protocol

from refactor_ai.contracts import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    ProviderErrorCode,
    ProviderInfo,
    ProviderMode,
)


class Provider(Protocol):
    """Bounded text generation for one role call.

    Implementations return expected failures (timeout, load error, input too long) as
    GenerationResult.error instead of raising, report their exact model identity, and
    never fall back silently from an adapter to the base model. Callers serialize access.
    """

    @property
    def mode(self) -> ProviderMode: ...

    def info(self) -> ProviderInfo: ...

    def generate(self, request: GenerationRequest) -> GenerationResult: ...

    def close(self) -> None: ...


def failed_result(
    mode: ProviderMode, code: ProviderErrorCode, message: str, elapsed_s: float = 0.0
) -> GenerationResult:
    return GenerationResult(
        provider_mode=mode,
        elapsed_s=elapsed_s,
        finish_reason="error",
        error=ProviderError(code=code, message=message),
    )
