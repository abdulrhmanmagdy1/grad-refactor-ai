# Model card

**Status: not trained.** No adapter has been trained on the curated dataset. A 16-step pilot adapter exists only as a feasibility check on pilot material. This card records the measured facts so far; it is not evidence that a trained model exists.

| Field | Current value |
|---|---|
| Intended task | Refactoring role for one task: replace nested conditionals with guard clauses (`guard_clauses`, task version 1, prompt refactor-v1) in one small Python function |
| Base model and revision | Qwen/Qwen2.5-Coder-0.5B-Instruct, revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25` (measured candidate; not yet approved by the supervisor) |
| License and adapter terms | Apache-2.0, from the model card metadata and the LICENSE file at that revision; adapter redistribution terms not yet reviewed |
| Training data and provenance | Not prepared; the curated dataset is built by the data workstream under `datasets/guard_clauses/v1/`. The pilot used 16 pilot records written by the models workstream |
| Adaptation method | LoRA on the refactoring role: rank 8, alpha 16, dropout 0.05 on all attention and MLP projections (4.4M trainable parameters), bf16 base with fp32 adapter weights; the training run will use gradient checkpointing and at most 1,024 tokens per record |
| Hardware and training duration | NVIDIA GeForce RTX 2050 (4 GB); the 16-step pilot took 20.8 s; the training run has not taken place |
| Test set | Not approved |
| Results and baselines | No evaluation results. Pilot observations only: the base model produced no parseable proposal on 8 pilot functions and one long input with greedy decoding, and 1 of 24 (an unchanged copy) with sampling; the pilot adapter made 12 of 12 pilot outputs parse, with 10 passing the rubric, on prompts in the style of its training records |
| Artifact and checksum | No released artifact. Pilot adapter (local only): `adapter_model.safetensors` SHA-256 `cf74fcea961ea9e94ffc228711c90c2bc5ac29e943a2dd27774a3bfca82bb34f` |

Measured context facts: the refactoring prompt adds 141 tokens to the code, a realistic 3,000-character function is about 770 tokens, and inputs dense in digits or non-ASCII text can reach one token per UTF-8 byte. Observed pilot failure cases: an output that dropped a branch of the original function, an output that kept the nesting, and explanations that stated nesting depths the model did not check. The intended use requires human review and does not guarantee behavioral preservation.
