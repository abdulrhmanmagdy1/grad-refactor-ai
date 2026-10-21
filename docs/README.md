# Documentation index

These documents describe the Multi-Agent Refactoring for Python project: what it must do, how the implemented system works, how it is built and checked, and how the research comparison is run. The service, the web interface, the dataset and the evaluation harness are implemented, the LoRA adapter is trained, and arms A to D have been compared once on the frozen test split; the [report](report/report.md) presents the results. Each document says which parts are implemented, measured or still planned. The [project README](../README.md) gives the current status and the quickstart.

## Start here

| Document | Main use |
|---|---|
| [User guide](delivery/user-guide.md) | Start the service; use the web interface and the API; read the results, dispositions and errors |
| [Environment setup](development/setup.md) | Reproduce the development environment, run the service and its checks |
| [First day](development/first-day.md) | Join the workspace and start contributing |

## Requirements and scope

| Document | Main use |
|---|---|
| [Project proposal](proposal/project-proposal.md) | Problem, research questions, scope and contribution |
| [Requirements](requirements/srs.md) | Functional and non-functional requirements and acceptance criteria |
| [Task scope](requirements/task-scope.md) | The single supported refactoring, `guard_clauses`: inclusion rules, reason codes, examples and the rubric |

## Architecture

| Document | Main use |
|---|---|
| [System design](architecture/system-design.md) | Proposed components and runtime behavior, written before the implementation; the contracts and the workflow page describe the implemented system |
| [Component contracts](architecture/contracts.md) | Authoritative fields, rules, error codes and settings (schema version 1) |
| [Workflow coordinator and verification](architecture/workflow.md) | Sequence, budgets, parsing, prompts, dispositions and token budgets |
| [Decision log](architecture/decisions.md) | Technical choices and trade-offs (ADRs) |
| [Example JSON](architecture/examples/README.md) | Real request, response, health and run-record examples generated from the contracts |

## Development

| Document | Main use |
|---|---|
| [Environment setup](development/setup.md) | Core environment, settings, run API and checks before a pull request |
| [Frontend development](development/frontend.md) | Toolchain, scripts, tests and building the web interface |
| [Testing](development/testing.md) | Test commands, what the suites cover, CI and the clean-clone record |
| [Runner safety](development/runner-safety.md) | How trusted reference tests are isolated, the self-checks and their honest limits |

## Data, training and evaluation

| Document | Main use |
|---|---|
| [Data plan](data-and-training/data-plan.md) | Sources, curation, reference tests, splits, leakage checks and the test-split freeze |
| [Dataset notice](../datasets/guard_clauses/v1/NOTICE.md) | Licenses and attribution of the `guard_clauses` v1 records |
| [Training plan](data-and-training/training-plan.md) | Training environment, LoRA configuration, preparation and selection |
| [Kaggle lane](../training/kaggle/README.md) | Running training and validation evaluations on Kaggle's free GPU with checksummed results |
| [Model card](data-and-training/model-card.md) | Model and adapter provenance, checksums, intended use, test results and limitations |
| [Evaluation protocol](evaluation/protocol.md) | Arms A to D, measures, statistics and the freezing procedure |
| [Project review benchmark](evaluation/project-benchmark.md) | Seeded projects, scoring rules and freeze for the whole-project mode |
| [Experiment records](../experiments/README.md) | Committed records: [hardware](../experiments/hardware/2026-10-20-demonstration-laptop.json), [data](../experiments/data/manual-inspection-2026-10-20.md), [models](../experiments/models/README.md), [training](../experiments/training/README.md), the [test-split evaluation](../experiments/evaluation/test-2026-10-21/targets-report/summary.md) and the [clean-clone reproduction](../experiments/qa/2026-10-21-clean-clone-reproduction.md) |

## Report material

| Document | Main use |
|---|---|
| [Report](report/report.md) | The graduation report draft with the final results |
| [Backend notes](report/notes/backend.md) | Run API, storage, recovery, errors and their evidence |
| [Workflow notes](report/notes/workflow.md) | Coordinator, verification, demonstration cases and their evidence |
| [Model notes](report/notes/model.md) | Model choice, benchmark, local provider and LoRA work |
| [Data and evaluation notes](report/notes/data-evaluation.md) | Dataset, splits and the evaluation harness |
| [Frontend notes](report/notes/frontend.md) | Interface design decisions, states and test evidence |
| [Screenshots](report/screenshots/) | 26 interface screenshots taken on 2026-10-21 with the fine-tuned model, light and dark, desktop and phone |
| [Related work](research/related-work.md) | Literature review and reading table |
| [References](references.md) | Methodology and tool sources |

## Delivery

| Document | Main use |
|---|---|
| [User guide](delivery/user-guide.md) | Use the web interface and the API |
| [Delivery checklist](delivery/checklist.md) | Prepare the release, report and demonstration |
| [Implementation handover](delivery/implementation-handover.md) | Commands, component map, results, known defects and what each owner inspects |
| [Acceptance matrix](delivery/acceptance-matrix.md) and [acceptance status](delivery/acceptance-status.md) | Each requirement and checklist item traced to its evidence |
| [Slides](delivery/slides/grad-refactor-ai-presentation.pptx), [presentation outline](delivery/presentation-outline.md) and [demonstration script](delivery/demo-script.md) | The presentation, likely questions and the live demonstration |
| [Acceptance and handover](agent-execution/06-acceptance-and-handover.md) | What each workstream must show before delivery is accepted |

## Planning and team

| Document | Main use |
|---|---|
| [Roadmap](planning/roadmap.md) | Phases, outcomes and supervisor reviews of the 21-day plan |
| [Team](planning/team.md) | Members and responsibilities |
| [Assignments](planning/assignments.md) | Each task's owner |
| [Tasks by owner](planning/by-owner.md) | All tasks for each person in one row |
| [Task index](planning/task-index.md) | Links to the GitHub Issues |
| [Risks](planning/risks.md) | Risks and responses |
| [GitHub workspace](planning/github-workspace.md) | The board, access settings and notifications |
| [Initial planning data](../planning/README.md) | Task and assignment data used to create the Issues |

## Supervisor reviews

| Document | Main use |
|---|---|
| [Supervisor reviews](supervisor-reviews/README.md) | How to prepare a review and record its decisions |
| [Review template](supervisor-reviews/review-template.md) | The form for each review |
| [R1 review pack: scope and feasibility](supervisor-reviews/r1-scope-and-feasibility.md) | Prepared by the team; the meeting has not taken place |
| [R2 review pack: data and baseline](supervisor-reviews/r2-data-and-baseline.md) | Prepared by the team; the meeting has not taken place |
| [R3 review pack: integration and first training run](supervisor-reviews/r3-integration-and-training.md) | Prepared by the team; the meeting has not taken place |
| [R4 review pack: integrated first release](supervisor-reviews/r4-first-release.md) | Prepared by the team; the meeting has not taken place |

## Optional agent execution pack

| Document | Main use |
|---|---|
| [Agent execution pack](agent-execution/README.md) | Implement or resume the project on one laptop with one coding agent per workstream |
| [Start prompt](agent-execution/START-PROMPT.md) | The prompt that starts an execution session |
| [01 Project brief](agent-execution/01-project-brief.md) | Goal, scope and constraints for the agents |
| [02 Execution plan](agent-execution/02-execution-plan.md) | Order of work and checkpoints |
| [03 Component contracts](agent-execution/03-component-contracts.md) | Starting contracts proposed before T11; the [component contracts](architecture/contracts.md) supersede them |
| [04 Data, model and evaluation](agent-execution/04-data-model-evaluation.md) | Data, training and evaluation rules for the agents |
| [05 Working and recovery](agent-execution/05-working-and-recovery.md) | Working rules, checkpoints and recovery |
| [06 Acceptance and handover](agent-execution/06-acceptance-and-handover.md) | Acceptance checks and handover to the students |
| [Team allocation](agent-execution/team-allocation.md) | One coding agent per workstream and its owner |

The execution state files [execution-state.json](agent-execution/execution-state.json) and [execution-state.template.json](agent-execution/execution-state.template.json) record checkpoints of an execution session.

## PDF editions

- [Complete project documentation](pdf/01-project-documentation.pdf)
- [Team delivery plan](pdf/02-team-delivery-plan.pdf)
- [Edition notes](pdf/README.md)

The PDFs are version 0.3 planning snapshots written before the implementation. The source documents above, the Issues and the Project board are the current references.

## Repository-level documents

- [Project README](../README.md): status, quickstart, layout and team
- [Contribution workflow](../CONTRIBUTING.md)
- [Instructions for coding agents](../AGENTS.md)
- [Licensing notice](../NOTICE.md)

Update the affected documents in the same pull request as a behavior or API change. Review the documentation at every phase boundary. The coordinator maintains the overall structure; each task owner maintains the technical content they change.
