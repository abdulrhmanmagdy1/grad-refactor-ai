/**
 * Typed builders for contract values, modelled on docs/architecture/examples/. Every
 * builder returns a complete object so tests fail to compile if the contract changes.
 */

import type {
  HealthResponse,
  ModelReference,
  ReferenceCaseSummary,
  RunAccepted,
  RunRecord,
  RunSummary,
  VerificationResult,
  WorkflowMode,
  WorkflowSettings,
} from "../api/contracts";

export const RUN_ID = "2a6d8f0b1c3e4a5b9d7f6e5d4c3b2a10";

export const ORIGINAL_CODE = [
  "def shipping_cost(weight, express):",
  '    """Return the shipping cost."""',
  "    if weight > 0:",
  "        if express:",
  "            return weight * 3",
  "        else:",
  "            return weight * 2",
  "    else:",
  '        raise ValueError("weight must be positive")',
  "",
].join("\n");

export const PROPOSED_CODE = [
  "def shipping_cost(weight, express):",
  '    """Return the shipping cost."""',
  "    if weight <= 0:",
  "        raise ValueError('weight must be positive')",
  "    if express:",
  "        return weight * 3",
  "    return weight * 2",
  "",
].join("\n");

export const DIFF_TEXT = [
  "--- original.py",
  "+++ proposed.py",
  "@@ -1,9 +1,7 @@",
  " def shipping_cost(weight, express):",
  '     """Return the shipping cost."""',
  "-    if weight > 0:",
  "-        if express:",
  "-            return weight * 3",
  "-        else:",
  "-            return weight * 2",
  "-    else:",
  '-        raise ValueError("weight must be positive")',
  "+    if weight <= 0:",
  "+        raise ValueError('weight must be positive')",
  "+    if express:",
  "+        return weight * 3",
  "+    return weight * 2",
  "",
].join("\n");

export const LOCAL_MODEL: ModelReference = {
  model_id: "example-org/example-code-model",
  model_revision: "0123456789abcdef0123456789abcdef01234567",
  adapter_id: "guard-clauses-lora",
  adapter_sha256: "f".repeat(64),
  use_adapter: true,
};

export const FAKE_MODEL: ModelReference = {
  model_id: "fake-provider",
  model_revision: "fake-v1",
  adapter_id: null,
  adapter_sha256: null,
  use_adapter: false,
};

export function settings(mode: WorkflowMode = "multi_role"): WorkflowSettings {
  // The per-role defaults of WorkflowSettings in contracts.py.
  const base = { temperature: 0, top_p: 1, seed: 42 };
  return {
    mode,
    refactor_use_adapter: false,
    max_calls: 5,
    max_corrections: 1,
    run_timeout_s: 600,
    generation: {
      analysis: { ...base, max_new_tokens: 384, max_input_tokens: 2048, timeout_s: 60 },
      refactor: { ...base, max_new_tokens: 1024, max_input_tokens: 2048, timeout_s: 120 },
      review: { ...base, max_new_tokens: 768, max_input_tokens: 4096, timeout_s: 90 },
    },
  };
}

export function verification(overrides: Partial<VerificationResult> = {}): VerificationResult {
  return {
    syntax: { status: "pass", error: null },
    rubric: {
      status: "pass",
      checks: {
        parses_as_single_function: true,
        same_name: true,
        same_signature: true,
        same_docstring: true,
        within_task_constraints: true,
        nesting_reduced: true,
        has_guard_clause: true,
        no_new_calls: true,
      },
      reasons: [],
    },
    reference_tests: {
      status: "pass",
      case_id: "shipping_cost",
      total: 4,
      passed: 4,
      failed: 0,
      errored: 0,
      reason: null,
      duration_s: 0.42,
      failures: [],
    },
    model_review: { status: "accept", reasons: ["The guard keeps zero invalid."], error: null },
    disposition: "proposal_ready",
    disposition_reasons: [],
    ...overrides,
  };
}

/** A completed multi-role run with a ready proposal from the local model. */
export function runRecord(overrides: Partial<RunRecord> = {}): RunRecord {
  return {
    schema_version: 1,
    run_id: RUN_ID,
    created_at: "2026-10-20T09:02:00Z",
    started_at: "2026-10-20T09:02:00.400000Z",
    finished_at: "2026-10-20T09:02:01Z",
    status: "completed",
    task_type: "guard_clauses",
    workflow_mode: "multi_role",
    reference_case_id: "shipping_cost",
    original_code: ORIGINAL_CODE,
    proposed_code: PROPOSED_CODE,
    provider_mode: "local_model",
    model: LOCAL_MODEL,
    settings: settings(overrides.workflow_mode ?? "multi_role"),
    attempt_count: 1,
    call_count: 3,
    stage_timings: [
      { stage: "validation", attempt: 0, started_at: "2026-10-20T09:02:00.400000Z", elapsed_s: 0.002, calls: 0 },
      { stage: "analysis", attempt: 0, started_at: "2026-10-20T09:02:00.410000Z", elapsed_s: 0.01, calls: 1 },
      { stage: "generation", attempt: 0, started_at: "2026-10-20T09:02:00.420000Z", elapsed_s: 0.01, calls: 1 },
      { stage: "verification", attempt: 0, started_at: "2026-10-20T09:02:00.430000Z", elapsed_s: 0.45, calls: 0 },
      { stage: "review", attempt: 0, started_at: "2026-10-20T09:02:00.880000Z", elapsed_s: 0.01, calls: 1 },
    ],
    analysis: {
      schema_version: 1,
      supported_task: true,
      findings: [
        {
          type: "nested_conditional",
          start_line: 3,
          end_line: 9,
          reason: "The else branch always raises, so it can become a guard clause.",
        },
      ],
      unsupported_reason: null,
      source: "model",
    },
    findings: [
      {
        type: "nested_conditional",
        start_line: 3,
        end_line: 9,
        reason: "The else branch always raises, so it can become a guard clause.",
      },
    ],
    explanation: "Inverted the weight check into a guard clause and removed the else branches.",
    diff: DIFF_TEXT,
    changed_lines: [3, 4, 5, 6, 7],
    review: {
      schema_version: 1,
      verdict: "accept",
      reasons: ["The guard keeps zero invalid."],
      suggested_correction: null,
    },
    verification: verification(),
    attempts: [
      {
        attempt: 0,
        raw_output: "Explanation: Inverted the weight check.\n```python\n" + PROPOSED_CODE + "```",
        parse_error: null,
        parse_repaired: false,
        proposed_code: PROPOSED_CODE,
        explanation: "Inverted the weight check into a guard clause and removed the else branches.",
        verification: verification(),
        review: null,
        model: LOCAL_MODEL,
        prompt_tokens: 120,
        completion_tokens: 40,
        elapsed_s: 0.01,
      },
    ],
    stop_reason: "no_correction_needed",
    error: null,
    warnings: [],
    human_decision: null,
    ...overrides,
  };
}

/** A run that has not finished: no results yet. */
export function pendingRecord(status: RunRecord["status"], overrides: Partial<RunRecord> = {}): RunRecord {
  return runRecord({
    status,
    started_at: status === "queued" ? null : "2026-10-20T09:02:00.400000Z",
    finished_at: null,
    proposed_code: null,
    model: null,
    attempt_count: 0,
    call_count: 0,
    stage_timings: [],
    analysis: null,
    findings: [],
    explanation: null,
    diff: null,
    changed_lines: [],
    review: null,
    verification: null,
    attempts: [],
    stop_reason: null,
    ...overrides,
  });
}

export function failedRecord(overrides: Partial<RunRecord> = {}): RunRecord {
  return pendingRecord("failed", {
    finished_at: "2026-10-20T09:15:00Z",
    error: {
      code: "interrupted",
      message: "The service stopped before this run finished. It was not rerun; submit the code again to retry.",
      stage: "generating",
    },
    ...overrides,
  });
}

export function accepted(overrides: Partial<RunAccepted> = {}): RunAccepted {
  const runId = overrides.run_id ?? RUN_ID;
  return { run_id: runId, status: "queued", poll_url: `/api/v1/runs/${runId}`, ...overrides };
}

export function health(mode: "fake" | "local_model" = "local_model", overrides: Partial<HealthResponse> = {}): HealthResponse {
  const fake = mode === "fake";
  return {
    status: "ok",
    version: "0.1.0",
    mode,
    provider: {
      provider_mode: mode,
      model_id: fake ? "fake-provider" : LOCAL_MODEL.model_id,
      model_revision: fake ? "fake-v1" : LOCAL_MODEL.model_revision,
      adapter_id: fake ? null : LOCAL_MODEL.adapter_id,
      adapter_sha256: fake ? null : LOCAL_MODEL.adapter_sha256,
      device: fake ? "none" : "cuda:0",
      ready: true,
      detail: fake ? "Deterministic test provider. Outputs are not language-model inference." : null,
    },
    runner: fake
      ? {
          enabled: false,
          reason: "Reference test execution is disabled by configuration (REFACTOR_AI_RUNNER=disabled).",
          isolation: {},
        }
      : { enabled: true, reason: null, isolation: { separate_process: true, no_network: true } },
    queue: { max_pending: 4, pending: 0 },
    refactor_use_adapter: !fake,
    ...overrides,
  };
}

export const SHIPPING_CASE: ReferenceCaseSummary = {
  case_id: "shipping_cost",
  title: "Shipping cost with nested validation",
  function_name: "shipping_cost",
  code: ORIGINAL_CODE,
  test_count: 4,
};

export const DISCOUNT_CASE: ReferenceCaseSummary = {
  case_id: "member_discount",
  title: "Member discount with a missing price",
  function_name: "discount",
  code: [
    "def discount(price, member):",
    "    if price is not None:",
    "        if member:",
    "            return price * 0.9",
    "        else:",
    "            return price",
    "    else:",
    "        return 0",
    "",
  ].join("\n"),
  test_count: 3,
};

export function runSummary(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: RUN_ID,
    created_at: "2026-10-20T09:02:00Z",
    finished_at: "2026-10-20T09:02:01Z",
    status: "completed",
    disposition: "proposal_ready",
    task_type: "guard_clauses",
    workflow_mode: "multi_role",
    provider_mode: "local_model",
    reference_case_id: "shipping_cost",
    human_decision: null,
    ...overrides,
  };
}
