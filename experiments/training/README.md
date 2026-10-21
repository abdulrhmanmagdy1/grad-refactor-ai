# Training records

| Record | Content |
|---|---|
| [full-2026-10-21.json](full-2026-10-21.json) | T17: the adapter trained on the curated train split on Kaggle (run-template fields, loss history, per-epoch validation loss, checksums) |
| [full-2026-10-20-local-attempt1-failed.json](full-2026-10-20-local-attempt1-failed.json) | The first attempt of the same run on the laptop, which failed after 22 steps |
| [validation-selection-2026-10-20.json](validation-selection-2026-10-20.json) | T22: selection rule written before any comparison, the four-arm validation results (A 6, B 3, C 69, D 46 of 84 `proposal_ready`) and the decision to adopt the adapter for the refactoring role |
| [pilot-2026-10-20.json](pilot-2026-10-20.json) | T05 pilot summary in the fields of `experiments/run-template.json`, with the reload, resume and budget evidence |
| [pilot-2026-10-20-full.json](pilot-2026-10-20-full.json) | Uninterrupted 16-step pilot run (manifest written by `training/train_lora.py`) |
| [pilot-2026-10-20-interrupted.json](pilot-2026-10-20-interrupted.json) | Same pilot run stopped and checkpointed after step 8 (`--stop-after-steps 8`) |
| [pilot-2026-10-20-resumed.json](pilot-2026-10-20-resumed.json) | Resumed from that checkpoint for steps 9 to 16 |
| [pilot-2026-10-20-reload-check.json](pilot-2026-10-20-reload-check.json) | Pilot adapter reloaded in a fresh process (`training/check_adapter.py`) |
| [2026-10-20-training-memory-probe.json](2026-10-20-training-memory-probe.json) | Training memory and step time against sequence length on the RTX 2050 (`training/probe_training_memory.py`) |

## T17: adapter on the curated dataset

- Data: `datasets/guard_clauses/v1/records.jsonl` (SHA-256 `299b4f7f...`, prompt refactor-v2), 627 train and 84 validation records; the 88 test records never reached the Trainer. Every record matched the chat template's tokenization (longest 695 tokens, so none exceeded `max_length` 1,024).
- First attempt, on the laptop (2026-10-20): stopped after 22 of 237 steps with `CUBLAS_STATUS_EXECUTION_FAILED`. Windows logged a low-virtual-memory event naming the training process as the largest consumer (7.6 GB), so the laptop could not hold the run while the other workstreams were active. No checkpoint was saved.
- Second attempt, on Kaggle (2026-10-21, private kernel `grad-refactor-ai-train-11708b80`, bundle `46acfc0a...`): `configs/training.full.json` unchanged except the paths, precision fp32 (the T4 has no native bf16) and the time cap raised to 200 minutes. Kaggle's PyTorch 2.11.0+cu128 on Python 3.13 with the pinned Transformers 5.20.2 and PEFT 0.21.2; The coordinator made two fixes to the lane: the kernel removes Kaggle's torchao 0.10, which made PEFT 0.21 raise ImportError (needed for this run), and the reference runner now drops to an unprivileged user under root (needed for the evaluation kernels).
- The session exposed two T4 GPUs, and the Trainer split every batch across both, so the effective batch was 16 records per optimizer step (2 GPUs x 1 x 8 accumulation) instead of the 8 configured for one GPU: 120 optimizer steps over 3 epochs rather than about 237. This is inferred from the step count (40 steps per epoch for 627 records) and recorded in the run record.
- Result: 1,144 s of training (20.5 GPU minutes for the whole session). Training loss went from 0.689 at step 1 to 0.013 at step 120. Validation loss per epoch: 0.0361, 0.0388, 0.0360; epoch 3 (`checkpoint-120`) was selected by validation loss only. Peak PyTorch memory on cuda:0 was 5,970 MiB allocated and 11,652 MiB reserved (fp32).
- Adapter: `adapter_model.safetensors` 17,640,136 bytes, SHA-256 `dff9ae024f0314224d84759772918b59a3fa9037ecbf7ad7a7d43357e1b1d5d2`; `adapter_config.json` SHA-256 `a190572935f3c37d2f22fcca45024c4fb4f790e3f99802457abc2d3f38682571`. All 14 output files matched the kernel's checksums after download. The adapter stays in the ignored `runs/training/kaggle-grad-refactor-ai-train-11708b80/`.
- On the demonstration laptop (bf16), the LocalProvider loaded the base model plus this adapter in 18.6 to 25.2 s and passed all 8 real-GPU tests. On the 8 benchmark pilot functions the adapter's outputs all parsed and passed the rubric (6 identical to the reference rewrite), against 4 rubric passes with the adapter turned off; decoding with the adapter was about half as fast (median 7.2 against 14.6 tokens per second) ([record](../models/2026-10-21-laptop-adapter-check.json)). These are pilot functions without reference tests. On the 84 validation cases (Kaggle, float32) arm C reached 69 `proposal_ready` against 6 for arm A, so the adapter was adopted for the refactoring role ([selection record](validation-selection-2026-10-20.json)).

## T05 pilot

LoRA feasibility pilot on 2026-10-20 with Qwen/Qwen2.5-Coder-0.5B-Instruct (revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`) on the RTX 2050. The data are 22 pilot records written by the models workstream ([training/pilot/](../../training/pilot/functions.py)), not the curated dataset, so the pilot results do not measure refactoring quality.

### Results

- Setup: LoRA rank 8, alpha 16, dropout 0.05 on all seven attention and MLP projections (4,399,104 trainable parameters, 0.88%, in fp32), bf16 base, batch 1 with gradient accumulation 2, learning rate 2e-4 with linear decay, 16 optimizer steps (2 epochs over 16 train records), seed 42. The 4 validation records were evaluated every 4 steps; the 2 test records never reached the Trainer. Every record matched the chat template's tokenization; the target ends with `<|im_end|>` (id 151645).
- Run: 20.8 s. Training loss went from 0.846 at step 1 to 0.039 at step 16, and validation loss from 0.433 (step 4) to 0.080 (step 16). Peak PyTorch memory per step was 2,167 MiB allocated and 3,728 MiB reserved; total GPU use peaked at 3,896 of 4,096 MiB.
- Artifact: `adapter_model.safetensors`, 17,640,136 bytes, SHA-256 `cf74fcea961ea9e94ffc228711c90c2bc5ac29e943a2dd27774a3bfca82bb34f` (kept in the ignored `runs/training/pilot-full/adapter/`). Checkpoints (53,152,250 bytes each, mostly optimizer state) were deleted after their checksums were recorded.
- Reload in a fresh process, through the LocalProvider worker's loading code: on each of 12 prompts (4 validation, 8 benchmark) the largest change of a last-position logit was between 5.69 and 6.56 (the top-ranked first token stayed the same), and every greedy output changed. Teacher-forced loss on the 4 validation references was 0.080 with the adapter and 0.797 without it. With the adapter, 12 of 12 outputs parsed and 10 of 12 passed the rubric; without it, 1 of 12 parsed and none passed. With the adapter disabled, the 8 benchmark outputs were byte-identical to those of the separate base-model benchmark process.
- Resume: the run interrupted after step 8 and resumed from its checkpoint executed only steps 9 to 16 with the identical learning-rate schedule, and its losses stayed within 2e-3 of the uninterrupted run (final validation loss 0.0797 against 0.0801). Two fresh runs with the same seed already differ by up to 3e-3 from step 3 because some GPU kernels are not deterministic, so the adapters are not bitwise identical.
- Observed failures: one adapter output (pilot-18) kept the nesting and dropped the paid-but-not-shipped branch, a behavior change that the rubric did not name and reference tests would catch; another (bench-07) kept the original behavior but not the guard-clause shape. The pilot explanations state nesting depths, and the model repeated such numbers even when they were wrong.

### Budget for the training run (T17)

| Length (tokens) | Without gradient checkpointing | With gradient checkpointing |
|---|---|---|
| 512 | 2,773 MiB allocated, 0.43 s | 1,923 MiB, 0.76 s |
| 768 | 3,652 MiB, 1.25 s | 2,383 MiB, 0.67 s |
| 1,024 | 4,529 MiB, 2.30 s | 2,838 MiB (3,240 reserved), 0.87 s |
| 1,280 | 5,353 MiB, 28.0 s | 3,293 MiB, 1.61 s |
| 1,536 | 6,235 MiB, 9.58 s | 3,749 MiB, 1.97 s |
| 2,048 | out of memory | 4,665 MiB, 2.68 s |

About 3.2 GB of the 4 GB GPU is free with the desktop running; above that the Windows driver moves allocations into system RAM, which is slow and competes with the rest of the laptop. The measured budget is therefore gradient checkpointing on, `max_length` 1,024 tokens (about 0.9 s per record of that length), batch size 1, at most 60 minutes per job bounded with `max_steps`, and `save_total_limit` 1 (about 51 MB per checkpoint). Curated train and validation records must fit in 1,024 tokens: a realistic 3,000-character input makes a record of about 1,512 tokens. `train_lora.py --check-data` reports any record over the limit.
