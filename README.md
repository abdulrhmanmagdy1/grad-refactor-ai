# Multi-Agent Refactoring for Python

A graduation project that asks whether coordinating analysis, refactoring and review roles, and fine-tuning a small open code model, make behavior-preserving refactoring proposals for Python more reliable than a single call to the original model.

The product is a local web application and HTTP API. A person pastes one small Python function; analysis, refactoring and review roles backed by one local model (Qwen2.5-Coder-0.5B-Instruct, with the refactoring role optionally fine-tuned with LoRA) propose a guard-clause refactoring: nested conditionals are replaced with early returns or raises. The proposal is checked in four dimensions that are reported separately and never merged: syntax, a structural task rubric, trusted reference tests run in an isolated process, and the model's own review. The person reads the diff and the evidence, then downloads the proposal and records an accept or reject decision; the service never changes their files.

The research part compares four arms on a frozen test split: the original model and the fine-tuned adapter, each in a single-role and a multi-role workflow.

| Arm | Refactoring role | Workflow |
|---|---|---|
| A | Original model | Single role: one refactoring call |
| B | Original model | Multi-role: analysis, refactoring, review, at most one correction |
| C | LoRA adapter | Single role |
| D | LoRA adapter (analysis and review on the original model) | Multi-role |

## Current status (2026-10-21)

**Implemented and tested.** The automated tests use a deterministic fake provider that stands in for the model; refactoring quality is measured only by the recorded evaluation below.

| Part | What exists | Evidence |
|---|---|---|
| Task | One refactoring, `guard_clauses` (task version 1): input rules with reason codes, a deterministic reference transformation and an eight-check rubric | [Task scope](docs/requirements/task-scope.md) |
| Workflow | Single-role (exactly one call) and multi-role (at most five calls, one correction) coordination with strict output parsing, budgets and deadlines | [Workflow](docs/architecture/workflow.md), [notes](docs/report/notes/workflow.md) |
| Verification | Syntax, rubric, reference tests and model review kept separate; the reference runner passed all 19 isolation self-checks on the Windows demonstration laptop, and its tests passed in the Ubuntu CI job as a non-root user | [Runner safety](docs/development/runner-safety.md) |
| Service | FastAPI run API with a bounded queue, SQLite run history (one service process per database, enforced by a file lock), interruption recovery and a uniform error model | [Contracts](docs/architecture/contracts.md), [backend notes](docs/report/notes/backend.md) |
| Web interface | React and TypeScript single-page application, redesigned on 2026-10-21: input, progress, diff, the four verification results, decisions, history; 26 screenshots taken in fake mode | [Frontend notes](docs/report/notes/frontend.md), [screenshots](docs/report/screenshots/) |
| Local model | Qwen2.5-Coder-0.5B-Instruct at a pinned revision, served by a separate worker process; real-GPU provider tests passed on the laptop | [Model notes](docs/report/notes/model.md) |
| Dataset | `guard_clauses` v1: 799 records with trusted reference tests, split 627 / 84 / 88 by source group, test split frozen | [Data plan](docs/data-and-training/data-plan.md) |
| Evaluation harness | Arms A to D with case-level records and paired comparisons; checked only with a stub workflow and the fake provider | [Protocol](docs/evaluation/protocol.md), [notes](docs/report/notes/data-evaluation.md) |
| Feasibility | A 16-step LoRA pilot on pilot material (saved, reloaded and resumed) and a validation-only choice of the code-first prompt format | [Training records](experiments/training/README.md), [model records](experiments/models/README.md) |

**Results (frozen test split, protocol eval-v1).** The fine-tuned refactoring role was trained on Kaggle (Tesla T4, 3 epochs, [training record](experiments/training/full-2026-10-21.json)) and adopted by a rule written before any comparison ([selection record](experiments/training/validation-selection-2026-10-20.json)). The single test-split run compared four arms on 88 held-out cases ([results](experiments/evaluation/test-2026-10-21/targets-report/summary.md)):

| Arm | Model | Workflow | Accepted (proposal_ready) |
|---|---|---|---|
| A | Original | One role | 7/88 (8.0%) |
| B | Original | Analysis, refactoring, review | 1/88 (1.1%) |
| C | Fine-tuned refactoring role | One role | 70/88 (79.5%) |
| D | Fine-tuned refactoring role | Analysis, refactoring, review | 35/88 (39.8%) |

Fine-tuning is the large effect (C vs A: 65 cases accepted only with the adapter, 2 only without it). Adding roles lowered acceptance with both models, mainly because the untuned review role's outputs were cut off and counted as errors. Eleven of the twelve targets set before the test run were met; arm D's acceptance floor was not. Passing reference tests supports behavior preservation on the tested inputs only. The full analysis is in the [report](docs/report/report.md).

**Open items.**

- No supervisor review has been held yet. The team's packs for [R1](docs/supervisor-reviews/r1-scope-and-feasibility.md) to [R5](docs/supervisor-reviews/r5-delivery.md) are prepared, with the feedback fields left empty.
- The university report template, the official deadline and the presentation format are not yet confirmed ([delivery checklist](docs/delivery/checklist.md)).
- Each student still has to inspect and accept their workstream ([handover](docs/delivery/implementation-handover.md)).
- Cross-machine reproduction is untested (a [clean clone](experiments/qa/2026-10-21-clean-clone-reproduction.md) passed on the demonstration laptop only), the redistribution license of the team-authored data is a team decision, and the adapter is not published. The reference runner has no operating-system network, file system or privilege boundary ([runner safety](docs/development/runner-safety.md#honest-limits)).

## Quickstart

Install Git, Python 3.11, [uv](https://docs.astral.sh/uv/getting-started/installation/) and, to build the web interface, Node.js 24.12.0 or a newer 24.x release with npm 11.6 or newer. Then, from a terminal:

```bash
git clone https://github.com/abdulrhmanmagdy1/grad-refactor-ai.git
cd grad-refactor-ai
uv sync --frozen
uv run python scripts/doctor.py

cd frontend
npm ci
npm run build
cd ..

uv run uvicorn refactor_ai.api:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/ for the web interface or http://127.0.0.1:8000/docs for the interactive API reference. Start the service from the repository root. By default it runs with the deterministic fake provider: the interface shows a permanent warning banner, and the results are fixtures, not model output. If uv was installed as a Python package, run the uv commands as `python -m uv ...`.

To use the local model, prepare the training environment and model weights, create `configs/model.local.json` from [configs/model.example.json](configs/model.example.json) and start the service with `REFACTOR_AI_PROVIDER=local`; `REFACTOR_AI_REFACTOR_USE_ADAPTER=true` runs the refactoring role with a configured LoRA adapter. The [user guide](docs/delivery/user-guide.md) explains every step, the results and the errors.

Checks before a pull request ([setup guide](docs/development/setup.md), [frontend guide](docs/development/frontend.md)):

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv run python scripts/check_docs.py

cd frontend
npm run typecheck
npm test
```

Neither the core tests nor CI download a model or need a GPU; the real-model provider tests run only with `REFACTOR_AI_GPU_TESTS=1`.

## How a run works

1. **Validate.** The input is checked against the task rules without a model. Unsupported input completes as `no_change` with reason codes and no model call.
2. **Analyze** (multi-role only). The analysis role reports the nested conditionals to flatten; unusable output falls back to the static findings.
3. **Generate.** The refactoring role writes the complete new function and a one-line explanation.
4. **Verify.** Syntax, the rubric and, for the six server-owned demonstration cases, trusted reference tests in an isolated process. The API itself never executes code.
5. **Review and correct** (multi-role only). The review role gives a verdict; a failed check or a rejection triggers one correction, never more.
6. **Decide.** The outcome is `proposal_ready`, `rejected`, `uncertain`, `no_change` or `failed`. Missing tests never count as a pass, a model verdict never overrides a failed check, and passing tests are never presented as proof of equal behavior for every input.

## Repository layout

| Path | Contents |
|---|---|
| `src/refactor_ai/` | The service: `api.py`, `config.py` and `contracts.py`; `tasks/` (task definition and rubric), `agents/` (coordinator, prompts, parsing), `verification/` (checks, disposition, reference runner), `providers/` (fake and local model), `runs/` (queue and storage), `data/` (dataset curation), `evaluation/` (harness), `fixtures/demo_cases.json` |
| `tests/` | Python tests for the core environment |
| `frontend/` | React and TypeScript web interface built with Vite; FastAPI serves the build from `frontend/dist` |
| `datasets/` | The curated `guard_clauses` v1 dataset with its manifest, metadata and attribution notice |
| `training/` | Model download, benchmark, LoRA training and adapter checks, pilot material, the training-environment lock and the private Kaggle lane (`training/kaggle/`) |
| `configs/` | Example model and training configurations; `*.local.json` files stay local |
| `experiments/` | Committed records: hardware, data curation and the test-split freeze, model benchmarks, training, evaluation |
| `scripts/` | Dataset curation and validation, evaluation and reporting, contract examples, documentation link check and PDF export, environment report (`doctor.py`) |
| `docs/` | Documentation; start at the [index](docs/README.md) |
| `planning/` | Initial task and assignment data |
| `.github/` | CI for Linux and Windows, Issue and pull request templates |
| `pyproject.toml`, `uv.lock` | The core Python environment (CPU only, no model libraries) |
| `CONTRIBUTING.md`, `AGENTS.md`, `NOTICE.md` | Contribution workflow, instructions for coding agents, licensing notice |
| `models/`, `runs/`, `data/` | Local only and ignored by Git: model weights, run history and training outputs, raw downloads |

## Key documents

| Document | Use |
|---|---|
| [User guide](docs/delivery/user-guide.md) | Start the service and use the web interface and the API |
| [Environment setup](docs/development/setup.md) and [frontend development](docs/development/frontend.md) | Reproduce the development environment |
| [Component contracts](docs/architecture/contracts.md) and [example JSON](docs/architecture/examples/README.md) | Authoritative behavior, fields, error codes and settings, with real request, response and run-record examples |
| [Workflow and verification](docs/architecture/workflow.md) | Sequence, budgets, dispositions and token budgets |
| [Task scope](docs/requirements/task-scope.md) and [requirements](docs/requirements/srs.md) | What the release supports and must do |
| [Runner safety](docs/development/runner-safety.md) | How reference tests are isolated and what the isolation does not cover |
| [Data plan](docs/data-and-training/data-plan.md), [training plan](docs/data-and-training/training-plan.md) and [model card](docs/data-and-training/model-card.md) | Dataset, fine-tuning and model provenance |
| [Evaluation protocol](docs/evaluation/protocol.md) | Arms, measures and the freezing procedure |
| Report notes: [backend](docs/report/notes/backend.md), [workflow](docs/report/notes/workflow.md), [model](docs/report/notes/model.md), [data and evaluation](docs/report/notes/data-evaluation.md), [frontend](docs/report/notes/frontend.md) | Each workstream's technical notes and evidence |
| [Report](docs/report/report.md), [slides](docs/delivery/slides/grad-refactor-ai-presentation.pptx) and [demonstration script](docs/delivery/demo-script.md) | The graduation report, the presentation and the live demonstration |
| [Implementation handover](docs/delivery/implementation-handover.md) | What was built, how to run it, results, known defects and what each owner inspects |
| [Delivery checklist](docs/delivery/checklist.md) and [acceptance and handover](docs/agent-execution/06-acceptance-and-handover.md) | What delivery requires |
| [Supervisor reviews](docs/supervisor-reviews/README.md) | How reviews are held and recorded; the R1 to R5 packs are prepared |
| [Experiment records](experiments/README.md) | Hardware, data, model, training and evaluation records; for example the [model records](experiments/models/README.md) and [training records](experiments/training/README.md) |
| [Documentation index](docs/README.md) | Every document |

The [project documentation](docs/pdf/01-project-documentation.pdf) and [team delivery plan](docs/pdf/02-team-delivery-plan.pdf) PDFs are version 0.3 planning snapshots written before the implementation. The source documents, Issues and the Project board are the current references.

## Team and workstreams

| Member | GitHub | Workstream | Owns |
|---|---|---|---|
| Abdelrahman Magdy | @abdulrhmanmagdy1 | Backend, integration and coordination | API, configuration, run storage, contracts and examples, releases, supervisor meetings |
| Abdullah Tarek | @abdallah414 | Agent workflow and verification | Task scope, roles and coordinator, verification checks, reference runner |
| Abdelrahman Adel | @abdelrhmanadel200 | Models and training | Model choice and benchmark, local model provider, LoRA training, model card |
| Shahd Abdelhay | @shahd-abdelhay | Data, research and evaluation | Related work, dataset and splits, demonstration cases, evaluation protocol and harness |
| Dania El-Walily | @d5ania | Frontend and delivery materials | Web interface, user guide, report assembly, slides and demonstration |

Each task has one accountable owner, and there is no assigned peer-review role. The implementation added on 2026-10-20 was produced on the demonstration laptop with the optional [agent execution pack](docs/agent-execution/README.md), one coding agent per workstream ([allocation](docs/agent-execution/team-allocation.md)). Each student owns their workstream and inspects and explains it before the delivery is accepted.

## Team workspace

- [Project board](https://github.com/users/abdulrhmanmagdy1/projects/1)
- [By Owner: live Project view](https://github.com/users/abdulrhmanmagdy1/projects/1/views/3), grouped by GitHub assignee
- [Issues](https://github.com/abdulrhmanmagdy1/grad-refactor-ai/issues)
- [Milestones](https://github.com/abdulrhmanmagdy1/grad-refactor-ai/milestones)
- [First-day guide](docs/development/first-day.md) and [contribution workflow](CONTRIBUTING.md)
- [21-day roadmap](docs/planning/roadmap.md), [tasks by owner](docs/planning/by-owner.md) and [team delivery plan](docs/planning/assignments.md)

The repository and the Project board are private. Team members publish work through linked pull requests; owners run the acceptance checks before merging, and a second-person approval is not required. Supervisor reviews are planned after each of the five phases.

## Licensing and data

No open-source license has been selected for the project ([NOTICE](NOTICE.md)). The base model is Apache-2.0; its weights and any adapters are never committed. Dataset sources and attribution are in the [dataset notice](datasets/guard_clauses/v1/NOTICE.md); the redistribution license of the team-authored records is still pending a team decision. The project uses no paid services.
