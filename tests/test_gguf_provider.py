"""GgufProvider, the GGUF worker (with a fake llama_cpp) and the one-model GPU pool."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_local_provider import REVISION, STUB_WORKER, request, stub_log

from refactor_ai.contracts import ProviderErrorCode
from refactor_ai.providers import gguf_worker, model_worker
from refactor_ai.providers.gguf import (
    GgufModelSettings,
    GgufProvider,
    ModelPool,
    PooledProvider,
    ReleasableLocalProvider,
)
from refactor_ai.providers.local import LocalModelSettings

GGUF_NAME = "model-q4.gguf"

# The local-provider stub, extended to report the checksum of the GGUF file it was given.
GGUF_STUB = (
    STUB_WORKER.replace(
        'revision = "f" * 40 if mode == "stub/wrong-identity" else LOAD["model_revision"]',
        "gguf_sha = None\n"
        'if "gguf_file" in LOAD and mode != "stub/no-gguf-sha":\n'
        '    with open(os.path.join(LOAD["model_dir"], LOAD["gguf_file"]), "rb") as fh:\n'
        "        gguf_sha = hashlib.sha256(fh.read()).hexdigest()\n"
        'revision = "f" * 40 if mode == "stub/wrong-identity" else LOAD["model_revision"]',
    )
    .replace(
        '"device": "stub-device", "dtype": LOAD["dtype"],',
        '"device": "stub-device", "dtype": LOAD["dtype"], "gguf_sha256": gguf_sha,',
    )
    .replace('log("start", mode=mode)', 'log("start", mode=mode, load=LOAD)')
)


@pytest.fixture
def stub(tmp_path):
    assert "gguf_sha256" in GGUF_STUB and "load=LOAD" in GGUF_STUB
    script = tmp_path / "gguf_stub.py"
    script.write_text(GGUF_STUB, encoding="utf-8")
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / GGUF_NAME).write_bytes(b"weights")
    return script, model_dir


WEIGHTS_SHA = hashlib.sha256(b"weights").hexdigest()


def make_gguf(stub, model_id="stub/ok", **overrides) -> GgufProvider:
    script, model_dir = stub
    values = {
        "python": sys.executable,
        "model_dir": model_dir,
        "model_id": model_id,
        "model_revision": REVISION,
        "gguf_file": GGUF_NAME,
        "device": "cpu",
        "load_timeout_s": 20,
    }
    values.update(overrides)
    return GgufProvider(GgufModelSettings(**values), worker_script=script)


def make_local(stub, model_id="stub/ok") -> ReleasableLocalProvider:
    script, model_dir = stub
    settings = LocalModelSettings(
        python=sys.executable,
        model_dir=model_dir,
        model_id=model_id,
        model_revision=REVISION,
        device="cpu",
        dtype="float32",
        load_timeout_s=20,
    )
    return ReleasableLocalProvider(settings, worker_script=script)


# --- provider -------------------------------------------------------------------------


def test_provider_sends_the_gguf_settings_and_checks_the_checksum(stub):
    with make_gguf(stub, gguf_sha256=WEIGHTS_SHA, context_tokens=4096) as provider:
        result = provider.generate(request("hello"))
        assert result.error is None and result.text == "echo[base]: hello"
        assert WEIGHTS_SHA in provider.info().detail
    load = next(entry["load"] for entry in stub_log(stub) if entry["event"] == "start")
    assert load["gguf_file"] == GGUF_NAME and load["gguf_sha256"] == WEIGHTS_SHA
    assert load["context_tokens"] == 4096 and load["gpu_layers"] == -1
    assert load["dtype"] == "float16" and load["adapter_dir"] is None


def test_checksum_mismatch_and_missing_checksum_are_load_errors(stub):
    with make_gguf(stub, gguf_sha256="0" * 64) as provider:
        failed = provider.generate(request("hello"))
        assert failed.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
        assert "does not match gguf_sha256" in failed.error.message
    with make_gguf(stub, model_id="stub/no-gguf-sha") as provider:
        failed = provider.generate(request("hello"))
        assert "did not report the GGUF checksum" in failed.error.message


def test_missing_gguf_file_fails_without_spawning(stub):
    with make_gguf(stub, gguf_file="absent.gguf") as provider:
        result = provider.generate(request("hello"))
        assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
        assert "gguf_file was not found" in result.error.message
    assert stub_log(stub) == []


def test_release_frees_the_worker_and_the_next_call_reloads(stub):
    with make_gguf(stub) as provider:
        assert provider.generate(request("one")).error is None
        first_pid = provider.worker_pid
        provider.release()
        assert provider.worker_pid is None and provider.info().ready is False
        assert provider.generate(request("two")).error is None
        assert provider.worker_starts == 2 and provider.worker_pid != first_pid


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"gguf_file": "dir/m.gguf"},
        {"gguf_file": "m.bin"},
        {"gguf_file": "m.gguf", "adapter_dir": "a", "adapter_id": "a"},
        {"gguf_file": "m.gguf", "context_tokens": 100},
        {"gguf_file": "m.gguf", "gguf_sha256": "nope"},
        {"gguf_file": "m.gguf", "backend": "llama_cpp"},
    ],
)
def test_invalid_gguf_settings_are_rejected(values):
    base = {
        "python": "python.exe",
        "model_dir": "model",
        "model_id": "org/model",
        "model_revision": REVISION,
    }
    with pytest.raises(ValidationError):
        GgufModelSettings(**{**base, **values})


def test_project_example_config_is_valid_and_pinned():
    root = Path(__file__).resolve().parents[1]
    settings = GgufModelSettings.from_file(root / "configs" / "model.project.example.json")
    assert settings.model_id == "Qwen/Qwen2.5-Coder-3B-Instruct-GGUF"
    assert len(settings.model_revision) == 40 and len(settings.gguf_sha256) == 64
    assert settings.gguf_file.endswith("q4_k_m.gguf") and settings.dtype == "float16"


# --- pool -----------------------------------------------------------------------------


def test_the_pool_keeps_one_model_loaded(stub):
    pool = ModelPool()
    small = PooledProvider(make_local(stub), pool)
    large = PooledProvider(make_gguf(stub), pool)
    try:
        assert small.generate(request("a")).error is None
        assert small.inner.worker_pid is not None and pool.active is small.inner
        assert large.generate(request("b")).error is None
        assert small.inner.worker_pid is None and large.inner.worker_pid is not None
        assert small.generate(request("c")).error is None
        assert large.inner.worker_pid is None and small.inner.worker_starts == 2
    finally:
        small.close()
        large.close()


def test_a_model_stopped_for_the_other_member_is_reported_as_paused(stub):
    pool = ModelPool()
    small = PooledProvider(make_local(stub), pool)
    large = PooledProvider(make_gguf(stub), pool)
    try:
        assert small.info().detail is None or not small.info().detail.startswith("Paused:")
        assert small.generate(request("a")).error is None
        assert large.generate(request("b")).error is None
        paused = small.info()
        assert paused.ready is False and paused.detail.startswith("Paused:")
        assert large.info().ready is True
        assert small.generate(request("c")).error is None
        assert small.info().ready is True and large.info().detail.startswith("Paused:")
    finally:
        small.close()
        large.close()


def test_a_model_that_failed_to_load_is_not_reported_as_paused(stub):
    pool = ModelPool()
    broken = PooledProvider(make_local(stub, model_id="stub/load-error"), pool)
    large = PooledProvider(make_gguf(stub), pool)
    try:
        assert broken.generate(request("a")).error is not None
        assert broken.inner.last_error
        assert large.generate(request("b")).error is None
        assert not broken.info().detail.startswith("Paused:")
    finally:
        broken.close()
        large.close()


def test_a_call_waiting_for_the_pool_too_long_is_busy(stub):
    pool = ModelPool()
    provider = PooledProvider(make_local(stub), pool)
    held = threading.Event()
    done = threading.Event()

    def hold():
        pool.acquire(provider.inner, timeout_s=5)
        held.set()
        done.wait(5)
        pool.release()

    thread = threading.Thread(target=hold)
    thread.start()
    held.wait(5)
    try:
        started = time.perf_counter()
        result = provider.generate(request("x", timeout_s=0.3))
        assert result.error.code is ProviderErrorCode.BUSY
        assert time.perf_counter() - started < 3
    finally:
        done.set()
        thread.join()
        provider.close()


# --- worker with a fake llama_cpp -----------------------------------------------------


class FakeLlama:
    """Stands in for llama_cpp.Llama: one token per word, three generated words."""

    template = "{{ messages }}"

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.metadata = {"tokenizer.chat_template": self.template} if self.template else {}
        self.completions: list[dict] = []
        self.resets = 0

    def token_eos(self) -> int:
        return 2

    def token_bos(self) -> int:
        return -1

    def detokenize(self, tokens, special=False) -> bytes:
        return b"<|im_end|>" if tokens == [2] else b""

    def tokenize(self, text: bytes, add_bos: bool, special: bool) -> list[int]:
        return list(range(len(text.split())))

    def reset(self) -> None:
        self.resets += 1

    def create_completion(self, prompt, **options) -> dict:
        self.completions.append({"prompt": prompt, **options})
        words = ["word"] * min(options["max_tokens"], 3)
        finish = "length" if options["max_tokens"] < 3 else "stop"
        return {
            "choices": [{"text": " ".join(words), "finish_reason": finish}],
            "usage": {"completion_tokens": len(words)},
        }


class FakeFormatter:
    def __init__(self, template, eos_token, bos_token, add_generation_prompt) -> None:
        self.eos_token = eos_token

    def __call__(self, *, messages):
        return type("Formatted", (), {"prompt": " ".join(m["content"] for m in messages)})()


class FakeLlamaPackage:
    def __init__(self) -> None:
        self.created: list[FakeLlama] = []
        self.gpu = True


@pytest.fixture
def fake_llama(monkeypatch) -> FakeLlamaPackage:
    state = FakeLlamaPackage()
    package = type(sys)("llama_cpp")
    package.__version__ = "0.0-test"

    def make(**kwargs):
        instance = FakeLlama(**kwargs)
        state.created.append(instance)
        return instance

    package.Llama = make
    package.llama_supports_gpu_offload = lambda: state.gpu
    chat_format = type(sys)("llama_cpp.llama_chat_format")
    chat_format.Jinja2ChatFormatter = FakeFormatter
    monkeypatch.setitem(sys.modules, "llama_cpp", package)
    monkeypatch.setitem(sys.modules, "llama_cpp.llama_chat_format", chat_format)
    return state


def gguf_folder(tmp_path: Path, content: bytes = b"gguf weights") -> tuple[Path, str]:
    folder = tmp_path / "gguf"
    folder.mkdir(exist_ok=True)
    (folder / GGUF_NAME).write_bytes(content)
    return folder, hashlib.sha256(content).hexdigest()


def load_line(folder: Path, **overrides) -> dict:
    message = {
        "type": "load",
        "protocol": 1,
        "model_dir": str(folder),
        "model_id": "org/model",
        "model_revision": REVISION,
        "adapter_dir": None,
        "adapter_id": None,
        "adapter_sha256": None,
        "device": "cpu",
        "dtype": "float16",
        "gguf_file": GGUF_NAME,
        "gguf_sha256": None,
        "context_tokens": 512,
        "gpu_layers": -1,
    }
    message.update(overrides)
    return message


def generate_line(request_id="r1", content="two words", **overrides) -> dict:
    message = {
        "type": "generate",
        "id": request_id,
        "messages": [{"role": "user", "content": content}],
        "max_new_tokens": 8,
        "temperature": 0.0,
        "top_p": 1.0,
        "seed": 1,
        "max_input_tokens": 64,
        "use_adapter": False,
    }
    message.update(overrides)
    return message


def backend(folder: Path, **overrides) -> gguf_worker.LlamaCppBackend:
    line = load_line(folder, **overrides)
    return gguf_worker.LlamaCppBackend(
        model_worker.parse_load(line), gguf_worker.parse_options(line)
    )


def run_serve(lines: list) -> tuple[int, list[dict]]:
    raw = b"".join(json.dumps(line).encode("utf-8") + b"\n" for line in lines)
    out = io.BytesIO()
    code = gguf_worker.serve(io.BytesIO(raw), out)
    return code, [json.loads(line) for line in out.getvalue().decode("utf-8").splitlines()]


def test_backend_verifies_the_checksum_and_generates_greedily(tmp_path, fake_llama):
    folder, sha = gguf_folder(tmp_path)
    model = backend(folder, gguf_sha256=sha)
    identity = model.identity()
    assert identity["gguf_sha256"] == sha and identity["revision_verified"] is True
    assert identity["adapter_sha256"] is None and identity["dtype"] == "float16"
    created = fake_llama.created[0]
    assert created.kwargs["n_ctx"] == 512 and created.kwargs["n_gpu_layers"] == 0
    reply = model.generate(model_worker.parse_generate(generate_line()))
    assert reply["text"] == "word word word" and reply["finish_reason"] == "stop"
    assert reply["prompt_tokens"] == 2 and reply["completion_tokens"] == 3
    options = created.completions[0]
    assert options["temperature"] == 0.0 and options["top_k"] == 1
    assert options["stop"] == list(gguf_worker.STOP_STRINGS)
    assert options["repeat_penalty"] == 1.0 and options["min_p"] == 0.0
    assert created.resets == 1


def test_backend_sampling_and_length(tmp_path, fake_llama):
    folder, _ = gguf_folder(tmp_path)
    model = backend(folder)
    assert model.identity()["revision_verified"] is False  # no pinned checksum
    line = generate_line(temperature=0.7, top_p=0.9, seed=5, max_new_tokens=2)
    reply = model.generate(model_worker.parse_generate(line))
    assert reply["finish_reason"] == "length" and reply["completion_tokens"] == 2
    options = fake_llama.created[0].completions[0]
    assert (options["temperature"], options["top_p"], options["top_k"], options["seed"]) == (
        0.7,
        0.9,
        0,
        5,
    )


def test_backend_input_limits(tmp_path, fake_llama):
    folder, _ = gguf_folder(tmp_path)
    model = backend(folder)
    too_many = model_worker.parse_generate(generate_line(content="a b c d e", max_input_tokens=4))
    with pytest.raises(model_worker.WorkerError) as raised:
        model.generate(too_many)
    assert raised.value.code == "input_too_long"
    no_room = model_worker.parse_generate(generate_line(content="a b", max_new_tokens=511))
    with pytest.raises(model_worker.WorkerError, match="context") as raised:
        model.generate(no_room)
    assert raised.value.code == "input_too_long"
    assert fake_llama.created[0].completions == []


def test_backend_load_failures(tmp_path, fake_llama, monkeypatch):
    folder, _ = gguf_folder(tmp_path)
    with pytest.raises(model_worker.LoadError, match="does not match"):
        backend(folder, gguf_sha256="0" * 64)
    with pytest.raises(model_worker.LoadError, match="not found"):
        backend(folder, gguf_file="other.gguf")
    with pytest.raises(model_worker.LoadError, match="without a LoRA adapter"):
        backend(folder, adapter_dir="a", adapter_id="a")
    fake_llama.gpu = False
    with pytest.raises(model_worker.LoadError, match="no GPU support"):
        backend(folder, device="cuda")
    fake_llama.gpu = True
    monkeypatch.setattr(FakeLlama, "template", "")
    with pytest.raises(model_worker.LoadError, match="chat template"):
        backend(folder)


def test_serve_runs_the_shared_protocol_loop(tmp_path, fake_llama):
    folder, sha = gguf_folder(tmp_path)
    lines = [
        load_line(folder, gguf_sha256=sha),
        generate_line(),
        generate_line("r2", use_adapter=True),
    ]
    code, replies = run_serve(lines)
    assert code == 0
    assert replies[0]["type"] == "starting"
    assert replies[1]["type"] == "ready" and replies[1]["gguf_sha256"] == sha
    assert replies[2]["type"] == "result" and replies[2]["text"] == "word word word"
    assert replies[3]["code"] == "unavailable"  # a GGUF model has no adapter


@pytest.mark.parametrize(
    "overrides",
    [
        {"gguf_file": None},
        {"gguf_file": "sub/model.gguf"},
        {"gguf_file": "model.bin"},
        {"gguf_sha256": "short"},
        {"context_tokens": 100},
        {"gpu_layers": -2},
        {"context_tokens": True},
    ],
)
def test_serve_rejects_bad_gguf_fields_before_starting(tmp_path, overrides):
    code, replies = run_serve([load_line(tmp_path, **overrides)])
    assert code == model_worker.LOAD_ERROR_EXIT_CODE
    assert [reply["type"] for reply in replies] == ["load_error"]


def test_serve_end_of_input_and_garbage(tmp_path):
    assert gguf_worker.serve(io.BytesIO(b""), io.BytesIO()) == 0
    out = io.BytesIO()
    assert gguf_worker.serve(io.BytesIO(b"[1]\n"), out) == model_worker.LOAD_ERROR_EXIT_CODE
    assert json.loads(out.getvalue())["type"] == "load_error"
