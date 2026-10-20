"""Real-model LocalProvider tests, skipped unless REFACTOR_AI_GPU_TESTS=1.

They need the training environment (.venv-train), the pinned model under models/ and a
base-model config (REFACTOR_AI_MODEL_CONFIG, default configs/model.local.json, without
an adapter). Set REFACTOR_AI_GPU_ADAPTER_DIR to a trained adapter directory to run the
adapter test as well. Only one model worker runs at a time; the adapter test closes the
shared provider first and must stay the last test in this file.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from refactor_ai.contracts import (
    ChatMessage,
    GenerationConfig,
    GenerationRequest,
    ProviderErrorCode,
    ProviderMode,
    Role,
)
from refactor_ai.providers.local import LocalModelSettings, LocalProvider
from refactor_ai.task_format import build_refactor_messages

pytestmark = pytest.mark.skipif(
    os.environ.get("REFACTOR_AI_GPU_TESTS") != "1",
    reason="set REFACTOR_AI_GPU_TESTS=1 to run the real-model tests on the GPU",
)

ROOT = Path(__file__).resolve().parents[1]
CODES = [
    "def withdraw(balance, amount):\n    if amount > 0:\n        if amount <= balance:\n"
    "            return balance - amount\n        else:\n"
    '            raise ValueError("insufficient funds")\n    else:\n'
    '        raise ValueError("amount must be positive")\n',
    "def label(score):\n    if score is not None:\n        if score >= 50:\n"
    '            return "pass"\n        else:\n            return "fail"\n    else:\n'
    '        return "missing"\n',
    "def ratio(a, b):\n    if b != 0:\n        if a >= 0:\n            return a / b\n"
    "        else:\n            return -a / b\n    else:\n        return 0.0\n",
]


def pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def request(code: str, *, use_adapter: bool = False, **config) -> GenerationRequest:
    config.setdefault("max_new_tokens", 256)
    config.setdefault("timeout_s", 120)
    return GenerationRequest(
        role=Role.REFACTOR,
        messages=[ChatMessage(**m) for m in build_refactor_messages(code)],
        config=GenerationConfig(**config),
        use_adapter=use_adapter,
    )


@pytest.fixture(scope="module")
def provider():
    path = Path(os.environ.get("REFACTOR_AI_MODEL_CONFIG", ROOT / "configs" / "model.local.json"))
    shared = LocalProvider.from_config(path)
    if shared.settings.adapter_dir is not None:
        pytest.fail("these tests expect a base-model config without an adapter")
    info = shared.warm_up()
    assert info.ready, info.detail
    yield shared
    shared.close()


def test_loads_the_pinned_model_on_the_gpu(provider):
    info = provider.info()
    assert info.ready and info.provider_mode is ProviderMode.LOCAL_MODEL
    assert info.model_id == provider.settings.model_id
    assert info.model_revision == provider.settings.model_revision
    assert info.device.startswith("cuda:0")
    assert "revision verified: True" in info.detail


def test_greedy_call_reports_identity_and_is_repeatable(provider):
    first = provider.generate(request(CODES[0]))
    second = provider.generate(request(CODES[0]))
    assert first.error is None and second.error is None
    assert first.text == second.text
    assert first.model.model_id == provider.settings.model_id
    assert first.model.model_revision == provider.settings.model_revision
    assert first.model.use_adapter is False and first.model.adapter_sha256 is None
    assert first.prompt_tokens > 100 and first.completion_tokens > 0
    assert first.finish_reason in ("stop", "length")


def test_max_new_tokens_is_enforced(provider):
    result = provider.generate(request(CODES[1], max_new_tokens=5))
    assert result.error is None
    assert result.finish_reason == "length" and result.completion_tokens == 5


def test_input_too_long_is_typed_and_keeps_the_worker(provider):
    pid = provider.worker_pid
    result = provider.generate(request(CODES[1], max_input_tokens=16))
    assert result.error.code is ProviderErrorCode.INPUT_TOO_LONG
    assert provider.worker_pid == pid


def test_seeded_sampling_is_reproducible(provider):
    first = provider.generate(request(CODES[2], temperature=0.8, top_p=0.95, seed=7))
    second = provider.generate(request(CODES[2], temperature=0.8, top_p=0.95, seed=7))
    assert first.error is None and first.text == second.text


def test_adapter_request_without_adapter_is_unavailable(provider):
    result = provider.generate(request(CODES[0], use_adapter=True))
    assert result.error.code is ProviderErrorCode.UNAVAILABLE


def test_timeout_kills_the_gpu_worker_and_the_next_call_restarts(provider):
    old_pid = provider.worker_pid
    starts = provider.worker_starts
    result = provider.generate(request(CODES[0], max_new_tokens=2048, timeout_s=0.5))
    assert result.error.code is ProviderErrorCode.TIMEOUT
    assert old_pid is not None and not pid_alive(old_pid)
    assert provider.worker_pid is None
    after = provider.generate(request(CODES[1], max_new_tokens=16))
    assert after.error is None
    assert provider.worker_starts == starts + 1 and provider.worker_pid != old_pid


def test_adapter_switch_and_disabled_adapter_equals_base(provider):
    """Last test: closes the shared provider so only one model is on the GPU."""
    adapter = os.environ.get("REFACTOR_AI_GPU_ADAPTER_DIR")
    if not adapter:
        pytest.skip("set REFACTOR_AI_GPU_ADAPTER_DIR to a trained adapter directory")
    adapter_dir = Path(adapter).resolve()
    base_texts = [provider.generate(request(code)).text for code in CODES]
    provider.close()
    settings = LocalModelSettings(
        **{
            **provider.settings.model_dump(),
            "adapter_dir": adapter_dir,
            "adapter_id": adapter_dir.parent.name,
        }
    )
    digest = hashlib.sha256((adapter_dir / "adapter_model.safetensors").read_bytes()).hexdigest()
    with LocalProvider(settings) as adapted:
        on = [adapted.generate(request(code, use_adapter=True)) for code in CODES]
        off = [adapted.generate(request(code, use_adapter=False)) for code in CODES]
    for result, active in [(r, True) for r in on] + [(r, False) for r in off]:
        assert result.error is None
        assert result.model.adapter_sha256 == digest
        assert result.model.adapter_id == adapter_dir.parent.name
        assert result.model.use_adapter is active
    assert [r.text for r in off] == base_texts  # use_adapter=false is exactly the base model
    # A trained adapter changes greedy outputs on at least one of these prompts.
    assert any(a.text != b.text for a, b in zip(on, off, strict=True))
