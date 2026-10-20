"""Model providers. FakeProvider is test-only; the local provider runs a pinned model."""

from refactor_ai.providers.base import Provider, failed_result
from refactor_ai.providers.fake import FakeProvider

__all__ = ["FakeProvider", "Provider", "failed_result"]
