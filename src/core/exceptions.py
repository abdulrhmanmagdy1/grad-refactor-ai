"""Domain exceptions for Multi-Agent Refactoring."""


class RefactorAIError(Exception):
    """Base exception for all refactor_ai errors."""


class InvalidSyntaxError(RefactorAIError):
    """Raised when submitted Python code has syntax errors."""

    def __init__(self, message: str, line: int | None = None, offset: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.offset = offset


class CodeLengthExceededError(RefactorAIError):
    """Raised when submitted code exceeds character boundary limits (NFR01, FR01)."""


class ExecutionTimeoutError(RefactorAIError):
    """Raised when an operation exceeds declared execution time boundary (FR08)."""


class ModelInferenceError(RefactorAIError):
    """Raised when model provider fails to generate a response."""


class VerificationFailedError(RefactorAIError):
    """Raised when candidate code fails AST or verification checks."""


class SandboxExecutionError(RefactorAIError):
    """Raised when sandbox runner encounters execution failures or violations."""


class ProviderUnavailableError(RefactorAIError):
    """Raised when a requested model provider cannot serve inference right now (UC03)."""


class TransformationError(RefactorAIError):
    """Raised when a deterministic AST transformation cannot be applied safely."""
