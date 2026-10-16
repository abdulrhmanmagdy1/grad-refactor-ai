# Project brief and target behavior

## Research problem

Can a small, locally runnable code model adapted with LoRA and coordinated through analysis, refactoring and review roles produce useful behavior-preserving Python refactorings under a measured resource budget? Compare the original and adapted model with single-role and multi-role workflows. Improvement is a question to measure, not a promised result.

## First-release user journey

A user opens a local page, pastes one Python snippet and selects the single supported refactoring type. The service validates limits, analyzes it, proposes revised code, checks it, and shows a diff and explanation. Syntax, reference-test status, model review and overall disposition are separate. Original code remains unchanged. The user may download the proposal after inspection; the system never edits a host repository automatically.

Select one narrow task during P1 using measured model examples, such as simplifying a constrained conditional pattern. A task must have explicit inclusion/exclusion rules and reference tests. The example is a candidate, not a validated choice. Default scope is one file containing a small pure function. No imports requiring external packages, filesystem operations, network use, interactive input or arbitrary project execution in test fixtures.

## Existing foundation - inspect before changing

- src/refactor_ai/api.py and analysis.py provide FastAPI health and static AST analysis only.
- pyproject.toml and uv.lock pin the Python 3.11 core environment.
- tests/ has foundation coverage. Run it rather than assuming a count remains constant.
- scripts/doctor.py, validate_dataset.py and check_docs.py provide foundation checks.
- training/train_lora.py, training/requirements.in and configs/training.example.json are preliminary training scaffolding. GPU execution is not validated. CHOOSE values are not real model selections.
- docs/ contains editable plans, with two PDF exports under docs/pdf/.
- .github/ contains CI and workflow templates. Core CI must remain runnable without a GPU or model download.

The product UI, actual model provider, role workflow, run history, isolated reference runner and completed research results are not delivered by this documentation update. Recheck that statement against the checkout when starting later.

## Minimal implementation choices

Retain FastAPI and Python 3.11. Prefer a small React/TypeScript UI built with Vite if the laptop has a supported Node runtime; pin Node and the frontend lockfile when introduced. Keep frontend code under frontend/. Use SQLite for local run records and one serialized inference queue with no simultaneous training and inference. A simple explicit coordinator is sufficient; do not add LangGraph, message brokers, microservices or Kubernetes for this release.

Put backend additions under src/refactor_ai/, deterministic tests under tests/, curation/evaluation entry points under scripts/, training tools under training/, sanitized evidence under experiments/ and supervisor records under docs/supervisor-reviews/. Keep downloads and generated runs in ignored data/, models/ and runs/.

## Release boundaries

Local demonstration with trusted fixtures only. No public deployment, authentication system, repository-wide edits, multiple languages, background agent autonomy outside the project, paid inference or training from scratch. A fake provider can validate plumbing but cannot fulfill the real-model demonstration. A pretrained model without a saved and reloaded training adapter cannot fulfill fine-tuning.
