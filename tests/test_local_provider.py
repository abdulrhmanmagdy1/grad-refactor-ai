"""LocalProvider and model-worker protocol tests that run in core CI without PyTorch.

A stub worker (written to a temporary directory) speaks protocol version 1 so the
parent's success, timeout, crash, protocol-error, load-error, adapter and serialization
paths are exercised with real subprocesses. The real worker's protocol loop is tested
in-process with a fake backend. GPU tests live in test_local_provider_gpu.py.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from refactor_ai.contracts import (
    ChatMessage,
    GenerationConfig,
    GenerationRequest,
    ProviderErrorCode,
    ProviderMode,
    Role,
)
from refactor_ai.providers import model_worker
from refactor_ai.providers.local import LocalModelSettings, LocalProvider

REVISION = "a" * 40

STUB_WORKER = textwrap.dedent(
    r"""
    import hashlib, json, os, subprocess, sys, time

    def send(message):
        sys.stdout.buffer.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
        sys.stdout.buffer.flush()

    def read():
        raw = sys.stdin.buffer.readline()
        return json.loads(raw.decode("utf-8")) if raw else None

    def log(event, **fields):
        with open(os.path.join(LOAD["model_dir"], "stub-log.jsonl"), "a", encoding="utf-8") as fh:
            record = {"event": event, "pid": os.getpid(), "t": time.monotonic(), **fields}
            fh.write(json.dumps(record) + "\n")

    LOAD = read()
    mode = LOAD["model_id"]
    log("start", mode=mode)
    interpreter_pid = os.getpid()
    if mode == "stub/detached-interpreter":
        # Pretend the interpreter is a process that does not die with the launcher.
        command = [sys.executable, "-c", "import time; time.sleep(120)"]
        try:
            sleeper = subprocess.Popen(command, creationflags=0x01000000)  # BREAKAWAY_FROM_JOB
            breakaway = True
        except (OSError, ValueError):
            sleeper = subprocess.Popen(command)
            breakaway = False
        interpreter_pid = sleeper.pid
        log("sleeper", sleeper_pid=sleeper.pid, breakaway=breakaway)
    if mode != "stub/no-starting":
        send({"type": "starting", "protocol": 1, "pid": interpreter_pid})
    if mode == "stub/load-error":
        send({"type": "load_error", "message": "cannot load " + LOAD["model_dir"]})
        sys.exit(3)
    if mode == "stub/load-crash":
        sys.stderr.write("Traceback (most recent call last):\nRuntimeError: boom while loading\n")
        sys.stderr.flush()
        sys.exit(5)
    if mode == "stub/load-hang":
        time.sleep(60)
    if mode == "stub/load-garbage":
        sys.stdout.buffer.write(b"not json at all\n")
        sys.stdout.buffer.flush()
        time.sleep(60)
    adapter_sha = config_sha = None
    if LOAD["adapter_dir"]:
        path = os.path.join(LOAD["adapter_dir"], "adapter_model.safetensors")
        with open(path, "rb") as fh:
            adapter_sha = hashlib.sha256(fh.read()).hexdigest()
        if mode != "stub/no-config-sha":
            with open(os.path.join(LOAD["adapter_dir"], "adapter_config.json"), "rb") as fh:
                config_sha = hashlib.sha256(fh.read()).hexdigest()
    revision = "f" * 40 if mode == "stub/wrong-identity" else LOAD["model_revision"]
    send({
        "type": "ready", "protocol": 1, "model_id": LOAD["model_id"],
        "model_revision": revision, "adapter_id": LOAD["adapter_id"],
        "adapter_sha256": adapter_sha, "adapter_config_sha256": config_sha,
        "device": "stub-device", "dtype": LOAD["dtype"],
        "load_s": 0.01, "revision_verified": mode != "stub/unverified",
        "versions": {}, "pid": os.getpid(),
    })
    while True:
        message = read()
        if message is None or message.get("type") == "shutdown":
            log("exit")
            sys.exit(0)
        request_id = message["id"]
        content = message["messages"][-1]["content"]
        log("request", id=request_id, content=content)
        words = content.split()
        if len(words) > message["max_input_tokens"]:
            send({"type": "error", "id": request_id, "code": "input_too_long",
                  "message": "prompt has %d tokens" % len(words)})
            continue
        if content.startswith("SLEEP:"):
            time.sleep(float(content.split(":", 1)[1].split()[0]))
        if content == "CRASH":
            sys.stderr.write("fatal: simulated crash\n")
            sys.stderr.flush()
            os._exit(7)
        if content == "GARBAGE":
            sys.stdout.buffer.write(b"this is not json\n")
            sys.stdout.buffer.flush()
            continue
        if content == "WRONG_ID":
            send({"type": "result", "id": "someone-else", "text": "x", "prompt_tokens": 1,
                  "completion_tokens": 1, "finish_reason": "stop", "generation_s": 0.0,
                  "use_adapter": message["use_adapter"], "peak_vram_mb": None})
            continue
        if content == "BAD_FIELDS":
            send({"type": "result", "id": request_id, "text": 123, "prompt_tokens": -1,
                  "completion_tokens": 1, "finish_reason": "maybe", "generation_s": 0.0,
                  "use_adapter": message["use_adapter"], "peak_vram_mb": None})
            continue
        if content == "UNKNOWN_CODE":
            send({"type": "error", "id": request_id, "code": "weird", "message": "x"})
            continue
        if content == "LIST_CODE":
            send({"type": "error", "id": request_id, "code": ["x"], "message": "x"})
            continue
        if content == "DICT_CODE":
            send({"type": "error", "id": request_id, "code": {"a": 1}, "message": "x"})
            continue
        if content in ("CUDA_FATAL", "FATAL_NO_EXIT"):
            send({"type": "error", "id": request_id, "code": "generation_error",
                  "message": "RuntimeError: CUDA error: unspecified launch failure",
                  "fatal": True})
            if content == "CUDA_FATAL":
                log("fatal-exit")
                sys.exit(4)
            continue
        if content == "FLIP_ADAPTER":
            send({"type": "result", "id": request_id, "text": "x", "prompt_tokens": 1,
                  "completion_tokens": 1, "finish_reason": "stop", "generation_s": 0.0,
                  "use_adapter": not message["use_adapter"], "peak_vram_mb": None})
            continue
        if content == "STDERR_NOISE":
            for _ in range(4000):
                sys.stderr.write("noise " * 10 + "\n")
            sys.stderr.flush()
        label = "adapter" if message["use_adapter"] else "base"
        output = ("echo[%s]: " % label) + content
        tokens = output.split(" ")
        finish = "stop"
        if len(tokens) > message["max_new_tokens"]:
            tokens = tokens[: message["max_new_tokens"]]
            output = " ".join(tokens)
            finish = "length"
        log("response", id=request_id)
        send({"type": "result", "id": request_id, "text": output,
              "prompt_tokens": len(words), "completion_tokens": len(tokens),
              "finish_reason": finish, "generation_s": 0.0,
              "use_adapter": message["use_adapter"], "peak_vram_mb": None})
    """
)


def pid_alive(pid: int) -> bool:
    """Liveness check that never signals the process (os.kill terminates on Windows)."""
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


@pytest.fixture
def stub(tmp_path):
    script = tmp_path / "stub_worker.py"
    script.write_text(STUB_WORKER, encoding="utf-8")
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    return script, model_dir


def make_provider(stub, model_id="stub/ok", **overrides) -> LocalProvider:
    script, model_dir = stub
    values = {
        "python": sys.executable,
        "model_dir": model_dir,
        "model_id": model_id,
        "model_revision": REVISION,
        "device": "cpu",
        "dtype": "float32",
        "load_timeout_s": 20,
    }
    values.update(overrides)
    return LocalProvider(LocalModelSettings(**values), worker_script=script)


def request(content: str, *, use_adapter: bool = False, **config) -> GenerationRequest:
    config.setdefault("timeout_s", 20)
    return GenerationRequest(
        role=Role.REFACTOR,
        messages=[
            ChatMessage(role="system", content="system text"),
            ChatMessage(role="user", content=content),
        ],
        config=GenerationConfig(**config),
        use_adapter=use_adapter,
    )


def stub_log(stub) -> list[dict]:
    path = stub[1] / "stub-log.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- success path ---------------------------------------------------------------------


def test_success_reports_identity_tokens_and_mode(stub):
    with make_provider(stub) as provider:
        assert provider.mode is ProviderMode.LOCAL_MODEL
        result = provider.generate(request("hello local model"))
        assert result.error is None
        assert result.text == "echo[base]: hello local model"
        assert result.provider_mode is ProviderMode.LOCAL_MODEL
        assert result.finish_reason == "stop"
        assert result.prompt_tokens == 3 and result.completion_tokens == 4
        assert result.model.model_id == "stub/ok"
        assert result.model.model_revision == REVISION
        assert result.model.adapter_id is None and result.model.adapter_sha256 is None
        assert result.model.use_adapter is False
        assert result.elapsed_s > 0
        assert any("started during this call" in w for w in result.warnings)
        second = provider.generate(request("again"))
        assert second.error is None and second.warnings == []
        assert provider.worker_starts == 1


def test_info_before_during_and_after(stub):
    provider = make_provider(stub)
    before = provider.info()
    assert before.ready is False and "not started" in before.detail
    assert before.model_id == "stub/ok" and before.model_revision == REVISION
    loaded = provider.warm_up()
    assert loaded.ready is True and loaded.device == "stub-device"
    assert "revision verified: True" in loaded.detail
    provider.close()
    closed = provider.info()
    assert closed.ready is False and closed.detail == "Provider closed."


def test_utf8_round_trip(stub):
    text = "café – مرحبا – \U0001d518 – 日本"
    with make_provider(stub) as provider:
        result = provider.generate(request(text))
        assert result.error is None
        assert result.text == "echo[base]: " + text


def test_unencodable_text_is_a_typed_error_without_restart(stub):
    with make_provider(stub) as provider:
        assert provider.generate(request("warm")).error is None
        pid = provider.worker_pid
        result = provider.generate(request("bad \ud800 surrogate"))
        assert result.error.code is ProviderErrorCode.GENERATION_ERROR
        assert "UTF-8" in result.error.message
        assert provider.worker_pid == pid


def test_max_new_tokens_reports_length(stub):
    with make_provider(stub) as provider:
        result = provider.generate(request("one two three four", max_new_tokens=2))
        assert result.error is None
        assert result.finish_reason == "length"
        assert result.completion_tokens == 2


def test_input_too_long_keeps_the_worker(stub):
    with make_provider(stub) as provider:
        assert provider.generate(request("short")).error is None
        pid = provider.worker_pid
        result = provider.generate(request("a b c d e", max_input_tokens=3))
        assert result.error.code is ProviderErrorCode.INPUT_TOO_LONG
        assert result.finish_reason == "error" and result.model is None
        assert provider.worker_pid == pid
        assert provider.generate(request("still alive")).error is None


def test_large_stderr_output_does_not_block_the_worker(stub):
    with make_provider(stub) as provider:
        result = provider.generate(request("STDERR_NOISE"))
        assert result.error is None and result.text == "echo[base]: STDERR_NOISE"


def test_unverified_revision_is_warned(stub):
    with make_provider(stub, model_id="stub/unverified") as provider:
        result = provider.generate(request("x"))
        assert result.error is None
        assert any("could not be verified" in w for w in result.warnings)


# --- timeout, crash and protocol errors -----------------------------------------------


def test_timeout_kills_only_the_worker_and_next_call_restarts(stub):
    with make_provider(stub) as provider:
        assert provider.generate(request("warm")).error is None
        old_worker = provider._worker
        old_pid = provider.worker_pid
        started = time.monotonic()
        result = provider.generate(request("SLEEP:30", timeout_s=0.5))
        assert time.monotonic() - started < 10
        assert result.error.code is ProviderErrorCode.TIMEOUT
        assert result.finish_reason == "error"
        assert old_worker.process.poll() is not None  # that exact process was terminated
        assert not pid_alive(old_pid)
        assert provider.worker_pid is None
        assert pid_alive(os.getpid())  # the parent is untouched
        after = provider.generate(request("after timeout"))
        assert after.error is None and after.text == "echo[base]: after timeout"
        assert provider.worker_pid not in (None, old_pid)
        assert provider.worker_starts == 2
        events = stub_log(stub)
        slept = [e for e in events if e["event"] == "request" and e["content"] == "SLEEP:30"]
        assert len(slept) == 1 and slept[0]["pid"] == old_pid
        responded = {e["id"] for e in events if e["event"] == "response"}
        assert slept[0]["id"] not in responded


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher and job-object behavior")
def test_interpreter_that_outlives_its_launcher_is_terminated(stub, caplog):
    """If the reported interpreter survives the launcher kill, its own handle stops it."""
    with make_provider(stub, model_id="stub/detached-interpreter") as provider:
        assert provider.generate(request("warm")).error is None
        launcher = provider._worker.process
        interpreter_pid = provider.worker_pid
        assert interpreter_pid != launcher.pid and pid_alive(interpreter_pid)
        with caplog.at_level("ERROR", logger="refactor_ai.providers.local"):
            result = provider.generate(request("SLEEP:30", timeout_s=0.5))
        assert result.error.code is ProviderErrorCode.TIMEOUT
        assert launcher.poll() is not None
        assert not pid_alive(interpreter_pid)
        breakaway = next(e for e in stub_log(stub) if e["event"] == "sleeper")["breakaway"]
        if breakaway:  # it really was outside the launcher's job, so the fallback ran
            assert "outlived its launcher" in caplog.text


def test_worker_crash_is_reported_and_restarted(stub):
    with make_provider(stub) as provider:
        result = provider.generate(request("CRASH"))
        assert result.error.code is ProviderErrorCode.GENERATION_ERROR
        assert "exit code 7" in result.error.message
        assert "simulated crash" in result.error.message
        assert provider.generate(request("recovered")).error is None
        assert provider.worker_starts == 2


@pytest.mark.parametrize(
    "content",
    ["GARBAGE", "WRONG_ID", "BAD_FIELDS", "UNKNOWN_CODE", "LIST_CODE", "DICT_CODE", "FLIP_ADAPTER"],
)
def test_malformed_worker_output_is_a_protocol_error(stub, content):
    with make_provider(stub) as provider:
        assert provider.generate(request("warm")).error is None
        old_worker = provider._worker
        result = provider.generate(request(content))
        assert result.error.code is ProviderErrorCode.GENERATION_ERROR
        assert "protocol error" in result.error.message
        assert old_worker.process.poll() is not None
        assert provider.generate(request("next")).error is None
        assert provider.worker_starts == 2


# --- load failures --------------------------------------------------------------------


def test_load_error_is_typed_and_redacts_host_paths(stub):
    provider = make_provider(stub, model_id="stub/load-error")
    result = provider.generate(request("x"))
    assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    assert "cannot load <model_dir>" in result.error.message
    assert str(stub[1]) not in result.error.message
    info = provider.info()
    assert info.ready is False and "cannot load" in info.detail
    provider.close()


def test_load_crash_reports_exit_code_and_log_line(stub):
    provider = make_provider(stub, model_id="stub/load-crash")
    result = provider.generate(request("x"))
    assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    assert "exit code 5" in result.error.message
    assert "boom while loading" in result.error.message
    provider.close()


def test_load_timeout_kills_the_loading_worker(stub):
    provider = make_provider(stub, model_id="stub/load-hang", load_timeout_s=0.5)
    started = time.monotonic()
    result = provider.generate(request("x"))
    assert time.monotonic() - started < 10
    assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    assert "did not finish loading" in result.error.message
    pids = [e["pid"] for e in stub_log(stub) if e["event"] == "start"]
    assert len(pids) == 1 and not pid_alive(pids[0])
    provider.close()


@pytest.mark.parametrize(
    ("model_id", "expected"),
    [
        ("stub/wrong-identity", "different model identity"),
        ("stub/load-garbage", "not JSON"),
        ("stub/no-starting", "expected a starting message"),
    ],
)
def test_bad_ready_message_is_a_load_error(stub, model_id, expected):
    provider = make_provider(stub, model_id=model_id)
    result = provider.generate(request("x"))
    assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    assert expected in result.error.message
    assert provider.worker_pid is None
    provider.close()


def test_missing_interpreter_or_model_dir_fails_without_spawning(stub, tmp_path):
    missing_python = make_provider(stub, python=tmp_path / "no" / "python.exe")
    result = missing_python.generate(request("x"))
    assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    assert "interpreter" in result.error.message
    missing_model = make_provider(stub, model_dir=tmp_path / "absent")
    result = missing_model.generate(request("x"))
    assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    assert "model_dir" in result.error.message
    assert stub_log(stub) == []


def test_real_worker_without_torch_reports_a_load_error(tmp_path):
    """The real model_worker.py run by an interpreter without PyTorch fails cleanly."""
    probe = subprocess.run(
        [sys.executable, "-c", "import importlib.util; print(importlib.util.find_spec('torch'))"],
        capture_output=True,
        text=True,
        check=True,
    )
    if probe.stdout.strip() != "None":
        pytest.skip("this interpreter has PyTorch; the check needs an environment without it")
    settings = LocalModelSettings(
        python=sys.executable,
        model_dir=tmp_path,
        model_id="Qwen/Qwen2.5-Coder-0.5B-Instruct",
        model_revision=REVISION,
        device="cpu",
        dtype="float32",
        load_timeout_s=60,
    )
    with LocalProvider(settings) as provider:
        result = provider.generate(request("x"))
        assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
        assert "No module named 'torch'" in result.error.message


# --- adapter handling -----------------------------------------------------------------


def test_adapter_requested_without_adapter_is_unavailable_and_starts_nothing(stub):
    with make_provider(stub) as provider:
        result = provider.generate(request("x", use_adapter=True))
        assert result.error.code is ProviderErrorCode.UNAVAILABLE
        assert "never used as a fallback" in result.error.message
        assert provider.worker_starts == 0 and stub_log(stub) == []


def make_adapter(tmp_path, weights=b"pretend adapter weights", config=b'{"r": 8, "alpha": 16}'):
    adapter = tmp_path / "adapter"
    adapter.mkdir()
    (adapter / "adapter_model.safetensors").write_bytes(weights)
    (adapter / "adapter_config.json").write_bytes(config)
    return adapter, hashlib.sha256(weights).hexdigest(), hashlib.sha256(config).hexdigest()


def test_adapter_identity_and_per_call_switch(stub, tmp_path):
    adapter, digest, config_digest = make_adapter(tmp_path)
    with make_provider(stub, adapter_dir=adapter, adapter_id="pilot-adapter") as provider:
        on = provider.generate(request("x", use_adapter=True))
        off = provider.generate(request("x", use_adapter=False))
        assert on.error is None and off.error is None
        assert on.text == "echo[adapter]: x" and off.text == "echo[base]: x"
        for result, active in ((on, True), (off, False)):
            assert result.model.adapter_id == "pilot-adapter"
            assert result.model.adapter_sha256 == digest
            assert result.model.use_adapter is active
        info = provider.info()
        assert info.adapter_sha256 == digest
        assert digest in info.detail and config_digest in info.detail


def test_adapter_config_checksum_is_verified(stub, tmp_path):
    """Same weights with another adapter_config.json (e.g. lora_alpha) must not pass."""
    adapter, digest, config_digest = make_adapter(tmp_path)
    good = make_provider(
        stub,
        adapter_dir=adapter,
        adapter_id="pilot-adapter",
        adapter_sha256=digest,
        adapter_config_sha256=config_digest,
    )
    assert good.generate(request("x", use_adapter=True)).error is None
    good.close()
    (adapter / "adapter_config.json").write_bytes(b'{"r": 8, "alpha": 32}')
    changed = make_provider(
        stub,
        adapter_dir=adapter,
        adapter_id="pilot-adapter",
        adapter_sha256=digest,
        adapter_config_sha256=config_digest,
    )
    result = changed.generate(request("x", use_adapter=True))
    assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    assert "adapter_config_sha256" in result.error.message
    assert changed.generate(request("x")).error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    changed.close()


def test_worker_must_report_the_adapter_config_checksum(stub, tmp_path):
    adapter, _, _ = make_adapter(tmp_path)
    provider = make_provider(
        stub, model_id="stub/no-config-sha", adapter_dir=adapter, adapter_id="pilot-adapter"
    )
    result = provider.generate(request("x", use_adapter=True))
    assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    assert "adapter config checksum" in result.error.message
    provider.close()


def test_adapter_checksum_mismatch_is_a_load_error(stub, tmp_path):
    adapter, _, _ = make_adapter(tmp_path, weights=b"weights")
    provider = make_provider(
        stub, adapter_dir=adapter, adapter_id="pilot-adapter", adapter_sha256="0" * 64
    )
    result = provider.generate(request("x", use_adapter=True))
    assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    assert "checksum" in result.error.message
    # The base model is not served instead: plain calls fail the same way.
    assert provider.generate(request("x")).error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    provider.close()


def test_missing_adapter_dir_is_a_load_error(stub, tmp_path):
    provider = make_provider(stub, adapter_dir=tmp_path / "missing", adapter_id="a")
    result = provider.generate(request("x"))
    assert result.error.code is ProviderErrorCode.MODEL_LOAD_ERROR
    assert "adapter_dir" in result.error.message
    provider.close()


# --- serialization and lifecycle ------------------------------------------------------


def test_concurrent_calls_are_serialized_without_cross_talk(stub):
    with make_provider(stub) as provider:
        results: dict[int, object] = {}

        def call(index: int) -> None:
            results[index] = provider.generate(request(f"SLEEP:0.05 caller-{index}"))

        threads = [threading.Thread(target=call, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert len(results) == 8
        for index, result in results.items():
            assert result.error is None
            assert result.text == f"echo[base]: SLEEP:0.05 caller-{index}"
        events = [e for e in stub_log(stub) if e["event"] in ("request", "response")]
        assert [e["event"] for e in events] == ["request", "response"] * 8


def test_busy_when_the_lock_is_not_free_within_the_timeout(stub):
    with make_provider(stub) as provider:
        assert provider.generate(request("warm")).error is None
        slow: list = []
        thread = threading.Thread(
            target=lambda: slow.append(provider.generate(request("SLEEP:1.5")))
        )
        thread.start()
        time.sleep(0.3)
        busy = provider.generate(request("impatient", timeout_s=0.2))
        thread.join(timeout=30)
        assert busy.error.code is ProviderErrorCode.BUSY
        assert slow[0].error is None


def test_close_is_graceful_idempotent_and_final(stub):
    provider = make_provider(stub)
    assert provider.generate(request("x")).error is None
    worker = provider._worker
    provider.close()
    provider.close()
    assert worker.process.poll() == 0
    assert any(e["event"] == "exit" for e in stub_log(stub))
    result = provider.generate(request("after close"))
    assert result.error.code is ProviderErrorCode.UNAVAILABLE


def test_close_during_a_call_stops_the_worker_promptly(stub):
    provider = make_provider(stub)
    assert provider.generate(request("warm")).error is None
    outcome: list = []
    thread = threading.Thread(
        target=lambda: outcome.append(provider.generate(request("SLEEP:20", timeout_s=60)))
    )
    thread.start()
    time.sleep(0.5)
    started = time.monotonic()
    provider.close()
    thread.join(timeout=30)
    assert time.monotonic() - started < 15
    assert outcome[0].error.code is ProviderErrorCode.GENERATION_ERROR


def test_close_during_warm_up_stops_the_loading_worker(stub):
    """API shutdown during the model load must not leave an orphan worker behind."""
    provider = make_provider(stub, model_id="stub/load-hang", load_timeout_s=180)
    loader = threading.Thread(target=provider.warm_up, daemon=True)
    loader.start()
    deadline = time.monotonic() + 20
    while not [e for e in stub_log(stub) if e["event"] == "start"]:
        assert time.monotonic() < deadline, "the stub never started"
        time.sleep(0.05)
    time.sleep(0.5)  # the worker has sent 'starting' and is now "loading"
    loading = provider._loading
    assert loading is not None and provider._worker is None
    started = time.monotonic()
    provider.close()
    assert time.monotonic() - started < 10
    assert loading.process.poll() is not None
    pid = [e["pid"] for e in stub_log(stub) if e["event"] == "start"][0]
    stopped = time.monotonic() + 10
    while pid_alive(pid) and time.monotonic() < stopped:
        time.sleep(0.1)
    assert not pid_alive(pid)
    loader.join(timeout=10)
    assert not loader.is_alive()
    assert provider._loading is None and provider._worker is None
    info = provider.info()
    assert info.ready is False and info.detail == "Provider closed."
    assert provider.generate(request("x")).error.code is ProviderErrorCode.UNAVAILABLE


@pytest.mark.parametrize("content", ["CUDA_FATAL", "FATAL_NO_EXIT"])
def test_fatal_device_error_restarts_the_worker(stub, content):
    """After a CUDA error the worker is not trusted: it is replaced on the next call."""
    with make_provider(stub) as provider:
        assert provider.generate(request("warm")).error is None
        old_worker = provider._worker
        result = provider.generate(request(content))
        assert result.error.code is ProviderErrorCode.GENERATION_ERROR
        assert "CUDA error" in result.error.message
        assert "will restart" in result.error.message
        assert provider._worker is None
        assert old_worker.process.poll() is not None  # exited by itself or was stopped
        after = provider.generate(request("after"))
        assert after.error is None and provider.worker_starts == 2


# --- configuration --------------------------------------------------------------------


def write_config(path: Path, **values) -> Path:
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def test_from_config_resolves_paths_relative_to_the_file(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config = write_config(
        config_dir / "model.local.json",
        _comment="comments start with an underscore",
        python="../.venv-train/Scripts/python.exe",
        model_dir="../models/m",
        model_id="org/model",
        model_revision=REVISION,
        adapter_dir="../runs/adapter",
        adapter_id="adapter-1",
    )
    provider = LocalProvider.from_config(config)
    settings = provider.settings
    expected = Path(os.path.abspath(tmp_path))
    assert settings.python == expected / ".venv-train" / "Scripts" / "python.exe"
    assert settings.model_dir == expected / "models" / "m"
    assert settings.adapter_dir == expected / "runs" / "adapter"
    assert settings.device == "cuda" and settings.dtype == "bfloat16"


def test_from_config_keeps_a_symlinked_interpreter(tmp_path):
    """A venv's python is often a symlink; following it would leave the venv."""
    target = tmp_path / "base" / "python.exe"
    target.parent.mkdir()
    target.write_bytes(b"")
    link = tmp_path / "venv" / "bin" / "python.exe"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symbolic links are not available here: {exc}")
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config = write_config(
        config_dir / "model.local.json",
        python="../venv/bin/python.exe",
        model_dir="../models/m",
        model_id="org/model",
        model_revision=REVISION,
    )
    settings = LocalModelSettings.from_file(config)
    assert settings.python == Path(os.path.abspath(link))
    assert settings.python.is_symlink()
    assert settings.python != target


@pytest.mark.parametrize(
    "values",
    [
        {"model_revision": "main"},
        {"unknown_key": 1},
        {"adapter_dir": "adapter"},
        {"adapter_id": "adapter"},
        {"adapter_sha256": "0" * 64},
        {"adapter_config_sha256": "0" * 64},
        {"adapter_dir": "a", "adapter_id": "a", "adapter_config_sha256": "not-a-sha"},
        {"device": "tpu"},
        {"load_timeout_s": 0},
    ],
)
def test_invalid_configs_are_rejected(tmp_path, values):
    base = {
        "python": "python.exe",
        "model_dir": "model",
        "model_id": "org/model",
        "model_revision": REVISION,
    }
    with pytest.raises(ValidationError):
        LocalProvider.from_config(write_config(tmp_path / "c.json", **{**base, **values}))


def test_config_must_be_an_object(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ValueError):
        LocalModelSettings.from_file(path)


def test_example_config_is_valid_and_pinned():
    root = Path(__file__).resolve().parents[1]
    settings = LocalModelSettings.from_file(root / "configs" / "model.example.json")
    assert settings.model_id == "Qwen/Qwen2.5-Coder-0.5B-Instruct"
    assert len(settings.model_revision) == 40
    assert settings.adapter_dir is None


def test_core_imports_do_not_load_torch():
    code = (
        "import sys, refactor_ai.providers.local, refactor_ai.providers.model_worker;"
        "assert 'torch' not in sys.modules and 'transformers' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


# --- the real worker's protocol loop (in-process, fake backend) -----------------------


class FakeBackend:
    def __init__(self, settings: model_worker.LoadSettings) -> None:
        self.settings = settings
        self.has_adapter = settings.adapter_dir is not None

    def identity(self) -> dict:
        return {"model_id": self.settings.model_id, "adapter_sha256": None}

    def generate(self, request: model_worker.GenerateRequest) -> dict:
        content = request.messages[-1]["content"]
        if content == "too long":
            raise model_worker.WorkerError("input_too_long", "prompt has 9 tokens")
        if content == "explode":
            raise RuntimeError("backend bug")
        if content == "cuda":
            raise RuntimeError("CUDA error: unspecified launch failure")
        if content == "oom":
            raise RuntimeError("CUDA out of memory. Tried to allocate 56.00 MiB")
        if content == "fatal-worker-error":
            raise model_worker.WorkerError("generation_error", "device lost", fatal=True)
        return {"text": content.upper(), "use_adapter": request.use_adapter}


def load_line(**overrides) -> dict:
    message = {
        "type": "load",
        "protocol": 1,
        "model_dir": "m",
        "model_id": "org/model",
        "model_revision": REVISION,
        "adapter_dir": None,
        "adapter_id": None,
        "adapter_sha256": None,
        "device": "cpu",
        "dtype": "float32",
    }
    message.update(overrides)
    return message


def generate_line(request_id: str = "r1", content: str = "hi", **overrides) -> dict:
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


def run_serve(lines: list, factory=FakeBackend) -> tuple[int, list[dict]]:
    raw = b"".join(
        (line if isinstance(line, bytes) else json.dumps(line).encode("utf-8")) + b"\n"
        for line in lines
    )
    out = io.BytesIO()
    code = model_worker.serve(factory, io.BytesIO(raw), out)
    replies = [json.loads(line) for line in out.getvalue().decode("utf-8").splitlines()]
    return code, replies


def test_serve_round_trip_and_shutdown():
    code, replies = run_serve([load_line(), generate_line(), {"type": "shutdown"}, generate_line()])
    assert code == 0
    assert replies[0] == {"type": "starting", "protocol": 1, "pid": os.getpid()}
    assert replies[1]["type"] == "ready" and replies[1]["protocol"] == 1
    assert replies[2] == {"type": "result", "id": "r1", "text": "HI", "use_adapter": False}
    assert len(replies) == 3  # nothing is processed after shutdown


def test_serve_end_of_input_exits_cleanly():
    code, replies = run_serve([load_line()])
    assert code == 0 and [r["type"] for r in replies] == ["starting", "ready"]
    assert run_serve([]) == (0, [])


@pytest.mark.parametrize(
    "first",
    [
        b"{not json",
        {"type": "generate"},
        load_line(protocol=2),
        load_line(adapter_dir="a"),
        load_line(device="tpu"),
        load_line(dtype="int4"),
    ],
)
def test_serve_rejects_bad_load_messages(first):
    code, replies = run_serve([first])
    assert code == model_worker.LOAD_ERROR_EXIT_CODE
    assert len(replies) == 1  # no starting message for an invalid load line
    assert replies[0]["type"] == "load_error" and replies[0]["message"]


def test_serve_reports_backend_load_failures():
    def failing(settings):
        raise model_worker.LoadError("weights missing")

    code, replies = run_serve([load_line()], factory=failing)
    assert code == model_worker.LOAD_ERROR_EXIT_CODE
    assert replies == [
        {"type": "starting", "protocol": 1, "pid": os.getpid()},
        {"type": "load_error", "message": "LoadError: weights missing"},
    ]


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"messages": []}, "must not be empty"),
        ({"messages": [{"role": "tool", "content": "x"}]}, "valid role"),
        ({"max_new_tokens": True}, "wrong type"),
        ({"max_new_tokens": 0}, "positive"),
        ({"temperature": 3.0}, "out of range"),
        ({"top_p": 0.0}, "out of range"),
        ({"use_adapter": "yes"}, "wrong type"),
        ({"seed": 1.5}, "wrong type"),
    ],
)
def test_serve_rejects_invalid_requests_but_keeps_running(overrides, fragment):
    code, replies = run_serve([load_line(), generate_line(**overrides), generate_line("r2")])
    assert code == 0
    error, result = replies[2:]
    assert error["type"] == "error" and error["id"] == "r1"
    assert error["code"] == "generation_error" and fragment in error["message"]
    assert result["type"] == "result" and result["id"] == "r2"


def test_serve_typed_errors_and_recovery():
    lines = [
        load_line(),
        b"{broken",
        {"type": "mystery", "id": "m"},
        generate_line("r1", use_adapter=True),
        generate_line("r2", content="too long"),
        generate_line("r3", content="explode"),
        generate_line("r4", content="fine"),
    ]
    code, replies = run_serve(lines)
    assert code == 0
    broken, mystery, adapter, too_long, explode, fine = replies[2:]
    assert broken["id"] is None and broken["code"] == "generation_error"
    assert mystery["id"] == "m" and "unknown message type" in mystery["message"]
    assert adapter["code"] == "unavailable"
    assert too_long["code"] == "input_too_long"
    assert explode["code"] == "generation_error" and "backend bug" in explode["message"]
    assert fine["type"] == "result" and fine["text"] == "FINE"


def test_worker_error_codes_are_restricted():
    with pytest.raises(ValueError):
        model_worker.WorkerError("timeout", "parents own timeouts")


@pytest.mark.parametrize("content", ["cuda", "fatal-worker-error"])
def test_serve_stops_after_a_fatal_device_error(content):
    lines = [load_line(), generate_line("r1"), generate_line("r2", content=content)]
    code, replies = run_serve([*lines, generate_line("r3")])
    assert code == model_worker.FATAL_ERROR_EXIT_CODE
    fatal = replies[-1]
    assert fatal["id"] == "r2" and fatal["code"] == "generation_error"
    assert fatal["fatal"] is True
    assert [r.get("id") for r in replies[2:]] == ["r1", "r2"]  # r3 was never served


@pytest.mark.parametrize("content", ["explode", "oom"])
def test_serve_keeps_running_after_ordinary_errors(content):
    code, replies = run_serve([load_line(), generate_line("r1", content=content), generate_line()])
    assert code == 0
    assert replies[2]["code"] == "generation_error" and "fatal" not in replies[2]
    assert replies[3]["type"] == "result"


def test_fatal_device_error_classification():
    fatal = model_worker.is_fatal_device_error
    assert fatal(RuntimeError("CUDA error: CUBLAS_STATUS_EXECUTION_FAILED when calling x"))
    assert fatal(RuntimeError("cuDNN error: CUDNN_STATUS_INTERNAL_ERROR"))
    assert fatal(RuntimeError("CUDA error: an illegal memory access was encountered"))
    assert not fatal(RuntimeError("CUDA out of memory. Tried to allocate 56.00 MiB"))
    assert not fatal(RuntimeError("backend bug"))
    assert not fatal(ValueError("CUDA error: wrong type of exception"))


def test_parse_load_accepts_an_optional_adapter_config_checksum():
    assert model_worker.parse_load(load_line()).adapter_config_sha256 is None
    settings = model_worker.parse_load(
        load_line(adapter_dir="a", adapter_id="a", adapter_config_sha256="c" * 64)
    )
    assert settings.adapter_config_sha256 == "c" * 64
    with pytest.raises(ValueError):
        model_worker.parse_load(load_line(adapter_config_sha256=5))


def test_verify_revision_reads_download_metadata(tmp_path):
    assert model_worker.verify_revision(tmp_path, REVISION) is False
    metadata = tmp_path / ".cache" / "huggingface" / "download"
    metadata.mkdir(parents=True)
    (metadata / "config.json.metadata").write_text(f"{REVISION}\netag\n1.0\n", encoding="utf-8")
    assert model_worker.verify_revision(tmp_path, REVISION) is True
    (metadata / "model.safetensors.metadata").write_text("b" * 40 + "\n", encoding="utf-8")
    with pytest.raises(model_worker.LoadError, match="pins"):
        model_worker.verify_revision(tmp_path, REVISION)


def test_sha256_file_matches_hashlib(tmp_path):
    path = tmp_path / "blob"
    path.write_bytes(b"x" * 3_000_001)
    assert model_worker.sha256_file(path) == hashlib.sha256(b"x" * 3_000_001).hexdigest()
