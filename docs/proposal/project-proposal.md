# Project proposal

**Working title:** Multi-Agent Refactoring for Python  
**Status:** planning draft for supervisor review  
**Initial delivery window:** three weeks from the agreed team start date

## Problem

Refactoring requires more than producing code that looks cleaner. A useful change must address a specific structural problem and preserve the program's intended behavior. Language models can propose changes that are unnecessary, invalid, or behaviorally incorrect. This project investigates whether separating analysis, modification, and review into coordinated roles improves the reliability of a small refactoring workflow.

The intended user is a student or developer reviewing a small Python function or file. The system will present a proposed change and the evidence available to assess it. It will not modify the user's original files automatically.

## Proposed approach

An analysis agent identifies a supported refactoring opportunity. A refactoring agent proposes a change. A review agent examines the change alongside deterministic checks. The interface presents the original and proposed code, a diff, an explanation, and separate verification results.

The roles may share one underlying code model. The team will fine-tune an existing open-weight model for a narrowly defined refactoring task, initially targeting the modification role. The original model will remain available as a baseline. Expanding fine-tuning to other roles depends on the feasibility results and available time.

## Objectives

- Deliver a reproducible, locally runnable workflow for selected Python refactorings.
- Prepare a documented dataset with source-level separation between training, validation, and test sets.
- Run a traceable fine-tuning experiment and retain the adapter and configuration.
- Measure the effects of fine-tuning and agent coordination separately.
- Report failure cases, resource use, and limitations as well as successful examples.

## First-release scope

The first release accepts one small Python function of at most 3,000 characters and 60 lines. The proposed refactoring type, pending the first supervisor review, is Fowler's "Replace Nested Conditional with Guard Clauses": a conditional branch that always returns or raises becomes an early exit when that lowers the nesting depth. Its inclusion and exclusion rules, before and after examples with reference tests, rubric and limits are defined in the [task scope](../requirements/task-scope.md). Inputs outside that scope are answered with an explicit "no change" and a reason, without a model call. The interface will support input, inspection of the proposed change, verification results, and explicit user acceptance or rejection.

Paid model APIs and paid hosting are outside the budget. Public deployment is not required for the initial delivery. Test execution is restricted to trusted demonstration cases owned by the service, run in a separate, resource-limited process that stays disabled when its isolation self-checks fail.

Training a language model from scratch, supporting multiple languages or large repositories, automatically changing GitHub branches, and guaranteeing behavioral equivalence for all programs are outside this release.

## Research questions

1. Does a coordinated analysis, modification, and review workflow produce more acceptable refactorings than a single-agent workflow on the selected tasks?
2. How does task-specific fine-tuning change performance relative to the original model?
3. What quality improvements, if any, justify the additional inference time and resource use?

The proposed contribution is an empirical study of this bounded workflow. Improvement is a hypothesis, not a promised result. Dataset preparation, reproducibility, and failure analysis are part of the contribution. The supervisor will confirm whether the proposed scope meets the department's academic requirements.

## Deliverables and success criteria

Deliverables are a working end-to-end prototype, documented data preparation, a recorded fine-tuning experiment, an evaluation report, developer and user documentation, and a presentation with a repeatable demonstration.

Prototype completion is assessed against the agreed acceptance criteria. Research findings are assessed through the evaluation protocol, including negative results. Numerical performance targets will be recorded after the baseline study and before the final test set is evaluated.

## Resources and supervision

The team has five members with similar reported experience. The repository owner coordinates the work. Hardware and weekly availability will be recorded at kickoff. Each phase ends with a supervisor review, written decisions, and follow-up Issues.

## Decisions for the first supervisor review

Confirm the problem and proposed contribution; select the refactoring types; review the training resources; confirm the university report template and official dates; and agree on the evaluation approach.
