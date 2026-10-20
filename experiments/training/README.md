# Training records (T05 pilot)

LoRA feasibility pilot on 2026-10-20 with Qwen/Qwen2.5-Coder-0.5B-Instruct (revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`) on the RTX 2050. The data are 22 pilot records written by the models workstream ([training/pilot/](../../training/pilot/functions.py)), not the curated dataset, so nothing here measures refactoring quality.

| Record | Content |
|---|---|
| [pilot-2026-10-20.json](pilot-2026-10-20.json) | Summary in the fields of `experiments/run-template.json`, with the reload, resume and budget evidence |
| [pilot-2026-10-20-full.json](pilot-2026-10-20-full.json) | Uninterrupted 16-step run (manifest written by `training/train_lora.py`) |
| [pilot-2026-10-20-interrupted.json](pilot-2026-10-20-interrupted.json) | Same run stopped and checkpointed after step 8 (`--stop-after-steps 8`) |
| [pilot-2026-10-20-resumed.json](pilot-2026-10-20-resumed.json) | Resumed from that checkpoint for steps 9 to 16 |
| [pilot-2026-10-20-reload-check.json](pilot-2026-10-20-reload-check.json) | Adapter reloaded in a fresh process (`training/check_adapter.py`) |
| [2026-10-20-training-memory-probe.json](2026-10-20-training-memory-probe.json) | Training memory and step time against sequence length (`training/probe_training_memory.py`) |

## Results

- Setup: LoRA rank 8, alpha 16, dropout 0.05 on all seven attention and MLP projections (4,399,104 trainable parameters, 0.88%, in fp32), bf16 base, batch 1 with gradient accumulation 2, learning rate 2e-4 with linear decay, 16 optimizer steps (2 epochs over 16 train records), seed 42. The 4 validation records were evaluated every 4 steps; the 2 test records never reached the Trainer. Every record matched the chat template's tokenization; the target ends with `<|im_end|>` (id 151645).
- Run: 20.8 s. Training loss went from 0.846 at step 1 to 0.039 at step 16, and validation loss from 0.433 (step 4) to 0.080 (step 16). Peak PyTorch memory per step was 2,167 MiB allocated and 3,728 MiB reserved; total GPU use peaked at 3,896 of 4,096 MiB.
- Artifact: `adapter_model.safetensors`, 17,640,136 bytes, SHA-256 `cf74fcea961ea9e94ffc228711c90c2bc5ac29e943a2dd27774a3bfca82bb34f` (kept in the ignored `runs/training/pilot-full/adapter/`). Checkpoints (53,152,250 bytes each, mostly optimizer state) were deleted after their checksums were recorded.
- Reload in a fresh process, through the LocalProvider worker's loading code: on each of 12 prompts (4 validation, 8 benchmark) the largest change of a last-position logit was between 5.69 and 6.56 (the top-ranked first token stayed the same), and every greedy output changed. Teacher-forced loss on the 4 validation references was 0.080 with the adapter and 0.797 without it. With the adapter, 12 of 12 outputs parsed and 10 of 12 passed the rubric; without it, 1 of 12 parsed and none passed. With the adapter disabled, the 8 benchmark outputs were byte-identical to those of the separate base-model benchmark process.
- Resume: the run interrupted after step 8 and resumed from its checkpoint executed only steps 9 to 16 with the identical learning-rate schedule, and its losses stayed within 2e-3 of the uninterrupted run (final validation loss 0.0797 against 0.0801). Two fresh runs with the same seed already differ by up to 3e-3 from step 3 because some GPU kernels are not deterministic, so the adapters are not bitwise identical.
- Observed failures: one adapter output (pilot-18) kept the nesting and dropped the paid-but-not-shipped branch, a behavior change that the rubric did not name and reference tests would catch; another (bench-07) kept the original behavior but not the guard-clause shape. The pilot explanations state nesting depths, and the model repeated such numbers even when they were wrong.

## Budget for the training run (T17)

| Length (tokens) | Without gradient checkpointing | With gradient checkpointing |
|---|---|---|
| 512 | 2,773 MiB allocated, 0.43 s | 1,923 MiB, 0.76 s |
| 768 | 3,652 MiB, 1.25 s | 2,383 MiB, 0.67 s |
| 1,024 | 4,529 MiB, 2.30 s | 2,838 MiB (3,240 reserved), 0.87 s |
| 1,280 | 5,353 MiB, 28.0 s | 3,293 MiB, 1.61 s |
| 1,536 | 6,235 MiB, 9.58 s | 3,749 MiB, 1.97 s |
| 2,048 | out of memory | 4,665 MiB, 2.68 s |

About 3.2 GB of the 4 GB GPU is free with the desktop running; above that the Windows driver moves allocations into system RAM, which is slow and competes with the rest of the laptop. The measured budget is therefore gradient checkpointing on, `max_length` 1,024 tokens (about 0.9 s per record of that length), batch size 1, at most 60 minutes per job bounded with `max_steps`, and `save_total_limit` 1 (about 51 MB per checkpoint). Curated train and validation records must fit in 1,024 tokens: a realistic 3,000-character input makes a record of about 1,512 tokens. `train_lora.py --check-data` reports any record over the limit.
