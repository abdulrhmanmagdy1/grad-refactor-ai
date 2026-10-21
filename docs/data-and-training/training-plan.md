# Fine-tuning plan

One LoRA adapter for the refactoring role was trained on the curated train split on 2026-10-21 (T17, [record](../../experiments/training/full-2026-10-21.json)); it was adopted for the refactoring role on validation data only (T22: arm C 69 of 84 `proposal_ready` against arm A 6 of 84, [record](../../experiments/training/validation-selection-2026-10-20.json)). No model choice has been approved by the supervisor. The original model remains the comparison baseline (arms A and B). Facts below come from the records in `experiments/` (see the [workstream notes](../report/notes/model.md)).

## Candidate model and hardware

- Measured candidate: Qwen/Qwen2.5-Coder-0.5B-Instruct, revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`, Apache-2.0 (model card and LICENSE file reviewed at that revision). The tokenizer is loaded from the same snapshot.
- Demonstration laptop: NVIDIA GeForce RTX 2050 with 4 GB (0.2 to 1.1 GB used by the desktop and other applications during the measurements), compute capability 8.6 with bf16 support, 7.8 GB RAM, driver 595.71 ([hardware record](../../experiments/hardware/2026-10-20-training-environment.json)).
- A 1.5B candidate was not measured because of the measured disk and GPU-memory limits ([record](../../experiments/models/2026-10-20-second-candidate-not-measured.json)).
- Qwen Coder is one candidate, not a claim of best performance.

## Training path

PyTorch, Transformers (Trainer), PEFT and Accelerate in a separate environment, `.venv-train`, pinned in `training/requirements-cuda.txt` (the lock also contains Datasets, which the script does not import because a top-level `datasets/` directory exists in the repository); the core environment never installs them. The script trains unquantized LoRA adapters on a CUDA GPU with the LoRA weights in fp32 and the base in bf16 (only on GPUs with native bf16, compute capability 8.0 or newer), fp16 or fp32 (`precision`). QLoRA is not implemented. CPU training is not supported. Heavy runs can use Kaggle's free GPU through the private lane in [training/kaggle/](../../training/kaggle/README.md), which runs the same script on a verified code bundle.

Training text equals inference text: the masked prefix is the refactoring chat rendered by the same function the local provider's worker uses (`model_worker.chat_prompt_text`), and the target is the completion followed by the chat template's end-of-turn token (`<|im_end|>` for this model). Every record is checked against the template's rendering of the full conversation before training starts.

## Preparation and execution

Create the environment and fetch the model from the repository root (Windows paths; on Linux use `.venv-train/bin/python`):

```bash
python -m uv venv .venv-train --python 3.11
python -m uv pip install --python .venv-train/Scripts/python.exe --torch-backend cu126 -r training/requirements-cuda.txt
.venv-train/Scripts/python.exe training/download_model.py --repo-id Qwen/Qwen2.5-Coder-0.5B-Instruct --revision ea3f2471cf1b1f0db85067f1ef93848e38e88c25 --local-dir models/Qwen2.5-Coder-0.5B-Instruct
```

Validate the curated JSONL in the core environment, then check its tokenization against the context limit in the training environment:

```bash
uv run python scripts/validate_dataset.py datasets/guard_clauses/v1/records.jsonl
.venv-train/Scripts/python.exe -X utf8 training/train_lora.py --config configs/training.local.json --check-data
```

Copy `configs/training.example.json` to `configs/training.local.json` (ignored by Git), review every value and run:

```bash
.venv-train/Scripts/python.exe -X utf8 training/train_lora.py --config configs/training.local.json --record experiments/training/<run-id>.json
```

The script rejects unknown keys and unresolved `CHOOSE` values, invalid data, records of another task or prompt version, records longer than `max_length` (curate them; they are never truncated) and machines without CUDA. Only split `train` is trained on and `validation` evaluated; test records never reach the Trainer. `--max-steps` bounds smoke runs, `--resume-from-checkpoint DIR` continues a run and `--stop-after-steps N` simulates an interruption for resume tests. Checkpoints are kept with `save_total_limit` (1 by default) to save disk.

## Pilot, budget and the training run

The T05 pilot ([records](../../experiments/training/README.md)) trained, saved, reloaded and resumed an adapter on 22 pilot records and measured the laptop's budget: with gradient checkpointing a 1,024-token record needs 2.8 GB of GPU memory, while about 3.2 GB is free with the desktop running. `configs/training.full.json` therefore uses `max_length` 1,024, gradient checkpointing, batch size 1 with gradient accumulation 8, `save_total_limit` 1, best epoch by validation loss and a time cap.

T17 used that configuration on the 627 curated train records. On the laptop it stopped after 22 steps: Windows reported low virtual memory with the training process as the largest consumer (7.6 GB), because the GPU memory spilled into system RAM while the other workstreams were also running. The run then went to Kaggle unchanged except for the paths, fp32 precision (the T4 has no native bf16) and a longer time cap. It took 1,144 s; validation loss after the three epochs was 0.0361, 0.0388 and 0.0360, and epoch 3 was kept. Kaggle gave the session two T4 GPUs and the Trainer used both, so the effective batch was 16 records per optimizer step instead of 8 (120 steps instead of about 237); to repeat this run on a single GPU, set `gradient_accumulation_steps` to 16; to get the configured batch of 8 in a two-GPU session, expose only one GPU (`CUDA_VISIBLE_DEVICES=0`). The adapter's checksums are in the record; it is served on the laptop in bfloat16.

## Experiment record

Each run writes `<output_dir>/run-manifest.json` with the fields of `experiments/run-template.json` (run identifier, code SHA and dirty flag, dataset hash and split counts, model revision, dependency lock hash, package and CUDA versions, hardware, configuration, seed, duration, peak memory, validation metrics, adapter checksum) plus the loss history, per-step time and memory, trainable parameters and the end-of-turn token. `--record` copies it into `experiments/training/`.

## Selection and reporting

The selection rule was written before any comparison: adopt the adapter for the refactoring role if arm C has more `proposal_ready` cases than arm A on the full validation split, otherwise keep the base model. The four-arm validation evaluation (84 cases, the shared harness, Kaggle T4 in float32, protocol eval-v1 draft) gave A 6, B 3, C 69 and D 46 of 84, so the adapter was adopted; analysis and review keep the base model. Training loss and validation loss did not take part in this decision. All 15 arm C cases that were not accepted kept the guard-clause shape but failed reference tests, which is the main remaining failure pattern. The frozen test split is evaluated only after the protocol freeze; if the adapter does not help there, that outcome is reported without tuning on the test set.

## Free resources and storage

Colab may support interactive training experiments within its limits, but it is neither guaranteed compute nor permanent hosting. Save resumable artifacts within the available quota. Prefer a small adapter and metadata over redistributing the base model; the base weights are never committed (`models/` is ignored by Git).
