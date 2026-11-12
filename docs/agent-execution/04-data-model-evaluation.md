# 04 — Data, model and evaluation

Condensed operational brief; the authoritative documents are the
[data plan](../data-and-training/data-plan.md), [training plan](../data-and-training/training-plan.md),
[model card](../data-and-training/model-card.md) and [evaluation protocol](../evaluation/protocol.md).

## Data preparation

- Record shape (JSONL): `id, source_group, split, prompt, completion, license, refactoring_type,
  smell_rule, variant, template_style, verification`. `prompt` is the original code;
  `completion` is a reviewed reference output. Clean controls (`variant: clean-control`,
  `smell_rule: null`) are identity pairs.
- Keep a manifest with source URLs, commits and reference tests.
- Split by `source_group` (repository/family or authored template family), never by random rows.
  A `source_group` must not cross splits. The current authored dataset uses 320/48/48
  (train/validation/test), with 20 findings + 20 clean controls per type in train and
  4 findings + 2 clean controls per type in validation/test.
- Validate with `uv run python scripts/validate_dataset.py data/curated.jsonl` (checks required
  fields, normalized duplicate prompts/completions, cross-split leakage, non-empty splits).
- Freeze the test split by Day 5 and never tune on it. Save dataset hash + split manifest.
- Licensing and provenance are mandatory; public GitHub availability is not a license review.

## Hardware decisions (P1 gate)

- Inventory CPU/RAM/GPU/VRAM/OS and weekly availability; record it in the environment Issue.
- Measure local inference and a tiny LoRA save/reload. If the laptop cannot train, reduce
  model/context/batch or obtain confirmed free university GPU access — and record the blocker.
- Do not assume CPU training or intermittent free compute meets the schedule.

## Training

- Path: PyTorch + Transformers + Datasets + PEFT + bitsandbytes. Default is 4-bit NF4 QLoRA
  (rank 16 / alpha 32 / all-linear, `max_length=2048`, 3 epochs, cosine, gradient checkpointing).
  The target is `Qwen/Qwen2.5-Coder-3B-Instruct` with a 1.5B local fallback and an optional 7B
  Colab run.
- Training and inference share `src/models/prompting.py` (system prompt, findings format, chat
  template, `<|im_end|>`); only completion tokens contribute to the loss.
- The script rejects unresolved settings, invalid data, records over `max_length`, and CPU-only
  training, excludes test records, and supports `--resume-from-checkpoint`. `--dry-run` audits
  token lengths with the real tokenizer on CPU.
- Record every run via `experiments/run-template.json` / `runs/<name>/run-manifest.json`: run id,
  code SHA, dataset hash/split manifest, resolved model commit, package/CUDA versions, hardware,
  seed, LoRA settings, batch, learning rate, epochs, context length, duration, peak memory,
  validation results, adapter location + checksum, and any failure (NFR05).
- Select on validation metrics, then evaluate the frozen test set once. Training loss alone does
  not measure successful refactoring; report a non-improvement honestly.

## Independent evaluation

- Comparison groups:
  - **A** — original model, one role, same verification tools available.
  - **B** — original model, analysis + refactoring + review roles.
  - **C** — fine-tuned modification model, one role.
  - **D** — fine-tuned modification role + original model for other roles; coordinated.
- Declare a total call/token budget and explain its distribution. If equal budgets are
  impractical, report quality alongside time, calls and tokens.
- Measures: syntax validity; reference-test preservation (with coverage/counts);
  `smell_resolution_rate`; `refactor_success_rate` (syntax valid + symbols preserved + tests
  available and passing + declared finding not unresolved); separate
  `findings_refactor_success_rate` and `clean_control_success_rate`; overall acceptance; latency,
  calls, tokens, memory; task-appropriate structural indicators (a lower indicator alone is not
  success).
- Group A receives the same AST findings as Group B; the only difference is coordination. A
  `--baseline base` run compares against the real base model rather than the deterministic mock.
- Best-of-N candidate selection (`--candidates N`) uses static AST scoring only; no candidate is
  executed during selection (NFR01).
- Include failures and timeouts in the denominator; compare the same examples across groups;
  report sample size, source diversity and repeated seeds where resources allow.
- Harness: `uv run python -m evaluation.harness --output-dir experiments` and
  `--dataset data/curated.jsonl --split test --name dataset_test` →
  `experiments/<name>_results.csv` and `experiments/<name>_summary.json`.

## Release acceptance

P0 behavior runs on the demonstration machine and from a clean clone in a fresh environment.
Prefer a second physical machine; otherwise label the reproduction as same-laptop clean setup and
record cross-machine validation as untested. A working prototype does not depend on proving the
research hypothesis.
