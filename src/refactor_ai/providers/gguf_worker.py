"""Model worker for a quantized GGUF model served by llama.cpp (project review mode).

It speaks protocol version 1 of model_worker.py and reuses its message loop, request
checks and error types. GgufProvider starts it with the training environment's interpreter
(isolated mode), where the refactor_ai package is not installed, so model_worker is then
imported from this file's own folder; only the standard library is imported at module level.

The load line carries four more fields: gguf_file (a file name inside model_dir),
gguf_sha256 (optional: the checksum published at the pinned revision), context_tokens (the
llama.cpp context: prompt plus generated tokens) and gpu_layers (-1 for every layer). The
ready message adds gguf_sha256, the checksum of the loaded file; revision_verified is true
only when that checksum matched the configured one. A GGUF model has no adapter, so
use_adapter=true is answered with unavailable by the shared loop. Decoding is exactly what
the request asks for: temperature 0 is greedy, anything else samples with that temperature
and top_p, seeded with the request seed; llama.cpp's other samplers are switched off.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

try:
    from refactor_ai.providers import model_worker
except ImportError:  # running as the worker script in the training environment
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import model_worker  # type: ignore[no-redef]

DEFAULT_CONTEXT_TOKENS = 8192
# End-of-turn markers of the Qwen chat format; generation stops at either.
STOP_STRINGS = ("<|im_end|>", "<|endoftext|>")
MAX_ERROR_CHARS = 500


@dataclass(frozen=True)
class GgufOptions:
    gguf_file: str
    gguf_sha256: str | None = None
    context_tokens: int = DEFAULT_CONTEXT_TOKENS
    gpu_layers: int = -1


def _short(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".strip()
    return text if len(text) <= MAX_ERROR_CHARS else text[: MAX_ERROR_CHARS - 3] + "..."


def parse_options(message: dict) -> GgufOptions:
    """The GGUF fields of a load message. Raises ValueError on any problem."""
    gguf_file = message.get("gguf_file")
    if not isinstance(gguf_file, str) or Path(gguf_file).name != gguf_file:
        raise ValueError("gguf_file must be a file name inside model_dir")
    if not gguf_file.endswith(".gguf"):
        raise ValueError("gguf_file must end in .gguf")
    sha = message.get("gguf_sha256")
    if sha is not None and (not isinstance(sha, str) or len(sha) != 64):
        raise ValueError("gguf_sha256 must be a 64-character hex digest or null")
    context = message.get("context_tokens", DEFAULT_CONTEXT_TOKENS)
    layers = message.get("gpu_layers", -1)
    for name, value in (("context_tokens", context), ("gpu_layers", layers)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"field {name!r} has the wrong type")
    if context < 256 or layers < -1:
        raise ValueError("context_tokens must be at least 256 and gpu_layers at least -1")
    return GgufOptions(gguf_file, sha, context, layers)


def add_cuda_library_paths() -> None:
    """Let llama.cpp's CUDA build find the CUDA runtime that ships with PyTorch.

    The prebuilt llama-cpp-python CUDA wheels do not bundle cudart and cuBLAS. The
    training environment has them in torch/lib, so on Windows that folder is added to the
    DLL search path and to PATH. Nothing is imported from PyTorch.
    """
    if os.name != "nt":
        return
    import importlib.util

    spec = importlib.util.find_spec("torch")
    if spec is None or spec.origin is None:
        return
    library_dir = Path(spec.origin).parent / "lib"
    if library_dir.is_dir():
        os.add_dll_directory(str(library_dir))
        os.environ["PATH"] = str(library_dir) + os.pathsep + os.environ.get("PATH", "")


class LlamaCppBackend:
    """One quantized GGUF model on llama.cpp, behind the model_worker Backend interface."""

    has_adapter = False

    def __init__(self, settings, options: GgufOptions) -> None:
        started = time.perf_counter()
        self.settings = settings
        self.options = options
        if settings.adapter_dir is not None:
            raise model_worker.LoadError("a GGUF model is served without a LoRA adapter")
        if not settings.model_dir.is_dir():
            raise model_worker.LoadError("model_dir does not exist or is not a directory")
        path = settings.model_dir / options.gguf_file
        if not path.is_file():
            raise model_worker.LoadError("gguf_file was not found in model_dir")
        self.gguf_sha256 = model_worker.sha256_file(path)
        if options.gguf_sha256 and options.gguf_sha256 != self.gguf_sha256:
            raise model_worker.LoadError(
                f"GGUF checksum {self.gguf_sha256} does not match the configured "
                f"gguf_sha256 {options.gguf_sha256}"
            )
        self.revision_verified = options.gguf_sha256 is not None

        add_cuda_library_paths()
        try:
            import llama_cpp
            from llama_cpp.llama_chat_format import Jinja2ChatFormatter
        except ImportError as exc:
            raise model_worker.LoadError(
                f"llama-cpp-python is not installed: {_short(exc)}"
            ) from exc
        on_cuda = settings.device == "cuda"
        if on_cuda and not llama_cpp.llama_supports_gpu_offload():
            raise model_worker.LoadError(
                "device is cuda but this llama-cpp-python build has no GPU support"
            )
        self.llm = llama_cpp.Llama(
            model_path=str(path),
            n_ctx=options.context_tokens,
            n_gpu_layers=options.gpu_layers if on_cuda else 0,
            seed=0,
            verbose=False,
        )
        template = self.llm.metadata.get("tokenizer.chat_template")
        if not template:
            raise model_worker.LoadError("the GGUF file has no chat template")
        self.formatter = Jinja2ChatFormatter(
            template=template,
            eos_token=self._token_text(self.llm.token_eos()),
            bos_token=self._token_text(self.llm.token_bos()),
            add_generation_prompt=True,
        )
        layers = "all" if options.gpu_layers == -1 else str(options.gpu_layers)
        self.device_label = f"cuda (llama.cpp, {layers} layers on the GPU)" if on_cuda else "cpu"
        self.versions = {"python": sys.version.split()[0], "llama_cpp": llama_cpp.__version__}
        self.load_s = time.perf_counter() - started

    def _token_text(self, token: int) -> str:
        if token < 0:
            return ""
        return self.llm.detokenize([token], special=True).decode("utf-8", errors="replace")

    def identity(self) -> dict:
        return {
            "model_id": self.settings.model_id,
            "model_revision": self.settings.model_revision,
            "adapter_id": None,
            "adapter_sha256": None,
            "adapter_config_sha256": None,
            "gguf_sha256": self.gguf_sha256,
            "device": self.device_label,
            "dtype": self.settings.dtype,
            "load_s": round(self.load_s, 3),
            "revision_verified": self.revision_verified,
            "versions": self.versions,
            "pid": os.getpid(),
        }

    def generate(self, request) -> dict:
        try:
            prompt = self.formatter(messages=request.messages).prompt
        except Exception as exc:
            raise model_worker.WorkerError(
                "generation_error", f"chat template failed: {_short(exc)}"
            ) from exc
        tokens = self.llm.tokenize(prompt.encode("utf-8"), add_bos=False, special=True)
        prompt_tokens = len(tokens)
        if prompt_tokens > request.max_input_tokens:
            raise model_worker.WorkerError(
                "input_too_long",
                f"The prompt has {prompt_tokens} tokens; max_input_tokens is "
                f"{request.max_input_tokens}.",
            )
        if prompt_tokens + request.max_new_tokens > self.options.context_tokens:
            raise model_worker.WorkerError(
                "input_too_long",
                f"The prompt has {prompt_tokens} tokens; with max_new_tokens "
                f"{request.max_new_tokens} it exceeds the context of "
                f"{self.options.context_tokens} tokens.",
            )
        if request.temperature == 0:
            sampling = {"temperature": 0.0, "top_p": 1.0, "top_k": 1}
        else:
            sampling = {"temperature": request.temperature, "top_p": request.top_p, "top_k": 0}
        self.llm.reset()
        started = time.perf_counter()
        output = self.llm.create_completion(
            prompt=tokens,
            max_tokens=request.max_new_tokens,
            stop=list(STOP_STRINGS),
            seed=request.seed,
            min_p=0.0,
            typical_p=1.0,
            repeat_penalty=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
            **sampling,
        )
        generation_s = time.perf_counter() - started
        choice = output["choices"][0]
        return {
            "text": choice["text"],
            "prompt_tokens": prompt_tokens,
            "completion_tokens": int(output["usage"]["completion_tokens"]),
            "finish_reason": "length" if choice.get("finish_reason") == "length" else "stop",
            "generation_s": round(generation_s, 4),
            "use_adapter": request.use_adapter,
            "peak_vram_mb": None,
        }


class _Replay:
    """A binary stream that returns one already-read line first, then reads on."""

    def __init__(self, first: bytes, stream: BinaryIO) -> None:
        self._first: bytes | None = first
        self._stream = stream

    def readline(self) -> bytes:
        if self._first is not None:
            line, self._first = self._first, None
            return line
        return self._stream.readline()


def serve(stdin: BinaryIO, stdout: BinaryIO, backend_class=LlamaCppBackend) -> int:
    """Read the GGUF fields from the load line, then run model_worker's protocol loop."""
    first = stdin.readline()
    if not first:
        return 0
    try:
        message = json.loads(first.decode("utf-8"))
        if not isinstance(message, dict):
            raise ValueError("a protocol message must be a JSON object")
        options = parse_options(message)
    except Exception as exc:  # reported like any invalid load line, before "starting"
        stdout.write(
            (json.dumps({"type": "load_error", "message": _short(exc)}) + "\n").encode("utf-8")
        )
        stdout.flush()
        return model_worker.LOAD_ERROR_EXIT_CODE
    return model_worker.serve(
        lambda settings: backend_class(settings, options), _Replay(first, stdin), stdout
    )


def main() -> int:
    sys.stdout.flush()
    protocol_fd = os.dup(1)
    os.dup2(2, 1)  # llama.cpp and Python output go to stderr; stdout carries the protocol
    sys.stdout = sys.stderr
    protocol_out = os.fdopen(protocol_fd, "wb")
    return serve(sys.stdin.buffer, protocol_out)


if __name__ == "__main__":
    raise SystemExit(main())
