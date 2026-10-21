# Kaggle lane

The demonstration laptop has a 4 GB GPU and 7.8 GB of RAM shared with the desktop and the other workstreams. On 2026-10-20 the full LoRA training run failed there after 22 steps when the laptop ran out of virtual memory ([record](../../experiments/training/full-2026-10-20-local-attempt1-failed.json)), and the user directed heavy GPU runs to Kaggle's free GPU. This lane runs the training and the validation evaluations on Kaggle with the repository's own scripts and brings the results back with checksums. Everything on Kaggle is **private**: one private dataset holds the code bundle, and every job is a private script kernel.

## Files

| File | Purpose |
|---|---|
| [lane.py](lane.py) | Host side: `bundle`, `upload`, `push`, `wait`, `fetch` |
| [kernel_template.py](kernel_template.py) | The script each kernel runs; `lane.py push` inserts the job description |
| [bundle-state.json](bundle-state.json) | SHA-256 and time of the bundle last uploaded (so unchanged bundles are not uploaded again) |

Generated files stay under `runs/kaggle/` (ignored by Git): the staged bundle, one folder per pushed kernel, and `submissions.jsonl`, an append-only log of every bundle, upload, push, status change and fetch.

## Commands

Run from the repository root with the system Python that has uv (the lane itself uses only the standard library). The Kaggle CLI 2.2.4 runs through `python -m uv tool run --from kaggle kaggle`, authenticated by `~/.kaggle/access_token`; the token is never printed.

```bash
python training/kaggle/lane.py bundle [--adapter runs/training/<run>/adapter]
python training/kaggle/lane.py upload
python training/kaggle/lane.py push --job smoke --arms A --case-ids gc1-blood-pressure-01 gc1-blood-pressure-02 --timeout-min 60
python training/kaggle/lane.py push --job train --run-id full-2026-10-20 --timeout-min 180
python training/kaggle/lane.py push --job eval --arms A,B,C,D --adapter-id <id> --adapter-sha256 <sha> --timeout-min 600
python training/kaggle/lane.py wait <slug>
python training/kaggle/lane.py fetch <slug>
```

- `bundle` packs `src/refactor_ai`, `scripts/`, `datasets/guard_clauses/v1/` (records, manifest, metadata, notice), `configs/training.full.json` and `configs/model.example.json`, `training/train_lora.py`, `training/common.py`, `training/requirements-cuda.txt`, the kernel template, `pyproject.toml`, `uv.lock` and, with `--adapter`, the adapter files (`training_args.bin`, a pickle, is left out). It writes a deterministic `bundle.zip` and `bundle-manifest.json` (SHA-256 of every file, the bundle SHA-256 over that list, the Git HEAD and whether the working tree had uncommitted changes).
- `upload` creates the private dataset `abdelrhmanadel208/grad-refactor-ai-bundle` the first time and adds a version only when the bundle SHA-256 differs from `bundle-state.json`, then waits until Kaggle reports the dataset `ready`.
- `push` writes `runs/kaggle/kernels/<slug>/` (the kernel script with the job inserted and `kernel-metadata.json`: private, GPU, internet, machine shape `NvidiaTeslaT4`, the bundle dataset as input) and pushes it with a session limit. The slug is `grad-refactor-ai-<job>-<hash of the job>`. The job pins the bundle SHA-256, and the kernel refuses a different bundle.
- `wait` polls the kernel status every minute until it is complete or failed.
- `fetch` downloads the kernel output into `runs/evaluation/kaggle-<slug>/` (or `runs/training/kaggle-<slug>/` for training) and checks every file against the kernel's `outputs-manifest.json`.

## What a kernel does

1. Records the hardware (`hardware.json`: GPU name, memory, driver, compute capability, PyTorch and CUDA versions, CPU count, RAM, Python).
2. Finds the bundle (Kaggle may extract the zip), copies it to `/tmp/grad/repo` and verifies every file against the manifest and the bundle SHA-256 named by the job.
3. Installs the pinned `transformers`, `peft`, `accelerate`, `safetensors`, `tokenizers` and `huggingface-hub` versions from `training/requirements-cuda.txt` and `pydantic==2.14.1` from `uv.lock`, keeping Kaggle's own PyTorch (a constraint file stops pip from changing it), and confirms the versions with `python -I`, the way the model worker starts.
4. Downloads Qwen/Qwen2.5-Coder-0.5B-Instruct at revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25` and checks the SHA-256 of `model.safetensors`.
5. Runs the job:
   - `train`: `training/train_lora.py` with `configs/training.full.json`, with only the paths changed and the precision set for the GPU. The adapter and the run manifest are kept; checkpoints are deleted after their checksums are recorded.
   - `eval` and `smoke`: `scripts/evaluate.py --split validation --provider local` with a model config that points the LocalProvider at `sys.executable`, the downloaded model and the bundled adapter, followed by `scripts/report_evaluation.py`.
6. Writes `status.json` (every step with its duration and any error), the logs and `outputs-manifest.json`, and exits with an error when a step failed.

Evaluation jobs use the validation split. The single final evaluation of the frozen test split is the only exception: `lane.py push --job eval --split test --i-confirm-frozen-test --protocol-version <version>` refuses to push unless the uploaded bundle was built from a clean, committed tree, the kernel refuses a dirty bundle again, and `scripts/evaluate.py` additionally requires the frozen protocol record (`experiments/evaluation/protocol-freeze.json`, included in the bundle) and matching split hashes. Kaggle has no Git, so the evaluation records' `code_sha` is empty there; the bundle manifest's `git_head` (with `git_dirty: false`) in `status.json` identifies the code, linked to every record by its `evaluation_id`.

## Precision on Kaggle

The T4 (compute capability 7.5) has no native bf16, and recent PyTorch reports emulated bf16 as supported, which is slow. fp16 risks overflow in Qwen2 models. On a GPU below compute capability 8.0 the kernel therefore trains in fp32 (no mixed precision) and runs inference in float32; on a GPU with native bf16 it uses bf16 as on the laptop. The precision used is in every run manifest and model config, and results computed in float32 on Kaggle can differ slightly from bf16 inference on the laptop.

## Evaluation records and hardware

The evaluation record schema belongs to the data workstream and does not have a hardware field. The hardware of a Kaggle evaluation is in `hardware.json` and in `run.json` (provider device) next to the records, linked to every record by its `evaluation_id`.
