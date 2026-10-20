/**
 * TypeScript mirror of src/refactor_ai/contracts.py (schema version 1).
 *
 * Field names, optionality and enum values follow the Pydantic models exactly. Fields
 * declared `X | None` in Python are `X | null` here because the API serializes None as
 * null. src/test/contractMirror.test.ts compares these definitions with contracts.py and
 * src/test/contractExamples.test.ts checks them against docs/architecture/examples/.
 */

export const SCHEMA_VERSION = 1;
/** RunCreateRequest.code max_length in contracts.py (characters, i.e. code points). */
export const MAX_CODE_CHARS = 20_000;
/** Task scope limits from src/refactor_ai/tasks/guard_clauses.py (task version 1). */
export const TASK_MAX_CHARS = 3_000;
export const TASK_MAX_LINES = 60;
export const TASK_TYPE = "guard_clauses";
/** GET /api/v1/runs limit bounds from docs/architecture/contracts.md. */
export const RUN_LIST_DEFAULT_LIMIT = 20;
export const RUN_LIST_MAX_LIMIT = 50;

export type Iso8601 = string;

export const PROVIDER_MODES = ["fake", "local_model"] as const;
export type ProviderMode = (typeof PROVIDER_MODES)[number];

export const ROLES = ["analysis", "refactor", "review"] as const;
export type Role = (typeof ROLES)[number];

export const WORKFLOW_MODES = ["multi_role", "single_role"] as const;
export type WorkflowMode = (typeof WORKFLOW_MODES)[number];

export const RUN_STATUSES = [
  "queued",
  "analyzing",
  "generating",
  "verifying",
  "completed",
  "failed",
] as const;
export type RunStatus = (typeof RUN_STATUSES)[number];

export const TERMINAL_STATUSES = ["completed", "failed"] as const satisfies readonly RunStatus[];

export const DISPOSITIONS = [
  "proposal_ready",
  "rejected",
  "uncertain",
  "no_change",
  "failed",
] as const;
export type Disposition = (typeof DISPOSITIONS)[number];

export const PROVIDER_ERROR_CODES = [
  "timeout",
  "model_load_error",
  "input_too_long",
  "generation_error",
  "busy",
  "unavailable",
] as const;
export type ProviderErrorCode = (typeof PROVIDER_ERROR_CODES)[number];

export const HUMAN_DECISIONS = ["accepted", "rejected"] as const;
export type HumanDecision = (typeof HUMAN_DECISIONS)[number];

export const REVIEW_VERDICTS = ["accept", "reject", "uncertain"] as const;
export type ReviewVerdict = (typeof REVIEW_VERDICTS)[number];

export const SYNTAX_STATUSES = ["pass", "fail", "not_run"] as const;
export type SyntaxStatus = (typeof SYNTAX_STATUSES)[number];

export const RUBRIC_STATUSES = ["pass", "fail", "not_run"] as const;
export type RubricStatus = (typeof RUBRIC_STATUSES)[number];

export const REFERENCE_TEST_STATUSES = [
  "pass",
  "fail",
  "not_available",
  "not_run",
  "error",
] as const;
export type ReferenceTestsStatus = (typeof REFERENCE_TEST_STATUSES)[number];

export const MODEL_REVIEW_STATUSES = ["accept", "reject", "uncertain", "error", "not_run"] as const;
export type ModelReviewStatus = (typeof MODEL_REVIEW_STATUSES)[number];

export const REFERENCE_FAILURE_KINDS = [
  "wrong_value",
  "wrong_exception",
  "unexpected_exception",
  "missing_exception",
  "timeout",
  "missing_function",
  "runner_error",
] as const;
export type ReferenceTestFailureKind = (typeof REFERENCE_FAILURE_KINDS)[number];

export const STAGES = ["validation", "analysis", "generation", "review", "verification"] as const;
export type Stage = (typeof STAGES)[number];

export const ANALYSIS_SOURCES = ["model", "static"] as const;
export type AnalysisSource = (typeof ANALYSIS_SOURCES)[number];

// --- Model provider -------------------------------------------------------------------

export interface GenerationConfig {
  max_new_tokens: number;
  temperature: number;
  top_p: number;
  seed: number;
  max_input_tokens: number;
  timeout_s: number;
}

export interface ModelReference {
  model_id: string;
  model_revision: string;
  adapter_id: string | null;
  adapter_sha256: string | null;
  use_adapter: boolean;
}

export interface ProviderInfo {
  provider_mode: ProviderMode;
  model_id: string | null;
  model_revision: string | null;
  adapter_id: string | null;
  adapter_sha256: string | null;
  device: string | null;
  ready: boolean;
  detail: string | null;
}

// --- Role outputs ---------------------------------------------------------------------

export interface RoleFinding {
  type: string;
  start_line: number;
  end_line: number;
  reason: string;
}

export interface AnalysisReport {
  schema_version: number;
  supported_task: boolean;
  findings: RoleFinding[];
  unsupported_reason: string | null;
  source: AnalysisSource;
}

export interface ReviewResult {
  schema_version: number;
  verdict: ReviewVerdict;
  reasons: string[];
  suggested_correction: string | null;
}

// --- Verification ---------------------------------------------------------------------

export interface SyntaxCheck {
  status: SyntaxStatus;
  error: string | null;
}

export interface RubricCheck {
  status: RubricStatus;
  checks: Record<string, boolean>;
  reasons: string[];
}

export interface ReferenceTestFailure {
  index: number;
  kind: ReferenceTestFailureKind;
  detail: string;
}

export interface ReferenceTestsResult {
  status: ReferenceTestsStatus;
  case_id: string | null;
  total: number | null;
  passed: number | null;
  failed: number | null;
  errored: number | null;
  reason: string | null;
  duration_s: number | null;
  failures: ReferenceTestFailure[];
}

export interface ModelReviewResult {
  status: ModelReviewStatus;
  reasons: string[];
  error: string | null;
}

export interface VerificationResult {
  syntax: SyntaxCheck;
  rubric: RubricCheck;
  reference_tests: ReferenceTestsResult;
  model_review: ModelReviewResult;
  disposition: Disposition;
  disposition_reasons: string[];
}

export interface RunnerInfo {
  enabled: boolean;
  reason: string | null;
  isolation: Record<string, boolean>;
}

// --- Workflow and run records ---------------------------------------------------------

export interface WorkflowSettings {
  mode: WorkflowMode;
  refactor_use_adapter: boolean;
  max_calls: number;
  max_corrections: number;
  run_timeout_s: number;
  generation: Partial<Record<Role, GenerationConfig>>;
}

export interface StageTiming {
  stage: Stage;
  attempt: number;
  started_at: Iso8601;
  elapsed_s: number;
  calls: number;
}

export interface AttemptRecord {
  attempt: number;
  raw_output: string | null;
  parse_error: string | null;
  parse_repaired: boolean;
  proposed_code: string | null;
  explanation: string | null;
  verification: VerificationResult | null;
  review: ReviewResult | null;
  model: ModelReference | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  elapsed_s: number | null;
}

export interface RunError {
  code: string;
  message: string;
  /** Free text in the contract: a stage name ("generation") or a run status ("generating"). */
  stage: string | null;
}

export interface RunRecord {
  schema_version: number;
  run_id: string;
  created_at: Iso8601;
  started_at: Iso8601 | null;
  finished_at: Iso8601 | null;
  status: RunStatus;
  task_type: string;
  workflow_mode: WorkflowMode;
  reference_case_id: string | null;
  original_code: string;
  proposed_code: string | null;
  provider_mode: ProviderMode;
  model: ModelReference | null;
  settings: WorkflowSettings;
  attempt_count: number;
  call_count: number;
  stage_timings: StageTiming[];
  analysis: AnalysisReport | null;
  findings: RoleFinding[];
  explanation: string | null;
  diff: string | null;
  changed_lines: number[];
  review: ReviewResult | null;
  verification: VerificationResult | null;
  attempts: AttemptRecord[];
  stop_reason: string | null;
  error: RunError | null;
  warnings: string[];
  human_decision: HumanDecision | null;
}

// --- HTTP API -------------------------------------------------------------------------

/** Request body; fields with a Pydantic default are optional. The client sends all four. */
export interface RunCreateRequest {
  code: string;
  task_type?: typeof TASK_TYPE;
  workflow_mode?: WorkflowMode;
  reference_case_id?: string | null;
}

export interface RunAccepted {
  run_id: string;
  status: RunStatus;
  poll_url: string;
}

export interface RunSummary {
  run_id: string;
  created_at: Iso8601;
  finished_at: Iso8601 | null;
  status: RunStatus;
  disposition: Disposition | null;
  task_type: string;
  workflow_mode: WorkflowMode;
  provider_mode: ProviderMode;
  reference_case_id: string | null;
  human_decision: HumanDecision | null;
}

export interface RunList {
  runs: RunSummary[];
  limit: number;
}

export interface DecisionRequest {
  decision: HumanDecision;
}

export interface ReferenceCaseSummary {
  case_id: string;
  title: string | null;
  function_name: string;
  code: string;
  test_count: number;
}

export interface QueueInfo {
  max_pending: number;
  pending: number;
}

export interface HealthResponse {
  status: "ok";
  version: string;
  mode: ProviderMode;
  provider: ProviderInfo;
  runner: RunnerInfo;
  queue: QueueInfo;
  /** True when the refactoring role uses the LoRA adapter; analysis and review use the base model. */
  refactor_use_adapter: boolean;
}

export interface ErrorDetail {
  code: string;
  message: string;
  details: Array<Record<string, unknown>> | null;
}

export interface ErrorResponse {
  error: ErrorDetail;
}

// --- Small helpers shared by the UI ----------------------------------------------------

function includes<T extends string>(values: readonly T[], value: unknown): value is T {
  return typeof value === "string" && (values as readonly string[]).includes(value);
}

export const isRunStatus = (value: unknown): value is RunStatus => includes(RUN_STATUSES, value);
export const isProviderMode = (value: unknown): value is ProviderMode =>
  includes(PROVIDER_MODES, value);
export const isWorkflowMode = (value: unknown): value is WorkflowMode =>
  includes(WORKFLOW_MODES, value);
export const isDisposition = (value: unknown): value is Disposition =>
  includes(DISPOSITIONS, value);

export function isTerminalStatus(status: RunStatus): boolean {
  return (TERMINAL_STATUSES as readonly RunStatus[]).includes(status);
}

/**
 * Mirrors proposal_problem() in src/refactor_ai/runs/records.py: a proposal can be
 * downloaded or decided on once the run has completed with non-empty proposed code,
 * whatever the disposition.
 */
export function hasProposal(record: Pick<RunRecord, "status" | "proposed_code">): boolean {
  return (
    record.status === "completed" &&
    typeof record.proposed_code === "string" &&
    record.proposed_code.length > 0
  );
}
