# Data, model and evaluation execution

## Hardware gate

Record OS, CPU, RAM, GPU/accelerator, available VRAM/unified memory and free disk without private machine identifiers. Read current official model and framework documentation when selecting versions. Choose the smallest licensed model that demonstrates the selected task; pin the exact model revision and license. No specific model or success claim is predetermined.

Keep core API/CI dependencies separate from training dependencies. The current training scaffold assumes CUDA and does not establish Apple Silicon or CPU training support. On a compatible CUDA laptop, validate the exact PyTorch/CUDA/transformers/PEFT combination in an isolated environment. On Apple Silicon, implement and smoke-test a compatible training path only if supported by official documentation and resources; never reuse an incompatible CUDA lock. CPU inference may be feasible; CPU fine-tuning must be measured, not promised.

First run a tiny licensed pilot with a short context and bounded steps. Record wall time, memory, output directory and command. Save/reload the adapter and confirm it actually changes the loaded model state. Test checkpoint resume separately if required. Define a maximum job duration and memory budget from the measurement before a longer run. Never assume that inference feasibility implies training feasibility. If infeasible, document a smaller-model attempt or confirmed free university hardware and leave the training task blocked until genuine execution.

## Curation sequence

Read the existing data schema and validator before adding fields. Keep source, source_group, license, original code, target code, task type and reference tests consistent. Use permitted existing sources and/or clearly identified team-authored examples. No invented provenance, scraped private code or silently model-generated ground truth. Record any synthetic generation method and inspect its quality.

Use a small pilot dataset for pipeline checks, then curate the feasible experimental dataset. Check parse validity and transformation inclusion rules. Split by source_group before adaptation; detect exact and near duplicates across splits and record exclusions. Save IDs, counts, hashes and provenance in manifests. Keep fixture examples independent of the final test set. The actual dataset size is a measured decision recorded by Day 5, not a fabricated target.

Keep train-only parameter updates, validation-only hyperparameter/prompt selection, and test-only final comparison. Freeze the held-out test set by Day 5. Do not inspect test failures to improve prompts/model and rerun the same test as an independent result; report any post-test change as exploratory with a new protocol/version.

## Fine-tuning sequence

Start with the refactoring role only and one LoRA adapter. Review target-module names for the actual architecture. Pin tokenizer/model revisions, dependency lock, data manifests and seed. Record precision, batch size, accumulation, sequence length, learning rate, steps/epochs, target modules, hardware and checkpoint paths. Compare validation outputs with the base model using the same format and budget. Check adapter save/reload and final checksums. Quantization is optional and hardware dependent, not an assumed universal solution.

Do not commit base weights, training records containing private inputs, caches or large checkpoints. Store small sanitized configs/log summaries in experiments/. Use permitted GitHub Release artifacts only after checking size, quota and redistribution rights; otherwise record reproducible retrieval instructions and hashes, with the storage limitation explicit.

## Final comparison

Follow docs/evaluation/protocol.md for the definitions of A/B/C/D. Keep original model single-role, original model multi-role, adapted model single-role and adapted model multi-role distinguishable. Set per-method call/token/time budgets and report differences honestly; more calls may explain gains. Run all feasible methods on the same frozen cases. Preserve every error/timeout in denominators.

Measure supported-task correctness, available reference-test outcomes, syntax validity, rejection/failure rates, latency and available resource metrics. Passing reference tests supports only those cases; no proof of universal equivalence. Derive figures from retained records using a repeatable command. Show counts and denominators, protocol version, model identities, limitations and failures. Small samples support limited conclusions. Training that fails to improve is a valid finding when documented.

## Evidence destinations

Store a hardware report, model comparison, pilot record, data manifest, baseline record, training record, validation selection, final evaluation index and limitations under experiments/, with hashes and commands. Update docs/data-and-training/model-card.md only from real records. See the existing experiment template; adapt it rather than discarding it. Agent-generated prose is not an experimental observation.
