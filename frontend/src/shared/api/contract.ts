/**
 * Runtime contracts for the HTTP API.
 *
 * The shapes mirror `src/core/schemas.py` in the FastAPI service. Parsing every
 * response with Zod turns a silent contract drift (a renamed field, a changed
 * type) into an explicit, visible error instead of `undefined` leaking into the
 * UI — the client and the server can never silently disagree.
 */
import { z } from 'zod';

export const astFindingSchema = z.object({
  rule: z.string(),
  line: z.number(),
  end_line: z.number().nullable(),
  node_type: z.string(),
  message: z.string(),
  rationale: z.string(),
});
export type AstFinding = z.infer<typeof astFindingSchema>;

export const astGraphNodeSchema = z.object({
  id: z.string(),
  label: z.string(),
  type: z.string(),
  line: z.number(),
  complexity: z.number(),
  has_smell: z.boolean(),
  smell_type: z.string().nullable(),
});
export type AstGraphNode = z.infer<typeof astGraphNodeSchema>;

export const astGraphEdgeSchema = z.object({
  source: z.string(),
  target: z.string(),
});
export type AstGraphEdge = z.infer<typeof astGraphEdgeSchema>;

export const astGraphSchema = z.object({
  nodes: z.array(astGraphNodeSchema),
  edges: z.array(astGraphEdgeSchema),
});
export type AstGraph = z.infer<typeof astGraphSchema>;

export const analysisSchema = z.object({
  syntax_valid: z.boolean(),
  findings: z.array(astFindingSchema),
  error: z.string().nullable(),
  engine: z.string(),
  metrics: z.record(z.string(), z.unknown()),
  ast_graph: astGraphSchema.nullable(),
});
export type AnalysisResult = z.infer<typeof analysisSchema>;

export const agentTraceSchema = z.object({
  agent: z.string(),
  phase: z.string(),
  summary: z.string(),
  details: z.record(z.string(), z.unknown()),
  duration_ms: z.number().nullable(),
});
export type AgentTrace = z.infer<typeof agentTraceSchema>;

export const verificationSchema = z.object({
  syntax_valid: z.boolean(),
  tests_available: z.boolean(),
  tests_passed: z.boolean(),
  review_verdict: z.string(),
  review_notes: z.string(),
  preserved_symbols: z.boolean(),
  critique_feedback: z.string().nullable(),
  auto_generated_tests: z.boolean(),
  metrics_before: z.record(z.string(), z.unknown()),
  metrics_after: z.record(z.string(), z.unknown()),
  metrics_delta: z.record(z.string(), z.unknown()),
  details: z.record(z.string(), z.unknown()),
});
export type VerificationResult = z.infer<typeof verificationSchema>;

export const runStatusSchema = z.enum([
  'queued',
  'analyzing',
  'generating',
  'verifying',
  'completed',
  'failed',
]);
export type RunStatus = z.infer<typeof runStatusSchema>;

export const runRecordSchema = z.object({
  id: z.string(),
  created_at: z.string(),
  status: runStatusSchema,
  input_code: z.string(),
  refactoring_type: z.string().nullable(),
  output_code: z.string().nullable(),
  diff: z.string().nullable(),
  explanation: z.string().nullable(),
  metrics: z.record(z.string(), z.unknown()),
  metrics_before: z.record(z.string(), z.unknown()),
  metrics_after: z.record(z.string(), z.unknown()),
  metrics_delta: z.record(z.string(), z.unknown()),
  agent_traces: z.array(agentTraceSchema),
  auto_generated_tests: z.string().nullable(),
  ast_graph_before: astGraphSchema.nullable(),
  ast_graph_after: astGraphSchema.nullable(),
  errors: z.string().nullable(),
  user_feedback: z.string().nullable(),
  feedback_comment: z.string().nullable(),
  verification: verificationSchema.nullable(),
  findings: z.array(astFindingSchema),
});
export type RunRecord = z.infer<typeof runRecordSchema>;

export const providerSchema = z.object({
  id: z.string(),
  label: z.string(),
  available: z.boolean(),
  engine: z.string(),
  detail: z.string(),
});
export type ProviderInfo = z.infer<typeof providerSchema>;

export const healthSchema = z.object({
  status: z.string(),
  version: z.string(),
  mode: z.string(),
});
export type HealthResponse = z.infer<typeof healthSchema>;

export const runListSchema = z.array(runRecordSchema);

/** Aggregate statistics measured over the stored runs. */
export const runStatsSchema = z.object({
  total_runs: z.number(),
  sampled_runs: z.number(),
  truncated: z.boolean(),
  by_status: z.record(z.string(), z.number()),
  by_verdict: z.record(z.string(), z.number()),
  mean_duration_ms: z.number().nullable(),
  median_duration_ms: z.number().nullable(),
  mean_total_tokens: z.number().nullable(),
  acceptance_rate: z.number().nullable(),
  runs_with_verdict: z.number(),
  runs_in_flight: z.number(),
  max_concurrent_runs: z.number(),
});
export type RunStats = z.infer<typeof runStatsSchema>;

/** Statuses that mean "the run will not change any more". */
export const TERMINAL_STATUSES: readonly RunStatus[] = ['completed', 'failed'];

export function isTerminalStatus(status: RunStatus): boolean {
  return TERMINAL_STATUSES.includes(status);
}
