"""Model worker process for LocalProvider: JSON lines over stdin/stdout.

LocalProvider (core environment, no PyTorch) starts this script with the training
environment's interpreter. The worker loads the pinned base model once, plus an
optional LoRA adapter, and serves generation requests until it reads a shutdown message
or stdin closes. Only the standard library is imported at module level, so the core
environment can import this module to test the protocol loop; PyTorch, Transformers and
PEFT are imported inside TorchBackend.

Protocol version 1. Every message is one JSON object on one UTF-8 line.

Parent to worker:
    {"type": "load", "protocol": 1, "model_dir", "model_id", "model_revision",
     "adapter_dir", "adapter_id", "adapter_sha256", "adapter_config_sha256" (optional),
     "device", "dtype"}                                                     (first line)
    {"type": "generate", "id", "messages", "max_new_tokens", "temperature", "top_p",
     "seed", "max_input_tokens", "use_adapter"}
    {"type": "shutdown"}

Worker to parent:
    {"type": "starting", "protocol": 1, "pid"}   (after a valid load line, before loading;
        pid is this interpreter's own PID, which differs from the launcher's PID when a
        Windows virtual environment's python.exe starts the real interpreter)
    {"type": "ready", "protocol": 1, "model_id", "model_revision", "adapter_id",
     "adapter_sha256" (adapter_model.safetensors), "adapter_config_sha256"
     (adapter_config.json), "device", "dtype", "load_s", "revision_verified", "versions"}
    {"type": "load_error", "message"}                        (the worker then exits 3)
    {"type": "result", "id", "text", "prompt_tokens", "completion_tokens",
     "finish_reason" ("stop" or "length"), "generation_s", "use_adapter",
     "peak_vram_mb"}
    {"type": "error", "id", "code", "message"}
        code is one of input_too_long, unavailable, generation_error. An error with
        "fatal": true (a CUDA, cuBLAS or cuDNN error that can leave the device unusable)
        is the worker's last message: it exits with code 4 and the parent restarts it.

Decoding is exactly what the request asks for: temperature 0 is greedy decoding, any
other temperature samples with that temperature and top_p (no top-k) after seeding
PyTorch with the request seed. The model repository's own sampling defaults
(generation_config.json) are replaced at load time so they never apply silently.
completion_tokens counts the generated tokens including the end-of-turn token.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

PROTOCOL_VERSION = 1
LOAD_ERROR_EXIT_CODE = 3
FATAL_ERROR_EXIT_CODE = 4
ADAPTER_WEIGHTS_FILE = "adapter_model.safetensors"
ADAPTER_CONFIG_FILE = "adapter_config.json"
# Messages of device errors after which a CUDA context is not trusted any more.
FATAL_DEVICE_MARKERS = (
    "CUDA error",
    "CUBLAS_STATUS",
    "CUDNN_STATUS",
    "cuDNN error",
    "device-side assert",
    "illegal memory access",
    "unspecified launch failure",
)
ERROR_CODES = frozenset({"input_too_long", "unavailable", "generation_error"})
DTYPES = ("bfloat16", "float16", "float32")
DEVICES = ("cuda", "cpu")
MAX_ERROR_CHARS = 500


class WorkerError(Exception):
    """An expected per-request failure reported to the parent with a typed code."""

    def __init__(self, code: str, message: str, *, fatal: bool = False) -> None:
        if code not in ERROR_CODES:
            raise ValueError(f"unknown worker error code {code!r}")
        super().__init__(message)
        self.code = code
        self.message = message
        self.fatal = fatal


def is_fatal_device_error(exc: BaseException) -> bool:
    """True for CUDA/cuBLAS/cuDNN failures after which the worker must not keep serving."""
    return isinstance(exc, RuntimeError) and any(m in str(exc) for m in FATAL_DEVICE_MARKERS)


class LoadError(Exception):
    """The model or adapter could not be loaded; the worker reports it and exits."""


@dataclass(frozen=True)
class LoadSettings:
    model_dir: Path
    model_id: str
    model_revision: str
    adapter_dir: Path | None
    adapter_id: str | None
    adapter_sha256: str | None
    device: str
    dtype: str
    adapter_config_sha256: str | None = None


@dataclass(frozen=True)
class GenerateRequest:
    id: str
    messages: list[dict]
    max_new_tokens: int
    temperature: float
    top_p: float
    seed: int
    max_input_tokens: int
    use_adapter: bool


class Backend(Protocol):
    has_adapter: bool

    def identity(self) -> dict: ...

    def generate(self, request: GenerateRequest) -> dict: ...


def _require(message: dict, key: str, kinds: type | tuple[type, ...], *, nullable: bool = False):
    if key not in message:
        raise ValueError(f"missing field {key!r}")
    value = message[key]
    if value is None and nullable:
        return None
    # bool is a subclass of int; never accept it where a number is expected.
    if isinstance(value, bool) and bool not in (kinds if isinstance(kinds, tuple) else (kinds,)):
        raise ValueError(f"field {key!r} has the wrong type")
    if not isinstance(value, kinds):
        raise ValueError(f"field {key!r} has the wrong type")
    return value


def parse_load(message: dict) -> LoadSettings:
    """Validate the first protocol message. Raises ValueError on any problem."""
    if message.get("type") != "load":
        raise ValueError("the first message must have type 'load'")
    if message.get("protocol") != PROTOCOL_VERSION:
        raise ValueError(f"unsupported protocol version {message.get('protocol')!r}")
    adapter_dir = _require(message, "adapter_dir", str, nullable=True)
    adapter_id = _require(message, "adapter_id", str, nullable=True)
    if (adapter_dir is None) != (adapter_id is None):
        raise ValueError("adapter_dir and adapter_id must be given together")
    device = _require(message, "device", str)
    if device not in DEVICES:
        raise ValueError(f"device must be one of {DEVICES}")
    dtype = _require(message, "dtype", str)
    if dtype not in DTYPES:
        raise ValueError(f"dtype must be one of {DTYPES}")
    return LoadSettings(
        model_dir=Path(_require(message, "model_dir", str)),
        model_id=_require(message, "model_id", str),
        model_revision=_require(message, "model_revision", str),
        adapter_dir=None if adapter_dir is None else Path(adapter_dir),
        adapter_id=adapter_id,
        adapter_sha256=_require(message, "adapter_sha256", str, nullable=True),
        adapter_config_sha256=(
            _require(message, "adapter_config_sha256", str, nullable=True)
            if "adapter_config_sha256" in message
            else None
        ),
        device=device,
        dtype=dtype,
    )


def parse_generate(message: dict) -> GenerateRequest:
    """Validate a generate message. Raises ValueError on any problem."""
    request_id = _require(message, "id", str)
    messages = _require(message, "messages", list)
    if not messages:
        raise ValueError("messages must not be empty")
    for item in messages:
        if (
            not isinstance(item, dict)
            or set(item) != {"role", "content"}
            or item["role"] not in ("system", "user", "assistant")
            or not isinstance(item["content"], str)
        ):
            raise ValueError("each message needs exactly a valid role and a string content")
    max_new_tokens = _require(message, "max_new_tokens", int)
    max_input_tokens = _require(message, "max_input_tokens", int)
    temperature = float(_require(message, "temperature", (int, float)))
    top_p = float(_require(message, "top_p", (int, float)))
    seed = _require(message, "seed", int)
    use_adapter = _require(message, "use_adapter", bool)
    if max_new_tokens < 1 or max_input_tokens < 1:
        raise ValueError("token limits must be positive")
    if not 0.0 <= temperature <= 2.0 or not 0.0 < top_p <= 1.0:
        raise ValueError("temperature or top_p out of range")
    return GenerateRequest(
        id=request_id,
        messages=[{"role": m["role"], "content": m["content"]} for m in messages],
        max_new_tokens=max_new_tokens,
        temperature=temperature,
        top_p=top_p,
        seed=seed,
        max_input_tokens=max_input_tokens,
        use_adapter=use_adapter,
    )


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_revision(model_dir: Path, revision: str) -> bool:
    """Compare the commit recorded by huggingface_hub.snapshot_download(local_dir=...).

    Each downloaded file has a metadata file whose first line is the commit hash.
    Returns True when all of them match, False when no metadata exists, and raises
    LoadError when any file came from a different commit.
    """
    metadata_root = model_dir / ".cache" / "huggingface" / "download"
    commits = set()
    if metadata_root.is_dir():
        for metadata in metadata_root.rglob("*.metadata"):
            lines = metadata.read_text(encoding="utf-8").splitlines()
            if lines:
                commits.add(lines[0].strip())
    if not commits:
        return False
    if commits != {revision}:
        raise LoadError(
            f"model files come from revision(s) {sorted(commits)}, "
            f"but the configuration pins {revision}"
        )
    return True


def chat_prompt_text(tokenizer, messages: list[dict]) -> str:
    """The text the model continues: the chat template with the assistant turn opened.

    Inference (TorchBackend) and LoRA training (training/train_lora.py) both use this
    function, and both tokenize its result with add_special_tokens=False, so the
    fine-tuned prompt format equals the inference format token for token.
    """
    return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)


def _short(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".strip()
    return text if len(text) <= MAX_ERROR_CHARS else text[: MAX_ERROR_CHARS - 3] + "..."


def _read_message(stream: BinaryIO) -> dict | None:
    """Next JSON object from the stream; None at end of input. Raises ValueError."""
    raw = stream.readline()
    if not raw:
        return None
    message = json.loads(raw.decode("utf-8"))
    if not isinstance(message, dict):
        raise ValueError("a protocol message must be a JSON object")
    return message


def _write_message(stream: BinaryIO, message: dict) -> None:
    stream.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
    stream.flush()


def serve(
    backend_factory: Callable[[LoadSettings], Backend],
    stdin: BinaryIO,
    stdout: BinaryIO,
) -> int:
    """Run the protocol until shutdown or end of input. Returns the process exit code."""
    try:
        first = _read_message(stdin)
        if first is None:
            return 0
        settings = parse_load(first)
        _write_message(
            stdout, {"type": "starting", "protocol": PROTOCOL_VERSION, "pid": os.getpid()}
        )
        backend = backend_factory(settings)
    except Exception as exc:  # any load failure is reported, never swallowed
        _write_message(stdout, {"type": "load_error", "message": _short(exc)})
        return LOAD_ERROR_EXIT_CODE
    _write_message(stdout, {"type": "ready", "protocol": PROTOCOL_VERSION, **backend.identity()})
    while True:
        try:
            message = _read_message(stdin)
        except ValueError as exc:
            _write_message(
                stdout,
                {
                    "type": "error",
                    "id": None,
                    "code": "generation_error",
                    "message": f"malformed request line: {_short(exc)}",
                },
            )
            continue
        if message is None or message.get("type") == "shutdown":
            return 0
        reply = handle_generate(backend, message)
        _write_message(stdout, reply)
        if reply.get("fatal") is True:  # the device may be unusable: stop serving
            return FATAL_ERROR_EXIT_CODE


def handle_generate(backend: Backend, message: dict) -> dict:
    request_id = message.get("id") if isinstance(message.get("id"), str) else None

    def error(code: str, text: str) -> dict:
        return {"type": "error", "id": request_id, "code": code, "message": text}

    if message.get("type") != "generate":
        return error("generation_error", f"unknown message type {message.get('type')!r}")
    try:
        request = parse_generate(message)
    except ValueError as exc:
        return error("generation_error", f"invalid generate request: {exc}")
    if request.use_adapter and not backend.has_adapter:
        return error(
            "unavailable",
            "use_adapter=true but no LoRA adapter is loaded; the base model is never "
            "used as a fallback",
        )
    try:
        result = backend.generate(request)
    except WorkerError as exc:
        reply = error(exc.code, exc.message)
        if exc.fatal:
            reply["fatal"] = True
        return reply
    except Exception as exc:  # report unexpected failures; device errors end the worker
        reply = error("generation_error", _short(exc))
        if is_fatal_device_error(exc):
            reply["fatal"] = True
        return reply
    return {"type": "result", "id": request.id, **result}


class TorchBackend:
    """Transformers model on one device, with an optional PEFT LoRA adapter."""

    def __init__(self, settings: LoadSettings) -> None:
        started = time.perf_counter()
        self.settings = settings
        if not settings.model_dir.is_dir():
            raise LoadError("model_dir does not exist or is not a directory")
        if settings.adapter_dir is not None and not settings.adapter_dir.is_dir():
            raise LoadError("adapter_dir does not exist or is not a directory")
        self.revision_verified = verify_revision(settings.model_dir, settings.model_revision)

        import torch
        import transformers
        from transformers import AutoModelForCausalLM, AutoTokenizer, GenerationConfig

        self.torch = torch
        self.generation_config_cls = GenerationConfig
        if settings.device == "cuda" and not torch.cuda.is_available():
            raise LoadError("device is cuda but torch.cuda.is_available() is False")
        dtype = getattr(torch, settings.dtype)
        if (
            settings.device == "cuda"
            and dtype is torch.bfloat16
            and torch.cuda.get_device_capability(0)[0] < 8
        ):  # emulated bf16 on older GPUs is slow; use float16 or float32 there
            raise LoadError("this GPU has no native bfloat16; configure float16 or float32")
        self.tokenizer = AutoTokenizer.from_pretrained(settings.model_dir, local_files_only=True)
        model = AutoModelForCausalLM.from_pretrained(
            settings.model_dir,
            dtype=dtype,
            local_files_only=True,
            device_map={"": "cuda:0" if settings.device == "cuda" else "cpu"},
        )
        self.eos_token_ids = self._eos_ids(model)
        pad = self.tokenizer.pad_token_id
        self.pad_token_id = self.eos_token_ids[0] if pad is None else pad
        # Replace the repository's sampling defaults so only requested settings apply.
        model.generation_config = GenerationConfig(
            eos_token_id=self.eos_token_ids,
            pad_token_id=self.pad_token_id,
            do_sample=False,
        )
        model.eval()
        self.adapter_sha256 = None
        self.adapter_config_sha256 = None
        self.has_adapter = settings.adapter_dir is not None
        versions = {
            "python": sys.version.split()[0],
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "transformers": transformers.__version__,
        }
        if self.has_adapter:
            weights = settings.adapter_dir / ADAPTER_WEIGHTS_FILE
            if not weights.is_file():
                raise LoadError(f"adapter_dir has no {ADAPTER_WEIGHTS_FILE}")
            config = settings.adapter_dir / ADAPTER_CONFIG_FILE
            if not config.is_file():
                raise LoadError(f"adapter_dir has no {ADAPTER_CONFIG_FILE}")
            # The weights alone are not the adapter: the config sets the LoRA scaling
            # (lora_alpha / r, rsLoRA) and layer type, so both files are identified.
            self.adapter_sha256 = sha256_file(weights)
            self.adapter_config_sha256 = sha256_file(config)
            if settings.adapter_sha256 and settings.adapter_sha256 != self.adapter_sha256:
                raise LoadError(
                    f"adapter checksum {self.adapter_sha256} does not match the configured "
                    f"adapter_sha256 {settings.adapter_sha256}"
                )
            if (
                settings.adapter_config_sha256
                and settings.adapter_config_sha256 != self.adapter_config_sha256
            ):
                raise LoadError(
                    f"adapter config checksum {self.adapter_config_sha256} does not match the "
                    f"configured adapter_config_sha256 {settings.adapter_config_sha256}"
                )
            import peft
            from peft import PeftModel

            model = PeftModel.from_pretrained(model, settings.adapter_dir, is_trainable=False)
            model.eval()
            self._check_adapter_is_effective(model)
            versions["peft"] = peft.__version__
        self.model = model
        self.device_label = (
            f"cuda:0 ({torch.cuda.get_device_name(0)})" if settings.device == "cuda" else "cpu"
        )
        self.versions = versions
        self.load_s = time.perf_counter() - started

    def _eos_ids(self, model) -> list[int]:
        ids: list[int] = []
        configured = model.generation_config.eos_token_id
        for value in configured if isinstance(configured, list) else [configured]:
            if isinstance(value, int) and value not in ids:
                ids.append(value)
        if self.tokenizer.eos_token_id is not None and self.tokenizer.eos_token_id not in ids:
            ids.append(self.tokenizer.eos_token_id)
        if not ids:
            raise LoadError("neither the model nor the tokenizer defines an end-of-sequence token")
        return ids

    def _check_adapter_is_effective(self, model) -> None:
        """Reject adapters whose LoRA B matrices are all zero (they cannot change outputs)."""
        total = 0
        nonzero = 0
        for name, parameter in model.named_parameters():
            if "lora_B" in name:
                total += 1
                if bool(parameter.detach().abs().sum() > 0):
                    nonzero += 1
        if total == 0:
            raise LoadError("the adapter added no LoRA layers to the model")
        if nonzero == 0:
            raise LoadError("every LoRA B matrix is zero, so the adapter would not change outputs")

    def identity(self) -> dict:
        return {
            "model_id": self.settings.model_id,
            "model_revision": self.settings.model_revision,
            "adapter_id": self.settings.adapter_id,
            "adapter_sha256": self.adapter_sha256,
            "adapter_config_sha256": self.adapter_config_sha256,
            "device": self.device_label,
            "dtype": self.settings.dtype,
            "load_s": round(self.load_s, 3),
            "revision_verified": self.revision_verified,
            "versions": self.versions,
            "pid": os.getpid(),
        }

    def prompt_ids(self, messages: list[dict]):
        """Token ids of the chat-formatted prompt, exactly as used for training prefixes."""
        text = chat_prompt_text(self.tokenizer, messages)
        return self.tokenizer(text, add_special_tokens=False, return_tensors="pt")["input_ids"]

    def generation_config_for(self, request: GenerateRequest):
        """Exactly the requested decoding: greedy at temperature 0, else temperature/top_p."""
        options = {
            "max_new_tokens": request.max_new_tokens,
            "eos_token_id": self.eos_token_ids,
            "pad_token_id": self.pad_token_id,
        }
        if request.temperature == 0:
            options["do_sample"] = False
        else:
            options.update(
                do_sample=True, temperature=request.temperature, top_p=request.top_p, top_k=0
            )
        return self.generation_config_cls(**options)

    def generate(self, request: GenerateRequest) -> dict:
        torch = self.torch
        try:
            input_ids = self.prompt_ids(request.messages)
        except Exception as exc:
            raise WorkerError("generation_error", f"chat template failed: {_short(exc)}") from exc
        prompt_tokens = int(input_ids.shape[1])
        if prompt_tokens > request.max_input_tokens:
            raise WorkerError(
                "input_too_long",
                f"The prompt has {prompt_tokens} tokens; max_input_tokens is "
                f"{request.max_input_tokens}.",
            )
        generation_config = self.generation_config_for(request)
        adapter_off = self.has_adapter and not request.use_adapter
        on_cuda = self.settings.device == "cuda"
        device = "cuda:0" if on_cuda else "cpu"
        input_ids = input_ids.to(device)
        if on_cuda:
            torch.cuda.reset_peak_memory_stats()
        try:
            with (
                torch.inference_mode(),
                self.model.disable_adapter() if adapter_off else nullcontext(),
            ):
                if request.temperature != 0:
                    torch.manual_seed(request.seed)
                started = time.perf_counter()
                output = self.model.generate(
                    input_ids=input_ids,
                    attention_mask=torch.ones_like(input_ids),
                    generation_config=generation_config,
                )
                if on_cuda:
                    torch.cuda.synchronize()
                generation_s = time.perf_counter() - started
        except torch.cuda.OutOfMemoryError as exc:
            torch.cuda.empty_cache()
            raise WorkerError("generation_error", f"CUDA out of memory: {_short(exc)}") from exc
        new_tokens = output[0, prompt_tokens:].tolist()
        if new_tokens and new_tokens[-1] in self.eos_token_ids:
            finish_reason = "stop"
        elif len(new_tokens) >= request.max_new_tokens:
            finish_reason = "length"
        else:
            finish_reason = "stop"
        return {
            # Never "clean up" spaces: that would change code such as "x ." or "a , b".
            "text": self.tokenizer.decode(
                new_tokens, skip_special_tokens=True, clean_up_tokenization_spaces=False
            ),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": len(new_tokens),
            "finish_reason": finish_reason,
            "generation_s": round(generation_s, 4),
            "use_adapter": request.use_adapter,
            "peak_vram_mb": (
                round(torch.cuda.max_memory_allocated() / 2**20, 1) if on_cuda else None
            ),
        }


def _protocol_stdout() -> BinaryIO:
    """Keep the real stdout for protocol lines and send everything else to stderr."""
    sys.stdout.flush()
    protocol_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return os.fdopen(protocol_fd, "wb")


def main() -> int:
    protocol_out = _protocol_stdout()
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    return serve(TorchBackend, sys.stdin.buffer, protocol_out)


if __name__ == "__main__":
    raise SystemExit(main())
