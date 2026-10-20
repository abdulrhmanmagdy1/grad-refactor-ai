# Models and training notes

Workstream: models and training (owner Abdelrahman Adel). Wave-1 tasks: T04 model benchmark, T05 LoRA feasibility pilot, T12 local model provider. Written on 2026-10-20 from the records under `experiments/` and the tests. The pilot functions in `training/pilot/functions.py` are pilot material written for this workstream, not the curated dataset, and nothing in these notes is an evaluation result.

## Status on 2026-10-20

| Item | Status |
|---|---|
| Training environment | Installed in `.venv-train` and locked in `training/requirements-cuda.txt` |
| T04 benchmark | Done for Qwen2.5-Coder-0.5B-Instruct (two runs); the 1.5B candidate was not measured because of the disk limit |
| T05 LoRA pilot | Done: trained, saved, reloaded in a fresh process, interrupted and resumed; training budget measured |
| T12 local provider | Implemented; 64 core tests pass without PyTorch; 8 real-GPU tests pass |

## Model choice

Qwen/Qwen2.5-Coder-0.5B-Instruct at revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25` is the only candidate measured. Its model card declares Apache-2.0 and the LICENSE file at that revision is the Apache License 2.0 ("Copyright 2024 Alibaba Cloud"). The card lists 0.49B parameters, 24 layers, grouped-query attention with 14 query and 2 key-value heads, tied embeddings and a 32,768-token context. The bf16 weights are one 988,097,824-byte file whose SHA-256 matched the published checksum after download.

Reasons: it is the smallest instruction-tuned code model in the family with a permissive license, its process needs about 1.0 GB of the 4 GB GPU (the desktop and other applications used 0.2 to 1.1 GB during the measurements), and it leaves room for unquantized bf16 LoRA training. Qwen2.5-Coder-1.5B-Instruct was not downloaded: its bf16 weights (3.09 GB) and its 4-bit variant (1.15 GB) did not fit the free disk above the team's floor, the bf16 weights would leave almost no GPU memory, and the quantized variants need runtimes outside the tested lock ([record](../../../experiments/models/2026-10-20-second-candidate-not-measured.json)).

## Training environment

- `python -m uv venv .venv-train --python 3.11`, then `python -m uv pip install --python .venv-train/Scripts/python.exe --torch-backend cu126 -r training/requirements-cuda.txt`.
- PyTorch 2.14.1+cu126 (the newest stable build on the official cu126 index; cu128 stops at 2.11.0), CUDA runtime 12.6, cuDNN 9.10.2, Transformers 5.20.2, PEFT 0.21.2, Accelerate 1.15.0, huggingface_hub 2.2.0. The driver (595.71) supports CUDA 13.2.
- The GPU reports compute capability 8.6 and bf16 support. uv hard-links the files from its cache, so the environment is stored once (about 4.3 GB).
- The core `.venv` never installs PyTorch; a test checks that importing the provider modules does not import `torch` or `transformers`.
- Weights are downloaded with `training/download_model.py` into `models/<name>/` at an exact revision, with Xet disabled so no second cache copy is created, and every LFS file is checked against its published SHA-256.

## T04 measurements

Run 2 is representative (2.2 GB of RAM free at the start); run 1 ran while the laptop was out of memory and is kept for comparison ([records](../../../experiments/models/README.md)).

- Load 17.6 s with a warm file cache (88.1 s for a cold first load, 76 to 116 s under memory pressure). The model process uses about 1.0 GB of GPU memory, 942 MiB of it allocated by PyTorch; the peak for a 910-token prompt plus 1,024 generated tokens is 993 MiB.
- Decode speed 13.8 to 26.1 tokens per second on the pilot prompts (median 24.5); 1,024 generated tokens after a 910-token prompt take 55.4 s (101 s under memory pressure).
- Greedy decoding is verified: over 64 steps the processed scores equal the raw logits and every chosen token is the argmax. The repository's `generation_config.json` enables sampling (temperature 0.7, top_p 0.8, top_k 20, repetition penalty 1.05); the worker replaces it at load time so only the requested settings apply. Outputs were byte-identical across the two runs and in repeated calls.
- With prompt refactor-v1 the base model returned only an `Explanation:` paragraph without a code block for all 8 pilot functions and the long input (0 of 9 parseable). Sampling with temperature 0.7 and top_p 0.8 over three seeds gave 1 parseable output in 24, an unchanged copy of the input that failed the rubric. The base model therefore produced no valid refactoring of any pilot function, which meets the revisit condition of ADR12; the untuned arms A and B would score no proposals on such inputs.
- Token lengths for inputs of exactly 3,000 characters: realistic code 769 tokens (prompt 910, with findings 1,027, reference completion 602); a digit-dense literal 2,896 tokens; Arabic text 1,461 tokens. The prompt adds 141 tokens. Byte-level BPE gives at most one token per UTF-8 byte, so the character limit does not bound tokens tightly.

Recommended per-role limits: refactoring `max_input_tokens` 2,048, `max_new_tokens` 1,024, `timeout_s` 120; analysis 2,048, 384, 60; review 4,096 (if its prompt carries both versions), 384 or 768 with a full correction, 90; `load_timeout_s` 180. The current refactoring default of 768 new tokens can cut off the longest realistic functions. The service should call `LocalProvider.warm_up()` at startup so the first run does not pay the model load.

## Provider design (T12)

`LocalProvider` (`src/refactor_ai/providers/local.py`) runs in the core environment and starts `model_worker.py` with the training environment's interpreter, `-I -X utf8 -u`, offline Hugging Face settings and no console window. The two processes exchange one JSON object per UTF-8 line (protocol version 1, documented in the worker). The worker announces its own PID (`starting`), loads the model once and replies `ready` with the identity it actually loaded, or `load_error`. The parent checks that identity against the configuration before serving.

- Configuration: `LocalProvider.from_config(path)` reads `configs/model.local.json` (keys in `configs/model.example.json`; unknown keys are rejected, the revision must be a 40-character commit, relative paths resolve against the config file). The worker also checks the revision recorded by the download metadata.
- Calls are serialized by a lock; a call that cannot get it within its `timeout_s` returns `busy`.
- `timeout_s` bounds each request. On timeout the parent terminates its own worker process and the next call starts a new one; model loading is bounded separately by `load_timeout_s`. On Windows the venv's `python.exe` is a launcher whose child is the real interpreter; terminating the launcher terminates that child (verified), and the parent also holds a handle to the PID the worker reported and terminates that process if it is still running (covered by a test that simulates such a process).
- Worker crashes, malformed lines, replies for another request, invalid fields and unknown error codes become `generation_error` and restart the worker; load failures, load timeouts and identity mismatches become `model_load_error`. The input-token limit is enforced by the worker (`input_too_long`); `max_new_tokens` is enforced by generation (`finish_reason="length"`).
- `use_adapter=true` without a configured adapter returns `unavailable` without starting a worker. A configured adapter that cannot load, has a checksum different from `adapter_sha256`, or has only zero LoRA B matrices is a `model_load_error`; the base model is never served instead. `use_adapter=false` with an adapter loaded runs PEFT's `disable_adapter()`, and its outputs were identical to the base model's.
- Decoding is exactly what `GenerationConfig` asks for: greedy at temperature 0, otherwise temperature and top_p sampling seeded with `seed`. Decoding never "cleans up" spaces, so code text is returned as generated.
- Error messages never contain host paths: configured paths and the home directory are replaced by placeholders before they reach run records.
- Tests: `tests/test_local_provider.py` (64 tests, no PyTorch) covers success, UTF-8 round trips, unencodable text, the token limits, timeout with kill and restart, crashes, five kinds of malformed output, load errors, load crashes, load timeouts, identity mismatches, adapter misuse, adapter identity and checksum, serialization without cross-talk, `busy`, closing, configuration validation, the real worker started without PyTorch, and the worker's protocol loop. `tests/test_local_provider_gpu.py` (8 tests, `REFACTOR_AI_GPU_TESTS=1`) passed on the laptop, including a 0.5 s timeout that stopped the GPU worker followed by a restart, and adapter switching with the pilot adapter ([record](../../../experiments/models/2026-10-20-local-provider-gpu-tests.json)).

## LoRA training (T05)

`training/train_lora.py` trains exactly the inference format: the prefix is the refactoring chat rendered by `model_worker.chat_prompt_text` (the function the worker uses) and is masked from the loss; the target is the completion followed by the token that closes an assistant turn in the chat template, read from the template and checked to be an end-of-sequence id (`<|im_end|>`, id 151645). Every record is compared with the template's own rendering of the full conversation before training. The script keeps the earlier protections (unresolved `CHOOSE` values, dataset validation, no test records in the Trainer, `--resume-from-checkpoint`) and adds unknown-key checks, a single-task and prompt-version check, bf16 when supported (fp16 otherwise) with LoRA weights in fp32, `--max-steps`, `--stop-after-steps`, `--check-data`, Windows-safe data loading and a run manifest with the fields of `experiments/run-template.json`.

Pilot results ([records](../../../experiments/training/README.md)): 16 steps on 16 pilot records took 20.8 s; training loss fell from 0.846 to 0.039 and validation loss from 0.433 to 0.080; peak memory was 2,167 MiB allocated and 3,728 MiB reserved. The 17.6 MB adapter (SHA-256 `cf74fcea...`) was reloaded in a fresh process through the worker's loading code: it changed every greedy output on 12 prompts, lowered the validation reference loss from 0.797 to 0.080, and with it 12 of 12 outputs parsed and 10 of 12 passed the rubric (none did without it). A run interrupted after step 8 and resumed from its checkpoint followed the uninterrupted run within the GPU's own run-to-run variation. One adapter output dropped a branch of the original function, a reminder that the rubric is not a behavior check.

Budget for the training run (T17), from the memory probe: about 3.2 GB of GPU memory is free with the desktop running, and beyond it the Windows driver spills into system RAM (one 1,280-token step without checkpointing took 28 s). With gradient checkpointing a 1,024-token record needs 2.8 GB and 0.87 s, so the budget is `max_length` 1,024 with checkpointing, batch size 1, at most 60 minutes per job, and `save_total_limit` 1. Curated records must fit in 1,024 tokens; a realistic 3,000-character function makes a record of about 1,512 tokens.

## Open issues

- The base model's format compliance on the pilot functions is 0 of 9 with greedy decoding (ADR12 revisit condition).
- Curated training records longer than 1,024 tokens do not fit the measured GPU budget.
- Performance numbers depend on how much memory other programs leave free; close GPU-heavy applications before a demonstration or training run.
