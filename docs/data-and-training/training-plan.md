# Fine-tuning plan

No model, hardware configuration, or training result has been approved yet. The first candidate task is the refactoring role, while the original model remains the comparison baseline.

## Feasibility experiment

Inventory hardware, select small candidates with suitable licenses, measure inference on the demonstration machine, and run a small training job. Check memory, elapsed time, adapter saving, reloading, and checkpoint recovery.

Qwen Coder is one example candidate, not a final selection or a claim of best performance. Record exact model and tokenizer revisions after selection.

## Candidate training path

The preliminary path uses PyTorch, Transformers, Datasets, and PEFT. Begin with LoRA if the hardware supports it. Consider quantization only after a compatibility test. The current script implements an unquantized CUDA LoRA path; QLoRA is not implemented.

Do not assume that CPU training or an intermittently available free GPU can meet the schedule. Set the model, precision, context length, batch settings, and training budget from measurements.

## Preparation and execution

Validate the curated JSONL file:

```bash
uv run python scripts/validate_dataset.py data/curated.jsonl
```

In a separate, hardware-compatible training environment, copy the configuration example, select an approved model and exact revision, and run:

```bash
python training/train_lora.py --config configs/training.local.json
```

The script rejects unresolved settings, invalid data, and environments without CUDA. It masks prompt tokens from the loss and excludes test records from the Trainer. It supports --resume-from-checkpoint. A GPU smoke test is required before relying on it for experiments.

## Experiment record

Record the run identifier, code SHA, dataset hash and split manifest, model revision, package and CUDA versions, hardware, seed, LoRA settings, batch and accumulation settings, learning rate, epochs, context length, duration, peak memory, validation results, adapter location and checksum, and any failure or interruption. Use experiments/run-template.json.

## Selection and reporting

Choose a candidate using declared validation metrics, then evaluate the agreed test set. Training loss alone does not measure successful refactoring. If fine-tuning does not improve results, investigate and report that outcome without tuning on the test set.

## Free resources and storage

Colab may support interactive training experiments within its limits, but it is neither guaranteed compute nor permanent hosting. Save resumable artifacts within the available quota. Prefer a small adapter and metadata over redistributing the base model.
