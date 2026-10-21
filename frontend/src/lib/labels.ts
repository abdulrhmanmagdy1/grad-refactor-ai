/**
 * Words, tones and icons for every status the service reports. Keeping them in one table
 * makes the rule "missing evidence never looks like a pass" checkable in tests: only
 * pass/accept use the "pass" tone, and not_available, not_run and error are marked as
 * absent evidence, which the stylesheet draws hatched.
 */

import type {
  Disposition,
  ModelReviewStatus,
  ProviderMode,
  ReferenceTestFailureKind,
  ReferenceTestsStatus,
  Role,
  RubricStatus,
  RunStatus,
  Stage,
  SyntaxStatus,
  WorkflowMode,
} from "../api/contracts";

export type Tone = "pass" | "fail" | "warn" | "neutral" | "info" | "progress";
export type Evidence = "present" | "absent";
export type IconName = "check" | "cross" | "dash" | "absent" | "alert" | "question" | "clock" | "spinner";

export interface StatusMeta {
  label: string;
  tone: Tone;
  icon: IconName;
  evidence: Evidence;
}

export const TASK_LABEL = "Flatten nested if statements (guard clauses)";
export const FAKE_PREFIX = "FAKE PROVIDER (not a model):";

export const RUN_STATUS_META: Record<RunStatus, { label: string; tone: Tone; activity: string }> = {
  queued: { label: "Queued", tone: "neutral", activity: "Waiting to start." },
  analyzing: { label: "Analyzing", tone: "progress", activity: "Finding nested if statements." },
  generating: { label: "Rewriting", tone: "progress", activity: "Writing the new code." },
  verifying: { label: "Checking", tone: "progress", activity: "Checking the new code." },
  completed: { label: "Done", tone: "info", activity: "Finished." },
  failed: { label: "Failed", tone: "fail", activity: "Stopped with an error." },
};

export interface DispositionMeta {
  label: string;
  title: string;
  summary: string;
  tone: Tone;
  icon: IconName;
}

export const DISPOSITION_META: Record<Disposition, DispositionMeta> = {
  proposal_ready: {
    label: "Ready",
    title: "Ready to use",
    summary: "All checks passed. Read the change before you accept it.",
    tone: "pass",
    icon: "check",
  },
  rejected: {
    label: "Not safe",
    title: "Not safe to use",
    summary: "A check failed. Do not use this change.",
    tone: "fail",
    icon: "cross",
  },
  uncertain: {
    label: "Not sure",
    title: "Not sure",
    summary: "Nothing failed, but some checks could not run.",
    tone: "warn",
    icon: "question",
  },
  no_change: {
    label: "No change",
    title: "Nothing to change",
    summary: "The tool cannot improve this code.",
    tone: "neutral",
    icon: "dash",
  },
  failed: {
    label: "Failed",
    title: "Something went wrong",
    summary: "The run stopped before it made a change.",
    tone: "fail",
    icon: "alert",
  },
};

const PASSED: StatusMeta = { label: "Passed", tone: "pass", icon: "check", evidence: "present" };
const FAILED: StatusMeta = { label: "Failed", tone: "fail", icon: "cross", evidence: "present" };
const NOT_RUN: StatusMeta = { label: "Not checked", tone: "neutral", icon: "dash", evidence: "absent" };
const ERRORED: StatusMeta = { label: "Could not check", tone: "warn", icon: "alert", evidence: "absent" };

export const SYNTAX_META: Record<SyntaxStatus, StatusMeta> = {
  pass: PASSED,
  fail: FAILED,
  not_run: NOT_RUN,
};

export const RUBRIC_META: Record<RubricStatus, StatusMeta> = {
  pass: PASSED,
  fail: FAILED,
  not_run: NOT_RUN,
};

export const REFERENCE_TESTS_META: Record<ReferenceTestsStatus, StatusMeta> = {
  pass: PASSED,
  fail: FAILED,
  not_available: { label: "No tests", tone: "neutral", icon: "absent", evidence: "absent" },
  not_run: NOT_RUN,
  error: ERRORED,
};

export const MODEL_REVIEW_META: Record<ModelReviewStatus, StatusMeta> = {
  accept: { label: "Accepted", tone: "pass", icon: "check", evidence: "present" },
  reject: { label: "Rejected", tone: "fail", icon: "cross", evidence: "present" },
  uncertain: { label: "Not sure", tone: "warn", icon: "question", evidence: "present" },
  error: ERRORED,
  not_run: NOT_RUN,
};

/** Labels for the rubric checks in src/refactor_ai/tasks/guard_clauses.py (RUBRIC_CHECKS). */
export const RUBRIC_CHECK_LABELS: Record<string, string> = {
  parses_as_single_function: "Parses as a single function",
  same_name: "Keeps the function name",
  same_signature: "Keeps the parameters and return annotation",
  same_docstring: "Keeps the docstring",
  within_task_constraints: "Stays within the task constraints",
  nesting_reduced: "Reduces the nesting depth",
  has_guard_clause: "Contains a guard clause",
  no_new_calls: "Introduces no new calls",
};

export function humanize(identifier: string): string {
  const words = identifier.replace(/[_-]+/g, " ").trim();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : identifier;
}

export function rubricCheckLabel(name: string): string {
  return RUBRIC_CHECK_LABELS[name] ?? humanize(name);
}

export const FAILURE_KIND_LABELS: Record<ReferenceTestFailureKind, string> = {
  wrong_value: "Wrong return value",
  wrong_exception: "Wrong exception type",
  unexpected_exception: "Unexpected exception",
  missing_exception: "Expected exception not raised",
  timeout: "Timed out",
  missing_function: "Function not found",
  runner_error: "Runner error",
};

export const STAGE_LABELS: Record<Stage, string> = {
  validation: "Validation",
  analysis: "Analysis",
  generation: "Generation",
  review: "Review",
  verification: "Verification",
};

export const WORKFLOW_META: Record<WorkflowMode, { label: string; description: string }> = {
  multi_role: {
    label: "With review",
    description: "Find, rewrite, then review. Slower.",
  },
  single_role: {
    label: "Fast",
    description: "One rewrite step. Faster.",
  },
};

export const PROVIDER_LABELS: Record<ProviderMode, string> = {
  fake: "Demo mode (no AI model)",
  local_model: "AI model",
};

/** Explanations for RunRecord.error codes written by the service, workflow and provider. */
const RUN_ERROR_HINTS: Record<string, string> = {
  interrupted:
    "The service stopped while this run was waiting or running. Runs are never restarted automatically.",
  timeout: "The model did not finish within its time limit.",
  model_load_error: "The model or its adapter could not be loaded.",
  input_too_long: "The prompt was longer than the model's input limit.",
  generation_error: "The model failed while generating text.",
  busy: "The model was busy with another request.",
  unavailable: "The model provider is not available.",
  internal_error: "The service hit an unexpected error; the server log has the details.",
  workflow_unavailable: "The refactoring workflow is not available on the server.",
  adapter_unavailable: "The fine-tuned model is missing, so nothing ran.",
};

export function runErrorHint(code: string): string | null {
  return RUN_ERROR_HINTS[code] ?? null;
}

/** RunRecord.stop_reason values written by src/refactor_ai/agents/coordinator.py. */
export const STOP_REASON_LABELS: Record<string, string> = {
  unsupported_input: "Input outside the supported task (no model call)",
  single_role_complete: "Single-role run verified",
  no_correction_needed: "No correction needed",
  correction_used: "The one correction was made and verified",
  correction_disabled: "A correction was needed but corrections are disabled",
  call_budget_exhausted: "A correction was needed but the call budget was used up",
  correction_input_too_long:
    "Correction skipped: its prompt exceeded the refactoring role's input limit, so the first proposal is reported",
  provider_error: "Model provider error",
  run_timeout: "The run reached its time limit",
  unparseable_output: "The model output could not be parsed",
  invalid_settings: "Invalid workflow settings",
  reference_case_mismatch: "The code did not match the reference case",
  internal_error: "Internal error",
};

export function stopReasonLabel(code: string): string {
  return STOP_REASON_LABELS[code] ?? humanize(code);
}

export const ROLE_LABELS: Record<Role, string> = {
  analysis: "Analysis",
  refactor: "Refactoring",
  review: "Review",
};

export type ActiveRunStatus = Exclude<RunStatus, "completed" | "failed">;

/**
 * Maps RunError.stage to a progress step. The field is free text: the workflow writes
 * stage names ("generation") and startup recovery writes run statuses ("generating").
 */
export function stepForStage(stage: string | null | undefined): ActiveRunStatus | null {
  switch (stage) {
    case "queued":
    case "validation":
      return "queued";
    case "analysis":
    case "analyzing":
      return "analyzing";
    case "generation":
    case "generating":
      return "generating";
    case "review":
    case "verification":
    case "verifying":
      return "verifying";
    default:
      return null;
  }
}

/** Texts for the task's reason codes (REASON_TEXT in guard_clauses.py). */
export const TASK_REASON_TEXT: Record<string, string> = {
  syntax_error: "The input is not valid Python.",
  too_long: "The input exceeds 3000 characters or 60 lines.",
  not_single_function: "The input must contain exactly one top-level function only.",
  async_function: "Async functions are outside the supported scope.",
  decorated_function: "Decorated functions are outside the supported scope.",
  generator_function: "Generator functions are outside the supported scope.",
  nested_definition: "Nested functions or classes are outside the supported scope.",
  imports_present: "Imports are outside the supported scope.",
  global_or_nonlocal: "global and nonlocal statements are outside the supported scope.",
  try_or_with_present: "try and with blocks are outside the supported scope.",
  match_present: "match statements are outside the supported scope.",
  dunder_access: "Access to double-underscore names is outside the supported scope.",
  no_opportunity: "No nested conditional can be flattened with guard clauses.",
  too_complex: "The input is nested too deeply to analyze.",
};

export interface ReasonParts {
  code: string | null;
  text: string;
}

const CODED_REASON = /^([a-z][a-z0-9_]*(?::[A-Za-z0-9_.]+)?):\s+([\s\S]+)$/;
const BARE_CODE = /^([a-z][a-z0-9_]*)(?::([A-Za-z0-9_.]+))?$/;

/**
 * Splits "code: explanation" reasons (for example "no_opportunity: No nested ...") and
 * expands bare task reason codes. Plain sentences are returned unchanged.
 */
export function splitReason(reason: string): ReasonParts {
  const trimmed = reason.trim();
  const coded = CODED_REASON.exec(trimmed);
  if (coded?.[1] && coded[2]) return { code: coded[1], text: coded[2] };
  const bare = BARE_CODE.exec(trimmed);
  if (bare?.[1]) {
    if (bare[1] === "denied_call" && bare[2]) {
      return { code: trimmed, text: `Calls to ${bare[2]}() are outside the supported scope.` };
    }
    const text = TASK_REASON_TEXT[bare[1]];
    if (text && !bare[2]) return { code: trimmed, text };
  }
  return { code: null, text: trimmed };
}

export function isFakeText(text: string | null | undefined): boolean {
  return typeof text === "string" && text.trimStart().startsWith(FAKE_PREFIX);
}
