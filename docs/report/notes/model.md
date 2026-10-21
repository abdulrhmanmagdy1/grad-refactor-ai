# Models and training notes

Workstream: models and training (owner Abdelrahman Adel). Tasks: T04 model benchmark, T05 LoRA feasibility pilot, T12 local model provider, T17 training run, T22 validation-only model selection (with the prompt-format study before it). Written on 2026-10-20 and updated on 2026-10-21 from the records under `experiments/` and the tests. The pilot functions in `training/pilot/functions.py` are pilot material written for this workstream, not the curated dataset, and nothing in these notes is an evaluation result.

## Status on 2026-10-21

| Item | Status |
|---|---|
| Training environment | Installed in `.venv-train` and locked in `training/requirements-cuda.txt` |
| T04 benchmark | Done for Qwen2.5-Coder-0.5B-Instruct (two runs); the 1.5B candidate was not measured because of the disk limit |
| Prompt format | refactor-v2 (code first) selected on 24 validation records before any training |
| T05 LoRA pilot | Done: trained, saved, reloaded in a fresh process, interrupted and resumed; training budget measured |
| T17 training run | Done on Kaggle after a failed attempt on the laptop |
| T22 selection | Adapter adopted for the refactoring role (arm C 69 of 84 `proposal_ready` against arm A 6 of 84 on validation) |
| T12 local provider | Implemented and hardened after review; 80 core tests (plus 4 for the training helpers) pass without PyTorch; 8 real-GPU tests pass on the laptop with the trained adapter |

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
- With prompt refactor-v1 the base model returned only an `Explanation:` paragraph without a code block for all 8 pilot functions and the long input (0 of 9 parseable). Sampling with temperature 0.7 and top_p 0.8 over three seeds gave 1 parseable output in 24, an unchanged copy of the input that failed the rubric. This met the revisit condition of ADR12 and led to the prompt-format study below.
- Token lengths for inputs of exactly 3,000 characters: realistic code 769 tokens (prompt 910, with findings 1,027, reference completion 602); a digit-dense literal 2,896 tokens; Arabic text 1,461 tokens. The prompt adds 141 tokens. Byte-level BPE gives at most one token per UTF-8 byte, so the character limit does not bound tokens tightly.

Recommended per-role limits: refactoring `max_input_tokens` 2,048, `max_new_tokens` 1,024, `timeout_s` 120; analysis 2,048, 384, 60; review 4,096 (if its prompt carries both versions), 384 or 768 with a full correction, 90; `load_timeout_s` 180. The current refactoring default of 768 new tokens can cut off the longest realistic functions. The service should call `LocalProvider.warm_up()` at startup so the first run does not pay the model load.

## Prompt format

A validation-only study ([record](../../../experiments/models/2026-10-20-prompt-format-selection.md)) compared four refactoring-prompt formats on 24 validation records with the base model, with the selection rule stated first (most records passing syntax, rubric and reference tests; ties by parse rate, then shorter prompt). Putting the fenced code first and the `Explanation:` line after it raised parsing from 2 of 24 to 24 of 24; the base model then mostly returned the input unchanged (2 of 24 passed everything). The code-first format became refactor-v2, and the curated records were regenerated in it (no record exceeds 1,024 tokens).

## Provider design (T12)

`LocalProvider` (`src/refactor_ai/providers/local.py`) runs in the core environment and starts `model_worker.py` with the training environment's interpreter, `-I -X utf8 -u`, offline Hugging Face settings and no console window. The two processes exchange one JSON object per UTF-8 line (protocol version 1, documented in the worker). The worker announces its own PID (`starting`), loads the model once and replies `ready` with the identity it actually loaded, or `load_error`. The parent checks that identity against the configuration before serving.

- Configuration: `LocalProvider.from_config(path)` reads `configs/model.local.json` (keys in `configs/model.example.json`; unknown keys are rejected, the revision must be a 40-character commit, relative paths resolve against the config file). The worker also checks the revision recorded by the download metadata.
- Calls are serialized by a lock; a call that cannot get it within its `timeout_s` returns `busy`.
- `timeout_s` bounds each request. On timeout the parent terminates its own worker process and the next call starts a new one; model loading is bounded separately by `load_timeout_s`. On Windows the venv's `python.exe` is a launcher whose child is the real interpreter; terminating the launcher terminates that child (verified), and the parent also holds a handle to the PID the worker reported and terminates that process if it is still running (covered by a test that simulates such a process).
- Worker crashes, malformed lines, replies for another request, invalid fields and unknown error codes become `generation_error` and restart the worker; load failures, load timeouts and identity mismatches become `model_load_error`. The input-token limit is enforced by the worker (`input_too_long`); `max_new_tokens` is enforced by generation (`finish_reason="length"`).
- `use_adapter=true` without a configured adapter returns `unavailable` without starting a worker. A configured adapter that cannot load, has a weights checksum different from `adapter_sha256` or a config checksum different from `adapter_config_sha256` (the config sets the LoRA scaling), or has only zero LoRA B matrices is a `model_load_error`; the base model is never served instead. Results report the weights checksum in `ModelReference.adapter_sha256`; `info()` shows both. `use_adapter=false` with an adapter loaded runs PEFT's `disable_adapter()`, and its outputs were identical to the base model's.
- Decoding is exactly what `GenerationConfig` asks for: greedy at temperature 0, otherwise temperature and top_p sampling seeded with `seed`. Decoding never "cleans up" spaces, so code text is returned as generated.
- Error messages never contain host paths: configured paths and the home directory are replaced by placeholders before they reach run records.
- Review fixes (2026-10-21), each with a regression test that fails when the fix is reverted: `close()` now stops a worker that is still loading the model (an API shutdown during warm-up left it running); config paths are made absolute without following symbolic links, so a symlinked venv interpreter stays in its environment; CUDA, cuBLAS and cuDNN errors are fatal for the worker, which replies, exits and is restarted on the next call instead of failing every later call; an error reply whose `code` is not a string is a protocol error instead of an exception; the adapter config is checksummed as well; and the training helpers return `None` when `nvidia-smi` or `git` hangs.
- Tests: `tests/test_local_provider.py` (80 tests, no PyTorch) covers success, UTF-8 round trips, unencodable text, the token limits, timeout with kill and restart, crashes, five kinds of malformed output, load errors, load crashes, load timeouts, identity mismatches, adapter misuse, adapter identity and checksum, serialization without cross-talk, `busy`, closing, configuration validation, the real worker started without PyTorch, and the worker's protocol loop. `tests/test_local_provider_gpu.py` (8 tests, `REFACTOR_AI_GPU_TESTS=1`) passed on the laptop, including a 0.5 s timeout that stopped the GPU worker followed by a restart, and adapter switching, first with the pilot adapter and on 2026-10-21 with the trained adapter in bfloat16 ([record](../../../experiments/models/2026-10-20-local-provider-gpu-tests.json)).

## LoRA training (T05)

`training/train_lora.py` trains exactly the inference format: the prefix is the refactoring chat rendered by `model_worker.chat_prompt_text` (the function the worker uses) and is masked from the loss; the target is the completion followed by the token that closes an assistant turn in the chat template, read from the template and checked to be an end-of-sequence id (`<|im_end|>`, id 151645). Every record is compared with the template's own rendering of the full conversation before training. The script keeps the earlier protections (unresolved `CHOOSE` values, dataset validation, no test records in the Trainer, `--resume-from-checkpoint`) and adds unknown-key checks, a single-task and prompt-version check, bf16 when supported (fp16 otherwise) with LoRA weights in fp32, `--max-steps`, `--stop-after-steps`, `--check-data`, Windows-safe data loading and a run manifest with the fields of `experiments/run-template.json`.

Pilot results ([records](../../../experiments/training/README.md)): 16 steps on 16 pilot records took 20.8 s; training loss fell from 0.846 to 0.039 and validation loss from 0.433 to 0.080; peak memory was 2,167 MiB allocated and 3,728 MiB reserved. The 17.6 MB adapter (SHA-256 `cf74fcea...`) was reloaded in a fresh process through the worker's loading code: it changed every greedy output on 12 prompts, lowered the validation reference loss from 0.797 to 0.080, and with it 12 of 12 outputs parsed and 10 of 12 passed the rubric (none did without it). A run interrupted after step 8 and resumed from its checkpoint followed the uninterrupted run within the GPU's own run-to-run variation. One adapter output dropped a branch of the original function, a reminder that the rubric is not a behavior check.

Budget for the training run (T17), from the memory probe: about 3.2 GB of GPU memory is free with the desktop running, and beyond it the Windows driver spills into system RAM (one 1,280-token step without checkpointing took 28 s). With gradient checkpointing a 1,024-token record needs 2.8 GB and 0.87 s, so the budget is `max_length` 1,024 with checkpointing, batch size 1, at most 60 minutes per job, and `save_total_limit` 1. Curated records must fit in 1,024 tokens; a realistic 3,000-character function makes a record of about 1,512 tokens.

## Training run (T17) and the Kaggle lane

`configs/training.full.json` (rank 8, alpha 16, the seven projections, learning rate 2e-4 with cosine decay and 12 warmup steps, 3 epochs, `max_length` 1,024 with gradient checkpointing, best epoch by validation loss) first ran on the laptop and stopped after 22 steps with `CUBLAS_STATUS_EXECUTION_FAILED`: Windows logged a low-virtual-memory event naming the training process as the largest consumer (7.6 GB), as the GPU memory spilled into system RAM while the other workstreams were running ([record](../../../experiments/training/full-2026-10-20-local-attempt1-failed.json)). The user then moved heavy GPU runs to Kaggle's free GPU.

The private Kaggle lane ([training/kaggle/](../../../training/kaggle/README.md)) uploads a checksummed code bundle as a private dataset, pushes private script kernels that verify the bundle, install the pinned libraries next to Kaggle's own PyTorch, download the model at the pinned revision and check its SHA-256, and brings the outputs back with per-file checksums. Two fixes by the coordinator made it work: the kernel removes Kaggle's torchao 0.10, which made PEFT 0.21 fail to import, and the reference runner drops to an unprivileged user under root.

On Kaggle (two T4 GPUs, fp32 because the T4 has no native bf16) the run took 1,144 s, 20.5 GPU minutes in all. The Trainer used both GPUs, so the effective batch was 16 records per optimizer step and the run had 120 steps instead of about 237. Validation loss after the three epochs was 0.0361, 0.0388 and 0.0360, and epoch 3 was kept. The adapter's weights SHA-256 is `dff9ae024f0314224d84759772918b59a3fa9037ecbf7ad7a7d43357e1b1d5d2` and its config SHA-256 `a190572935f3c37d2f22fcca45024c4fb4f790e3f99802457abc2d3f38682571` ([record](../../../experiments/training/full-2026-10-21.json)).

## Validation-only selection (T22)

The rule, written before any comparison, adopts the adapter if arm C has more `proposal_ready` cases than arm A on the full validation split. The four arms ran on the 84 validation cases with the shared harness on Kaggle (float32, 76.2 GPU minutes): A 6/84, B 3/84, C 69/84, D 46/84 `proposal_ready`; rubric pass A 17, B 16, C 84, D 84; reference tests pass A 66, B 69, C 69, D 69. On the same cases 65 were accepted only by C and 2 only by A. The adapter was therefore adopted for the refactoring role ([record](../../../experiments/training/validation-selection-2026-10-20.json)), and `configs/model.local.json` points at it on the laptop.

Failure patterns: all 15 arm C cases that were not accepted kept the guard-clause shape and failed reference tests, so the adapter sometimes changes behavior (five of the twelve validation families); arm D accepted fewer cases than C mainly because the base model's reviews were often unparseable (27 review errors, 23 uncertain). On the laptop, in bfloat16, the adapter decodes at about half the speed of the base model (median 7.2 against 14.6 tokens per second on pilot functions), because the LoRA layers are applied separately on every projection.

## Open issues

- The adapter changes behavior on some cases that pass the rubric (15 of 84 on validation); only reference tests catch them.
- Kaggle results were computed in float32 on a T4, while the laptop serves the adapter in bfloat16.
- The trained adapter used an effective batch of 16 because the Kaggle session exposed two GPUs; reruns must pin the GPU count to reproduce it.
- Curated training records longer than 1,024 tokens do not fit the laptop's measured GPU budget.
- Performance numbers depend on how much memory other programs leave free; close GPU-heavy applications before a demonstration or training run.
