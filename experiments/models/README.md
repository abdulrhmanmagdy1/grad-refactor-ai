# Model benchmark records (T04)

Pilot measurements on the demonstration laptop (RTX 2050 4 GB, 7.8 GB RAM). They describe the pilot functions in [training/pilot/functions.py](../../training/pilot/functions.py) only and are not an evaluation. Raw outputs are kept in the JSON records.

| Record | Content |
|---|---|
| [2026-10-20-qwen2.5-coder-0.5b-instruct-benchmark-run2.json](2026-10-20-qwen2.5-coder-0.5b-instruct-benchmark-run2.json) | Benchmark run 2 (`training/benchmark_model.py`), the representative measurement |
| [2026-10-20-qwen2.5-coder-0.5b-instruct-benchmark-run1-under-memory-pressure.json](2026-10-20-qwen2.5-coder-0.5b-instruct-benchmark-run1-under-memory-pressure.json) | Benchmark run 1, taken while the laptop was out of memory |
| [2026-10-20-base-format-sampling-exploration.json](2026-10-20-base-format-sampling-exploration.json) | Exploratory sampling of the base model on the same prompts (`training/explore_base_format.py`), not the evaluation protocol |
| [2026-10-20-second-candidate-not-measured.json](2026-10-20-second-candidate-not-measured.json) | Why Qwen2.5-Coder-1.5B-Instruct (and its quantized variants) was not downloaded or measured |
| [2026-10-20-local-provider-gpu-tests.json](2026-10-20-local-provider-gpu-tests.json) | Results of the real-model LocalProvider tests |
| [2026-10-20-prompt-format-selection.md](2026-10-20-prompt-format-selection.md) | Validation-only selection of the refactoring prompt format (v1 to v4) on 24 validation records, with raw outputs in the matching JSON |
| [2026-10-20-prompt-format-token-lengths.json](2026-10-20-prompt-format-token-lengths.json) | Curated train and validation record lengths under the formats |
| [2026-10-21-gguf-3b-feasibility.json](2026-10-21-gguf-3b-feasibility.json) | Qwen2.5-Coder-3B-Instruct (GGUF q4_k_m, llama.cpp) on the laptop for the project review mode: load time, speed, GPU memory and one unconstrained bug-review attempt |

## Candidate

Qwen/Qwen2.5-Coder-0.5B-Instruct, revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`. License Apache-2.0, read from the model card metadata and the LICENSE file at that revision ("Copyright 2024 Alibaba Cloud"). `model.safetensors` is 988,097,824 bytes with SHA-256 `f9523886352217ded3aeeef552b381af79d568c6d49a4b9e423288cea56b0a44`, which matched the published LFS checksum after the download (379.5 s, `training/download_model.py`, Xet disabled, no second cache copy). No second candidate was measured: the bf16 1.5B weights (3.09 GB) and even its 4-bit variant (1.15 GB) did not fit the free disk above the team's floor, and the coordinator ruled out further downloads.

## Conditions

Run 1 (13:04) started with 0.3 GB of RAM available while five workstreams shared the laptop; its load time and speed describe an overloaded machine. Run 2 (14:58) started with 2.2 GB of RAM available and is the representative measurement. Both runs produced byte-identical outputs on all 9 prompts.

## Results

| Measurement | Run 2 | Run 1 (memory pressure) |
|---|---|---|
| Model load, including importing PyTorch | 17.6 s (warm file cache) | 115.5 s |
| GPU memory of the model process | about 1,019 MiB | about 1,080 MiB |
| PyTorch allocated after load | 942 MiB | 942 MiB |
| Peak PyTorch allocation per pilot call | 962 MiB | 962 MiB |
| Pilot calls: generation time for 80 to 137 tokens | 3.1 to 9.1 s (median 5.0 s) | 5.5 to 12.5 s |
| Pilot calls: decode speed | 13.8 to 26.1 tokens/s (median 24.5) | 9.5 to 14.7 tokens/s |
| Prompt processing (189 to 241 tokens) | 35 to 85 ms | 47 to 504 ms |
| 1,024 forced new tokens after a 910-token prompt | 55.4 s (18.5 tokens/s), peak 993 MiB allocated | 100.8 s (10.2 tokens/s) |
| Greedy decoding check (64 steps) | processed scores equal raw logits, every token is the argmax, repository sampling defaults removed | same |
| Output format | 0 of 8 pilot outputs and 0 of 1 long input contained a code block | same outputs |

All nine base-model outputs start with `Explanation:`, contain no code fence and no `def`, and end with the end-of-turn token (369 to 626 characters); the ones read in full describe the original function instead of rewriting it. `parse_refactor_output` reported `no_code_block` for all of them, so no rubric could be computed.

To check whether this is specific to greedy decoding, the same 8 prompts were sampled with the model card's temperature 0.7 and top_p 0.8 (the provider contract has no top_k or repetition penalty) for seeds 1, 2 and 3. Of the 24 outputs, 23 again had no code block; the one that parsed (bench-05, seed 1) returned the original function unchanged (nesting depth 3 to 3, no guard clause) and then began repeating the prompt, so it failed the rubric. Across both decodings the base model produced no valid refactoring of any pilot function. This meets the revisit condition recorded for ADR12 and is reported to the coordinator. After the 16-step pilot LoRA run, the same model parsed on all 12 pilot prompts it was checked on ([reload check](../training/pilot-2026-10-20-reload-check.json)).

## Token lengths of the prompt

| Input (exactly 3,000 characters) | Lines | UTF-8 bytes | Code tokens | Prompt tokens | With findings | Reference completion tokens |
|---|---|---|---|---|---|---|
| Realistic ASCII code | 55 | 3,000 | 769 | 910 | 1,027 | 602 |
| Digit-dense literal | 8 | 3,000 | 2,896 | 3,037 | 3,076 | 2,911 |
| Arabic text in a string | 8 | 5,378 | 1,461 | 1,602 | 1,641 | 1,476 |

The refactoring prompt adds 141 tokens to the code (system message, instructions, format and chat markup). Byte-level BPE tokens cover at least one byte each, so code tokens never exceed the UTF-8 byte count; the 3,000-character limit alone does not bound tokens tightly. Structured outputs measured as JSON from the static findings of the pilot functions: analysis 72 to 188 tokens, a review with a full suggested correction 91 to 143 tokens.

## Recommended limits

| Role | max_input_tokens | max_new_tokens | timeout_s | Basis |
|---|---|---|---|---|
| Refactoring | 2,048 | 1,024 | 120 | Largest realistic prompt 1,027 tokens; reference completion 602 tokens and the input's own code 769 tokens; 1,024 tokens took 55 s normally and 101 s under memory pressure |
| Analysis | 2,048 | 384 | 60 | Static-findings JSON 72 to 188 tokens; 384 tokens take at most about 38 s at the slowest measured rate |
| Review | 4,096 if the prompt carries both versions, else 2,048 | 384, or 768 when a full corrected function is requested | 90 | Two copies of the largest realistic function are about 1,540 code tokens; a correction repeats the function (up to about 600 tokens) |
| Worker start | | | `load_timeout_s` 180 | Loads of 17.5 to 19.9 s warm, 88.1 s cold, 76 to 116 s under memory pressure |

The current `WorkflowSettings` default of 768 new tokens for the refactoring role can cut off the longest realistic functions. Inputs dense in digits or non-ASCII text can exceed 2,048 prompt tokens and then fail as `input_too_long` before any generation. The API should call `LocalProvider.warm_up()` at startup so the first run does not pay the model load.
