# Multi-Agent Refactoring for Python

A local, modular, and fully tested multi-agent Python refactoring system with deterministic AST analysis, bounded multi-agent coordination, isolated sandbox verification, a curated 416-record dataset (findings + clean controls), a native fp16 LoRA fine-tuning path (the 4-bit QLoRA example remains experimental), an academic evaluation harness, and a professional single-page web interface (dark/light themes, Monaco editor, live diff/verification/metrics/trace/AST-graph inspection).

Built strictly according to graduation project architectural specifications (Python 3.11, FastAPI, Pydantic v2, SQLite, and React 19 + TypeScript + Vite + Tailwind v4 + Monaco for the UI).

### Implementation status

| Capability | State |
|---|---|
| Static AST analysis, structural metrics, AST constellation graph | Implemented and tested |
| Multi-agent workflow (Analysis → Refactoring → Review) with bounded correction | Implemented and tested |
| Provider registry (`mock`, `smart_ast`, `ollama`, `local_lora`) with live availability | Implemented (`GET /api/v1/providers`) |
| Isolated sandbox runner + auto-synthesized golden equivalence tests | Implemented and tested |
| Curated dataset (416 authored records, 320/48/48 splits, 224 findings + 192 clean controls, sha256 manifest) | Implemented (`data/curated.jsonl`, `data/manifest.json`) |
| Evaluation harness A–D with CodeBLEU / AST-similarity / MI + `refactor_success` / `smell_resolution_rate` | Implemented; Groups A/B executed on the built-in suite and the dataset test split |
| Web UI (React/TypeScript, dark + light themes, Monaco editor, run inspector, AST graph) | Implemented, built, and served by FastAPI |
| LoRA training path (`training/train_lora.py`, shared chat template, token audit) | Implemented & executed on Kaggle T4 as **native fp16 LoRA** (`load_in_4bit=false`, `optim=adamw_torch`; 4-bit QLoRA path remains unproven on that image); `eval_loss=0.005797` (`experiments/training/lora-fp16/run-manifest.json`, tracked copy; the adapter itself is not committed) |
| Fine-tuned adapter and Groups C/D results | Executed on frozen 48-case test split vs real untuned 3B base (`experiments/dataset_test_finetuned_summary.json`): Group D `refactor_success_rate=0.9167` (44/48; findings `0.8750`, clean `1.0000`, `test_pass_rate=1.0000` on 44 testable cases; `execution_pass_at_1=0.9773` on those 44, i.e. `43/48 = 0.8958` over all 48) vs Group A `0.6042` / Group B `0.7500` |

Measured artifacts: the 4-page report is tracked at `docs/report/Grad_Refactor_AI_Accuracy_Report.pdf`; the training manifest is tracked at `experiments/training/lora-fp16/run-manifest.json`; the adapter (`runs/lora-fp16/adapter`) is a private Kaggle dataset and is not committed; the blind-review answer key is excluded from Git until every rating is collected.

---

## Architecture Overview

```
                      +-----------------------------+
                      |     Web UI / FastAPI API    |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |    Workflow Orchestrator    |
                      +--------------+--------------+
                                     |
     +-------------------------------+-------------------------------+
     |                               |                               |
     v                               v                               v
+----+---------+              +------+-------+              +--------+-----+
|   Analysis   |              |  Refactoring |              |    Review    |
|    Agent     |              |    Agent     |              |     Agent    |
+----+---------+              +------+-------+              +--------+-----+
     |                               |                               |
     v                               v                               v
[Static AST]                 [Provider registry]             [Deterministic]
- Long Functions             - Mock (deterministic)          - Syntax Checks
- Deep Nesting               - Smart AST (CPU-safe)          - Symbol Integrity
- Complexity                 - Ollama / Local LoRA           - Isolated Sandbox
- AST constellation graph    - Live availability catalog     - Auto golden tests
```

### Separation of Concerns & Agent Roles
1. **Analysis Role (`src/agents/analysis_agent.py`)**:
   - Parses code statically with `ast.parse` (never executes input code).
   - Detects code smells: long functions (>30 lines), async routines, deeply nested control blocks (>3 levels), and cyclomatic complexity (>10).
2. **Refactoring Role (`src/agents/refactoring_agent.py`)**:
   - Proposes targeted transformations using a decoupled model provider interface.
   - Enforces token boundaries and responds to feedback in correction loops.
3. **Review Role (`src/agents/review_agent.py`)**:
   - Performs deterministic syntax checks.
   - Verifies symbol preservation (ensures required functions and classes are not deleted).
   - Generates unified diffs with line statistics.
   - Executes optional verification tests in an isolated sandbox runner.
4. **Workflow Orchestrator (`src/agents/orchestrator.py`)**:
   - Coordinates the 5-step pipeline: Ingestion -> Analysis -> Generation -> Verification -> Completion.
   - **Bounded Correction Loop**: allows at most **1 retry** with error diagnostics if syntax or review fails.
   - Enforces timeout boundaries and records state transitions in SQLite.

---

## Trust & Security Boundaries (NFR01, NFR02)
- **Zero API Code Execution (NFR01)**: The main FastAPI process and agent engine **never execute** submitted or candidate code directly. All code inspection is strictly performed via Python AST parsing.
- **Isolated Sandbox Runner (NFR02)**: User-provided tests, or golden equivalence tests auto-synthesized by the Review Agent (`src/runner/test_generator.py`), run in a strictly isolated subprocess (`src/runner/sandbox.py`) with:
  - 5-second execution timeout.
  - Memory limit (256 MB) and CPU limits via OS `setrlimit`.
  - Sanitized environment variables (stripping host tokens, keys, and paths).
  - Isolated temporary directory with automated cleanup.

---

## Model Layer (ADR08, ADR10, ADR12)
- **`BaseModelProvider` (`src/models/base.py`)**: Abstract interface defining `generate_refactoring` and `explain_changes`.
- **`MockModelProvider` (`src/models/mock_provider.py`)**: Deterministic, reproducible transformations for offline execution without GPUs or paid cloud APIs. Includes simulation knobs for testing retry loops.
- **`SmartASTProvider` (`src/models/smart_ast_provider.py`)**: Provably safe AST-to-AST transformations on CPU (mutable defaults, nesting merges, long-function extraction).
- **`OllamaModelProvider` (`src/models/ollama_provider.py`)**: Local Ollama daemon HTTP provider (default `qwen2.5-coder:1.5b`).
- **`LocalModelProvider` (`src/models/local_provider.py`)**: HuggingFace Transformers + PEFT/LoRA adapters with CPU fallback and timeout controls. When an explicit fine-tuned adapter is requested but cannot be loaded, it raises `ProviderUnavailableError` — a base model is **never** silently substituted for a fine-tuned one (NFR06 honesty rule).
- **`src/models/registry.py`**: name resolution plus the availability catalog behind `GET /api/v1/providers` (15-second probe cache; Ollama availability and HuggingFace stack status are probed live).

---

## Storage & Audit Trail (FR07, FR10, ADR09)
SQLite persistence (`src/core/db.py`) storing runs in table `runs`:
- `id` (UUID), `created_at` (ISO 8601), `status` (`queued`, `analyzing`, `generating`, `verifying`, `completed`, `failed`).
- `input_code`, `output_code`, `diff`, `metrics`, `errors`, `user_feedback`, and `verification`.
- Configured with Write-Ahead Logging (WAL) and ACID transactions.

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health, version, and `production` mode |
| `POST` | `/api/v1/analyze` | Run static AST heuristics (NFR01) |
| `GET` | `/api/v1/providers` | Live provider availability catalog for the UI selector |
| `POST` | `/runs` | Initiate refactoring workflow (returns run ID; supports `?sync=true`) |
| `GET` | `/runs/{id}` | Poll run status, metrics, diff, graphs, agent traces, and verification |
| `GET` | `/runs/{id}/report` | Markdown report rendered from the stored run record (inline or `?download=true`) |
| `GET` | `/runs` | List history of previous runs (FR10) |
| `GET` | `/api/v1/stats` | Measured aggregates over the stored runs (status, verdicts, mean/median duration, tokens) |
| `GET` | `/metrics` | The same aggregates in Prometheus text format (NFR07), plus in-flight runs and provider availability |
| `POST` | `/runs/{id}/feedback` | Record user acceptance or rejection (FR06); `/decision` is an alias |
| `GET` | `/` | Web UI (single-page React app) — built from `frontend/` |

`POST /runs` answers `429` with an explicit message when
`REFACTOR_AI_MAX_CONCURRENT_RUNS` (default 2) workflows are already executing. Service logs are
one JSON object per line (`REFACTOR_AI_LOG_FORMAT=text` for a human-readable line) and carry the
`X-Request-ID` echoed by every response.

---

## Quickstart & Local Setup

### Requirements
- Git, Python 3.11, and `uv`

### Installation
```bash
git clone https://github.com/abdulrhmanmagdy1/grad-refactor-ai.git
cd grad-refactor-ai
uv sync --frozen
```

### Running the API and Web UI
```bash
uv run uvicorn refactor_ai.api:app --reload --host 127.0.0.1 --port 8000
```
Open **http://127.0.0.1:8000** for the web interface (Monaco editor, Monaco diff viewer, run
comparison, history export,
verification inspector, metrics table, agent trace timeline, AST structure graph, command
palette, run history, and a dark/light theme toggle). `Ctrl+Enter` (`Cmd+Enter` on macOS)
starts a run from anywhere in the app, and the results header exports the current run as
a Markdown report. Swagger stays at **http://127.0.0.1:8000/docs**.

### Building the web UI (optional — the built bundle is committed)
The built bundle lives under `frontend/dist/` and is served automatically when present.
Rebuild after frontend changes:

```bash
cd frontend
npm install
npm run build
```

---

## Verification & Testing Suite

Run all checks and automated test suites:

```bash
# One command for every gate below (cross-platform, stops at the first failure)
python scripts/tasks.py all

# Run system doctor (toolchain, built bundle freshness, SQLite integrity)
uv run python scripts/doctor.py

# Run complete pytest suite (unit, integration, sandbox, API, operations)
uv run pytest

# Run linting and formatting checks
uv run ruff check .
uv run ruff format --check .

# Validate documentation links
uv run python scripts/check_docs.py

# Fail if the API models and the web client contract drifted apart
uv run python scripts/check_contract.py

# Validate dataset splits
uv run python scripts/validate_dataset.py data/curated.jsonl

# Release smoke test: boots the app, serves the built UI, completes one run (8 checks)
uv run python scripts/smoke_ui.py

# Retention for the local run history (dry run by default; --yes to delete)
uv run python scripts/prune_runs.py --keep 500

# Build the release checksum manifest and verify the working tree against it
uv run python scripts/make_release.py
uv run python scripts/verify_release.py
```

Web client gates (run inside `frontend/`):

```bash
npm ci
npm run verify   # eslint + tsc --noEmit + vitest + production build
```

---

## Curated Dataset (FR09, NFR05)

`data/curated.jsonl` holds 416 authored/synthetic records: 8 refactoring types × 52 records
(28 findings records + 24 clean-control records). Splits: train 320 / validation 48 / test 48;
each type has 20 findings + 20 clean controls in train and 4 findings + 2 clean controls in
validation/test. Every findings record is machine-verified before being written: prompts must
trigger their declared detector rule, and completions are accepted as behaviour-preserving only
after a real isolated-sandbox equivalence run (golden-baseline pytest with sampled inputs) or,
for signature-changing refactorings such as long-parameter-list, an authored smoke test. Clean
controls are identity pairs whose prompt the analyzer reports as finding-free; they teach the
model not to rewrite clean code. `data/manifest.json` records the sha256 of the file, template
counts, split/type counts and per-record verification method. License: CC0-1.0 (authored, not
scraped). Prompts contain no `# example:` provenance comment, so training and inference see the
same code.

```bash
# Regenerate (re-runs the full verification pipeline) and validate the splits
uv run python scripts/generate_curated_dataset.py
uv run python scripts/validate_dataset.py data/curated.jsonl

# Audit prompt+completion lengths against the training context window
uv run python scripts/audit_tokens.py data/curated.jsonl --max-length 2048
```

## Fine-Tuning (LoRA / QLoRA)

`training/train_lora.py` supports both 4-bit NF4 QLoRA and native fp16 LoRA for
`Qwen/Qwen2.5-Coder-3B-Instruct` (1.5B local fallback, 7B optional on Colab): rank 16 / alpha 32 over all linear layers, `max_length=2048`, three epochs, cosine schedule, gradient checkpointing and best-validation checkpoint selection. Training and inference both render the prompt with `models/prompting.py` and use the Qwen assistant end token, so the adapter is not trained on a different input distribution than it is evaluated on.

```bash
# In the separate CUDA environment: config, token audit, then training
python training/train_lora.py --config configs/training.example.json --dry-run
python training/train_lora.py --config configs/training.local.json
```

The Kaggle Tesla T4 training run completed 60/60 steps (`1:57:24` training loop / `7157.5s` manifest) using **native fp16 LoRA** (`load_in_4bit=false`, `optim=adamw_torch`) because 4-bit loading remained unproven on that container image. Final validation loss on `48/48` records was `0.005797` (`29,933,568 / 3,115,872,256` trainable parameters = `0.9607%`), with `adapter_model.safetensors` SHA-256 `42ae18e5eb26976143077051824e97719222103d4352ca70a24ef1089bb8405f`. Real A–D evaluation results live in `experiments/dataset_test_finetuned_summary.json` (`Group-D-FineTunedMultiAgent`: `refactor_success_rate = 0.9167` vs untuned 3B `Group-A = 0.6042`, `Group-B = 0.7500`).

---

## Comparative Evaluation Harness (FR09, UC04)

Evaluate Groups A–D on the built-in benchmark suite and/or any dataset split:

```bash
# Built-in suite (4 cases: long function, deep nesting, async, complexity)
uv run python -m evaluation.harness --groups A B C D --output-dir experiments

# Dataset test split (--include-code also exports the source for blind human review)
uv run python -m evaluation.harness --dataset data/curated.jsonl --split test \
  --name dataset_test --include-code --output-dir experiments

# Optional: compare against the real base model and use best-of-N AST-only selection
uv run python -m evaluation.harness --baseline base --base-model Qwen/Qwen2.5-Coder-3B-Instruct \
  --candidates 4 --adapter-path runs/lora-first/adapter --groups C D --output-dir experiments

# Blinded review packet -> humans fill score_sheet.csv -> aggregate (refuses to invent ratings)
uv run python scripts/prepare_blind_review.py --results experiments/dataset_test_results.csv \
  --output-dir experiments/review
uv run python scripts/aggregate_blind_review.py --review-dir experiments/review
```

Outputs (per run name):
- `experiments/<name>_results.csv`: case-level records — status/failure type, review verdict,
  syntax/test outcomes, latency, tokens, LOC and complexity deltas, CodeBLEU, AST similarity,
  maintainability-index before/after (plus `original_code`/`refactored_code` with `--include-code`).
- `experiments/<name>_summary.json`: per-group aggregates (acceptance, syntax validity,
  test-pass rate, `smell_resolution_rate`, `refactor_success_rate` with separate findings and
  clean-control breakdowns, execution pass@1, mean CodeBLEU, mean AST similarity, MI
  improvement, complexity reduction, retries, tokens).

Honesty rules (NFR06): groups whose provider/adapter is unavailable emit
`status=provider_unavailable` failure rows with the raw reason and `null` aggregate rates —
never fabricated zeros or 1.0s. CodeBLEU and AST similarity are documented Python variants
(equal-weight CodeBLEU formulation; LCS ratio over annotated preorder nodes); they are
reference-based and reported as measured, not as proof of semantic equivalence.

---

## Documentation Index
- [System Design](docs/architecture/system-design.md)
- [Technical Decisions (ADRs)](docs/architecture/decisions.md)
- [Software Requirements (SRS)](docs/requirements/srs.md)
- [Requirements Traceability](docs/requirements/traceability.md)
- [Evaluation Protocol](docs/evaluation/protocol.md)
- [Team & Workstreams](docs/planning/team.md)
- [Delivery Roadmap](docs/planning/roadmap.md)
- [Setup Guide](docs/development/setup.md)
- [Single-laptop Agent Execution Pack](docs/agent-execution/README.md)
- [Contributing](CONTRIBUTING.md)
- [Agent guidance (AGENTS.md)](AGENTS.md)
