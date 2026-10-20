import json

from refactor_ai.contracts import (
    ChatMessage,
    GenerationConfig,
    GenerationRequest,
    ProviderError,
    ProviderErrorCode,
    ProviderMode,
    Role,
)
from refactor_ai.providers import FakeProvider
from refactor_ai.task_format import build_refactor_user_prompt, parse_refactor_output
from refactor_ai.tasks import guard_clauses

CODE = (
    "def f(x):\n    if x is not None:\n        if x > 0:\n            return 1\n"
    "        else:\n            return 2\n    else:\n        return 0\n"
)


def request(role, content, **config):
    return GenerationRequest(
        role=role,
        messages=[ChatMessage(role="user", content=content)],
        config=GenerationConfig(**config),
    )


def test_fake_is_labelled_everywhere():
    provider = FakeProvider()
    assert provider.mode is ProviderMode.FAKE
    assert provider.info().provider_mode is ProviderMode.FAKE
    result = provider.generate(request(Role.REFACTOR, build_refactor_user_prompt(CODE)))
    assert result.provider_mode is ProviderMode.FAKE
    assert result.model.model_id == "fake-provider"
    parsed = parse_refactor_output(result.text)
    assert parsed.explanation.startswith("FAKE PROVIDER")
    assert guard_clauses.rubric(CODE, parsed.code).passed


def test_fake_analysis_and_review_defaults_are_json():
    provider = FakeProvider()
    analysis = json.loads(
        provider.generate(request(Role.ANALYSIS, f"Code:\n```python\n{CODE}```")).text
    )
    assert analysis["supported_task"] is True and analysis["findings"]
    review = json.loads(provider.generate(request(Role.REVIEW, "anything")).text)
    assert review["verdict"] == "accept" and review["reasons"][0].startswith("FAKE")


def test_scripted_responses_and_errors():
    error = ProviderError(code=ProviderErrorCode.GENERATION_ERROR, message="boom")
    provider = FakeProvider(script={Role.REFACTOR: ["first", error, lambda r: "called"]})
    assert provider.generate(request(Role.REFACTOR, "x")).text == "first"
    failed = provider.generate(request(Role.REFACTOR, "x"))
    assert failed.error.code is ProviderErrorCode.GENERATION_ERROR
    assert failed.finish_reason == "error"
    assert provider.generate(request(Role.REFACTOR, "x")).text == "called"
    assert len(provider.calls) == 3


def test_fake_timeout_is_typed():
    provider = FakeProvider(delay_s=0.2)
    result = provider.generate(request(Role.REVIEW, "x", timeout_s=0.05))
    assert result.error.code is ProviderErrorCode.TIMEOUT
