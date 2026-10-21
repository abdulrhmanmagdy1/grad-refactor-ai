# Release notes (draft)

Status: draft of 2026-10-21, prepared by the coding agent for Abdelrahman Magdy (T28). No tag exists. The [acceptance status](acceptance-status.md) places the tag after the owners' inspections and the team's decisions on the data license and the adapter, so this draft is ready to paste into a GitHub release once those are done. Replace the commit below with the tagged commit and re-check every checksum.

Proposed tag: `v1.0.0` on `main`, published as a release of the private repository. Base-model weights are never included.

## What this release contains

A local web service and interface that proposes one refactoring, flattening nested if statements into guard clauses, for one small Python function, and reports four checks separately: syntax, a structural rubric, trusted reference tests run in an isolated process, and a model review. It runs Qwen2.5-Coder-0.5B-Instruct on a 4 GB laptop GPU, with a LoRA adapter for the refactoring role, or in a demo mode without a model.

- Service, run history and web interface: [user guide](user-guide.md), [setup](../development/setup.md)
- Dataset `guard_clauses` v1 with frozen splits: [data plan](../data-and-training/data-plan.md)
- Training lane on Kaggle: [Kaggle lane](../../training/kaggle/README.md)
- Evaluation harness and the frozen protocol eval-v1: [protocol](../evaluation/protocol.md)
- Report ([Markdown](../report/report.md), [PDF](../report/report.pdf)), [slides](slides/grad-refactor-ai-presentation.pptx), [demonstration script](demo-script.md), [handover](implementation-handover.md)

## Results (frozen test split, 88 cases per arm, one run)

| Arm | Model | Workflow | Ready to use (`proposal_ready`) |
|---|---|---|---|
| A | Original | Single role | 7 (8.0%) |
| B | Original | Three roles | 1 (1.1%) |
| C | Fine-tuned | Single role | 70 (79.5%) |
| D | Fine-tuned | Three roles | 35 (39.8%) |

Fine-tuning helped (C against A: 65 cases accepted only with the adapter, 2 only without it; Holm-adjusted exact McNemar p < 0.0001). The three-role workflow lowered acceptance with both models, mainly because the untuned review role's outputs were cut off and counted as errors. Eleven of twelve pre-registered targets were met. Source: [test-split summary](../../experiments/evaluation/test-2026-10-21/targets-report/summary.md).

## Checksums

| Artifact | Identity |
|---|---|
| Base model | Qwen/Qwen2.5-Coder-0.5B-Instruct, revision `ea3f2471cf1b1f0db85067f1ef93848e38e88c25`, `model.safetensors` SHA-256 `f9523886352217ded3aeeef552b381af79d568c6d49a4b9e423288cea56b0a44` (downloaded by the user, not included) |
| LoRA adapter `full-2026-10-21` | `adapter_model.safetensors` SHA-256 `dff9ae024f0314224d84759772918b59a3fa9037ecbf7ad7a7d43357e1b1d5d2`, `adapter_config.json` SHA-256 `a190572935f3c37d2f22fcca45024c4fb4f790e3f99802457abc2d3f38682571` (attach only after the team decides its redistribution) |
| Dataset | `datasets/guard_clauses/v1/records.jsonl` SHA-256 `299b4f7fca170d2a9260319f6c1f81e832d54114c8bdd51959d6aeb8b23ff2e3` |
| Frozen test split | rendered hash `27b6d0ec9430ee30a96617949a31e1c71a0a5c0be7187b36bc660d998e95633`, content hash `3a1e6b95…` ([freeze record](../../experiments/data/test-split-freeze.json)) |
| Evaluation code | commit `9582c66` (clean tree), protocol eval-v1 ([provenance](../../experiments/evaluation/test-2026-10-21/provenance.json)) |

## How to run

```powershell
uv sync --frozen
cd frontend; npm ci; npm run build; cd ..
uv run uvicorn refactor_ai.api:app --host 127.0.0.1
```

This starts demo mode. For the model, follow [using the fine-tuned adapter](user-guide.md#using-the-fine-tuned-adapter-for-the-refactoring-role).

## Known limits

- One refactoring type and one small model; most data comes from team-written templates.
- Passing reference tests covers the tested inputs only; code pasted by a user has no trusted tests and ends at best as "Not sure".
- The reference runner is not a sandbox for hostile code ([runner safety](../development/runner-safety.md)).
- Reproduced from a clean clone on one laptop only ([clean-clone record](../../experiments/qa/2026-10-21-clean-clone-reproduction.md)).
- Training and evaluation ran in float32 on Kaggle; the laptop serves the adapter in bfloat16.

## Before publishing

- [ ] Each owner has inspected their workstream ([handover](implementation-handover.md)).
- [ ] The license of the team-authored data and the adapter's redistribution are decided.
- [ ] The tagged commit passes CI and the checksums above are re-checked.
- [ ] The R5 review is recorded, or the release is labeled as before it.
