# Multi-Agent Refactoring for Python

A graduation project investigating whether a coordinated analysis, refactoring, and review workflow can improve Python code while preserving its intended behavior. The team will fine-tune an existing open-weight code model and evaluate it against the original model and a single-agent baseline.

**Current status:** project foundation. The repository contains the project specification, an eight-week delivery plan, team assignments, a working static-analysis API, and a preliminary training script. The model, agent workflow, and product interface have not been implemented or evaluated yet.

## Project documents

| Document | Purpose |
|---|---|
| [Project documentation (PDF)](docs/pdf/01-project-documentation.pdf) | Full specification, design, development, data, training, and evaluation |
| [Team delivery plan (PDF)](docs/pdf/02-team-delivery-plan.pdf) | Each member's workstream and outputs in every phase |
| [Documentation index](docs/README.md) | Editable source documents |
| [Team assignments](docs/planning/assignments.md) | Workstream owners and phase outcomes |

The PDFs are version 0.2 planning snapshots. Source documents, Issues, and the Project board remain the current working references. The team keeps clear workstream ownership across the five phases and records scope changes with the supervisor.

## Scope of the first release

The first release will support small Python inputs and one or two agreed refactoring types. It will show a proposed change, an explanation, and separate verification results for human review. Training from scratch, multiple programming languages, large repositories, and public execution of arbitrary code are outside this release.

The initial delivery window is eight weeks from the team's agreed start date. The official deadline and university report template still need confirmation. A supervisor review is planned after each phase. The project has no budget for paid services.

## Run the foundation service

Install Git, Python 3.11, and [uv](https://docs.astral.sh/uv/getting-started/installation/), then run:

```bash
git clone https://github.com/abdulrhmanmagdy1/grad-refactor-ai.git
cd grad-refactor-ai
uv sync --frozen
uv run uvicorn refactor_ai.api:app --reload --host 127.0.0.1
```

Open http://127.0.0.1:8000/docs for the interactive API reference. The current service parses code and reports a small set of structural heuristics. It does not execute submitted code, generate refactorings, or call a language model.

```bash
uv run python scripts/doctor.py
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python scripts/check_docs.py
```

## Team workspace

- [Project board](https://github.com/users/abdulrhmanmagdy1/projects/1)
- [Issues](https://github.com/abdulrhmanmagdy1/grad-refactor-ai/issues)
- [Milestones](https://github.com/abdulrhmanmagdy1/grad-refactor-ai/milestones)
- [First-day guide](docs/development/first-day.md)
- [Contribution workflow](CONTRIBUTING.md)

The repository and Project board are private. Team members publish work through linked pull requests. Owners run acceptance checks before merging; a second-person approval is not required.

## Repository layout

`src/` contains the service, `tests/` its tests, `scripts/` validation utilities, `training/` the preliminary fine-tuning path, `configs/` configuration examples, `experiments/` experiment records, `planning/` the initial task and assignment data, and `docs/` the documentation.

Large datasets and model weights do not belong in ordinary Git history. The feasibility phase will check whether adapters and permitted data can fit within GitHub's free storage limits. No paid storage or hosting is assumed.
