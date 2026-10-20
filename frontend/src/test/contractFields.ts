/**
 * Field names of every contract model the frontend mirrors. fieldsOf<T>() only compiles
 * when the list names every property of T and nothing else, so these lists are exactly
 * the TypeScript interfaces; contractMirror.test.ts then compares them with contracts.py.
 */

import type * as C from "../api/contracts";

type MissingKeys<T, K extends readonly PropertyKey[]> = Exclude<keyof T, K[number]>;

function fieldsOf<T>() {
  return <const K extends readonly (keyof T)[]>(
    keys: K,
    ..._missing: [MissingKeys<T, K>] extends [never] ? [] : [missing: MissingKeys<T, K>]
  ): readonly string[] => keys as readonly string[];
}

export const CONTRACT_FIELDS = {
  GenerationConfig: fieldsOf<C.GenerationConfig>()([
    "max_new_tokens",
    "temperature",
    "top_p",
    "seed",
    "max_input_tokens",
    "timeout_s",
  ]),
  ModelReference: fieldsOf<C.ModelReference>()([
    "model_id",
    "model_revision",
    "adapter_id",
    "adapter_sha256",
    "use_adapter",
  ]),
  ProviderInfo: fieldsOf<C.ProviderInfo>()([
    "provider_mode",
    "model_id",
    "model_revision",
    "adapter_id",
    "adapter_sha256",
    "device",
    "ready",
    "detail",
  ]),
  RoleFinding: fieldsOf<C.RoleFinding>()(["type", "start_line", "end_line", "reason"]),
  AnalysisReport: fieldsOf<C.AnalysisReport>()([
    "schema_version",
    "supported_task",
    "findings",
    "unsupported_reason",
    "source",
  ]),
  ReviewResult: fieldsOf<C.ReviewResult>()(["schema_version", "verdict", "reasons", "suggested_correction"]),
  SyntaxCheck: fieldsOf<C.SyntaxCheck>()(["status", "error"]),
  RubricCheck: fieldsOf<C.RubricCheck>()(["status", "checks", "reasons"]),
  ReferenceTestFailure: fieldsOf<C.ReferenceTestFailure>()(["index", "kind", "detail"]),
  ReferenceTestsResult: fieldsOf<C.ReferenceTestsResult>()([
    "status",
    "case_id",
    "total",
    "passed",
    "failed",
    "errored",
    "reason",
    "duration_s",
    "failures",
  ]),
  ModelReviewResult: fieldsOf<C.ModelReviewResult>()(["status", "reasons", "error"]),
  VerificationResult: fieldsOf<C.VerificationResult>()([
    "syntax",
    "rubric",
    "reference_tests",
    "model_review",
    "disposition",
    "disposition_reasons",
  ]),
  RunnerInfo: fieldsOf<C.RunnerInfo>()(["enabled", "reason", "isolation"]),
  WorkflowSettings: fieldsOf<C.WorkflowSettings>()([
    "mode",
    "refactor_use_adapter",
    "max_calls",
    "max_corrections",
    "run_timeout_s",
    "generation",
  ]),
  StageTiming: fieldsOf<C.StageTiming>()(["stage", "attempt", "started_at", "elapsed_s", "calls"]),
  AttemptRecord: fieldsOf<C.AttemptRecord>()([
    "attempt",
    "raw_output",
    "parse_error",
    "parse_repaired",
    "proposed_code",
    "explanation",
    "verification",
    "review",
    "model",
    "prompt_tokens",
    "completion_tokens",
    "elapsed_s",
  ]),
  RunError: fieldsOf<C.RunError>()(["code", "message", "stage"]),
  RunRecord: fieldsOf<C.RunRecord>()([
    "schema_version",
    "run_id",
    "created_at",
    "started_at",
    "finished_at",
    "status",
    "task_type",
    "workflow_mode",
    "reference_case_id",
    "original_code",
    "proposed_code",
    "provider_mode",
    "model",
    "settings",
    "attempt_count",
    "call_count",
    "stage_timings",
    "analysis",
    "findings",
    "explanation",
    "diff",
    "changed_lines",
    "review",
    "verification",
    "attempts",
    "stop_reason",
    "error",
    "warnings",
    "human_decision",
  ]),
  RunCreateRequest: fieldsOf<C.RunCreateRequest>()(["code", "task_type", "workflow_mode", "reference_case_id"]),
  RunAccepted: fieldsOf<C.RunAccepted>()(["run_id", "status", "poll_url"]),
  RunSummary: fieldsOf<C.RunSummary>()([
    "run_id",
    "created_at",
    "finished_at",
    "status",
    "disposition",
    "task_type",
    "workflow_mode",
    "provider_mode",
    "reference_case_id",
    "human_decision",
  ]),
  RunList: fieldsOf<C.RunList>()(["runs", "limit"]),
  DecisionRequest: fieldsOf<C.DecisionRequest>()(["decision"]),
  ReferenceCaseSummary: fieldsOf<C.ReferenceCaseSummary>()(["case_id", "title", "function_name", "code", "test_count"]),
  QueueInfo: fieldsOf<C.QueueInfo>()(["max_pending", "pending"]),
  HealthResponse: fieldsOf<C.HealthResponse>()([
    "status",
    "version",
    "mode",
    "provider",
    "runner",
    "queue",
    "refactor_use_adapter",
  ]),
  ErrorDetail: fieldsOf<C.ErrorDetail>()(["code", "message", "details"]),
  ErrorResponse: fieldsOf<C.ErrorResponse>()(["error"]),
} as const;

export type MirroredModel = keyof typeof CONTRACT_FIELDS;

/** Models in contracts.py the frontend never receives or sends (provider, roles, workflow internals). */
export const INTERNAL_MODELS = [
  "ChatMessage",
  "ProviderError",
  "GenerationRequest",
  "GenerationResult",
  "RefactorProposal",
  "ReferenceExpectation",
  "ReferenceTest",
  "ReferenceCase",
  "WorkflowRequest",
  "WorkflowOutcome",
] as const;

/** Nested models, for checking example JSON recursively. */
type Shape = MirroredModel | { list: MirroredModel } | { map: MirroredModel };

export const NESTED: Partial<Record<MirroredModel, Record<string, Shape>>> = {
  AnalysisReport: { findings: { list: "RoleFinding" } },
  RubricCheck: {},
  ReferenceTestsResult: { failures: { list: "ReferenceTestFailure" } },
  VerificationResult: {
    syntax: "SyntaxCheck",
    rubric: "RubricCheck",
    reference_tests: "ReferenceTestsResult",
    model_review: "ModelReviewResult",
  },
  WorkflowSettings: { generation: { map: "GenerationConfig" } },
  AttemptRecord: { verification: "VerificationResult", review: "ReviewResult", model: "ModelReference" },
  RunRecord: {
    model: "ModelReference",
    settings: "WorkflowSettings",
    stage_timings: { list: "StageTiming" },
    analysis: "AnalysisReport",
    findings: { list: "RoleFinding" },
    review: "ReviewResult",
    verification: "VerificationResult",
    attempts: { list: "AttemptRecord" },
    error: "RunError",
  },
  RunList: { runs: { list: "RunSummary" } },
  HealthResponse: { provider: "ProviderInfo", runner: "RunnerInfo", queue: "QueueInfo" },
  ErrorResponse: { error: "ErrorDetail" },
};
