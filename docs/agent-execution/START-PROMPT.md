# START-PROMPT

Copy the block below into a coding agent that has this repository open on a single laptop.

---

You are working inside the private repository `grad-refactor-ai` (Multi-Agent Refactoring for
Python). Begin with **repository inspection**, not a new scaffold.

1. Read root `AGENTS.md`, `README.md`, and everything under `docs/agent-execution/` in the
   order listed in `docs/agent-execution/README.md`.
2. Read `docs/requirements/srs.md`, `docs/architecture/system-design.md`,
   `docs/architecture/decisions.md`, `docs/planning/roadmap.md`, and
   `planning/backlog.json` + `planning/assignments.json`.
3. Inspect the existing `src/` packages (`refactor_ai`, `api`, `core`, `agents`, `models`,
   `runner`, `evaluation`), `tests/`, `scripts/`, `training/`, `configs/` and `frontend/`.
   Run `uv run python scripts/doctor.py` and `uv run pytest`.
4. Perform the **hardware gate** (P1) before designing any training work: record CPU, RAM, GPU,
   VRAM, OS, weekly availability, a measured local inference run, and a tiny LoRA save/reload
   smoke test — or a recorded blocker. Do not assume a free GPU.
5. Copy `docs/agent-execution/execution-state.template.json` to a working file and update it
   after every meaningful step. **Resume from state, not memory.**
6. Implement the ordered steps in `docs/agent-execution/02-execution-plan.md`, keeping actual
   evidence (commands, outputs, links) for each exit condition.
7. Keep the trust boundary: the API process never executes submitted or generated code; any
   test execution stays in the isolated runner and only on trusted examples.
8. Never invent datasets, training runs, successful tests, approvals or citations. If a result
   is absent, write that it is absent.

Stop and record a blocker rather than fabricate progress. Finish with the handover checklist in
`docs/agent-execution/06-acceptance-and-handover.md` for human team inspection.
