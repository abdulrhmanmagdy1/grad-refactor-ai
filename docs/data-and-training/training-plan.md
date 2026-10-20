# Fine-tuning plan

No adapter has been trained on the curated dataset yet, and no model choice has been approved by the supervisor. The first fine-tuning target is the refactoring role; the original model remains the comparison baseline (arms A and B). Facts below come from the records in `experiments/` (see the [workstream notes](../report/notes/model.md)).

## Candidate model and hardware

- Measured candidate: Qwen/Qwen2.5-Coder-0.5B-Instruct, revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`, Apache-2.0 (model card and LICENSE file reviewed at that revision). The tokenizer is loaded from the same snapshot.
- Demonstration laptop: NVIDIA GeForce RTX 2050 with 4 GB (0.2 to 1.1 GB used by the desktop and other applications during the measurements), compute capability 8.6 with bf16 support, 7.8 GB RAM, driver 595.71 ([hardware record](../../experiments/hardware/2026-10-20-training-environment.json)).
- A 1.5B candidate was not measured because of the measured disk and GPU-memory limits ([record](../../experiments/models/2026-10-20-second-candidate-not-measured.json)).
- Qwen Coder is one candidate, not a claim of best performance.

## Training path

PyTorch, Transformers (Trainer), PEFT and Accelerate in a separate environment, `.venv-train`, pinned in `training/requirements-cuda.txt` (the lock also contains Datasets, which the script does not import because a top-level `datasets/` directory exists in the repository); the core environment never installs them. The script trains unquantized LoRA adapters on a CUDA GPU in bf16 (fp16 when bf16 is unsupported) with the LoRA weights in fp32. QLoRA is not implemented. CPU training is not supported.

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

## Pilot and budget

The T05 pilot ([records](../../experiments/training/README.md)) used 22 pilot records built by `training/pilot/build_pilot_data.py` (16 train, 4 validation, 2 test that never reach the Trainer) with `configs/training.pilot.json`: LoRA rank 8, alpha 16, dropout 0.05 on all seven projections, bf16 with fp32 adapter weights, 16 steps. The run took 20.8 s, the training loss fell from 0.846 to 0.039 and the validation loss from 0.433 to 0.080, and the 17.6 MB adapter was reloaded in a fresh process through the LocalProvider worker, where it changed every greedy output and made 12 of 12 pilot outputs parse. A run interrupted after step 8 resumed from its checkpoint with the same learning-rate schedule and stayed within the GPU's run-to-run variation (up to 3e-3 in loss).

The budget for the training run comes from the memory probe: with gradient checkpointing a 1,024-token record needs 2.8 GB of GPU memory and 0.87 s per step, while about 3.2 GB is free with the desktop running; longer records, or 768 tokens and more without checkpointing, spill into system RAM on Windows and slow down sharply. Use `max_length` 1,024 with `gradient_checkpointing` true (the values in `configs/training.example.json`), batch size 1, `save_total_limit` 1 (about 51 MB per checkpoint) and at most 60 minutes per job, bounded with `max_steps`. Curated records must fit in 1,024 tokens; `--check-data` lists any that do not.

## Experiment record

Each run writes `<output_dir>/run-manifest.json` with the fields of `experiments/run-template.json` (run identifier, code SHA and dirty flag, dataset hash and split counts, model revision, dependency lock hash, package and CUDA versions, hardware, configuration, seed, duration, peak memory, validation metrics, adapter checksum) plus the loss history, per-step time and memory, trainable parameters and the end-of-turn token. `--record` copies it into `experiments/training/`.

## Selection and reporting

Choose a candidate with declared validation metrics, then evaluate the agreed test set. Training loss alone does not measure successful refactoring. If fine-tuning does not improve results, investigate and report that outcome without tuning on the test set.

## Free resources and storage

Colab may support interactive training experiments within its limits, but it is neither guaranteed compute nor permanent hosting. Save resumable artifacts within the available quota. Prefer a small adapter and metadata over redistributing the base model; the base weights are never committed (`models/` is ignored by Git).
