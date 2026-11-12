/** Typed endpoints for the Refactor AI API. */
import { z } from 'zod';

import {
  analysisSchema,
  healthSchema,
  providerSchema,
  runListSchema,
  runRecordSchema,
  type AnalysisResult,
  type HealthResponse,
  type ProviderInfo,
  type RunRecord,
} from './contract';
import { requestJson, requestText } from './http';

export type FeedbackDecision = 'accepted' | 'rejected';

export interface RunRequest {
  code: string;
  test_code?: string | null;
  provider?: string | null;
  refactoring_type?: string | null;
  max_retries?: number;
  max_model_calls?: number;
  max_total_tokens?: number;
  max_duration_seconds?: number;
}

export const api = {
  health: (signal?: AbortSignal): Promise<HealthResponse> =>
    requestJson('/health', { schema: healthSchema, signal, timeoutMs: 10_000 }),

  providers: (signal?: AbortSignal): Promise<ProviderInfo[]> =>
    requestJson('/api/v1/providers', { schema: z.array(providerSchema), signal, timeoutMs: 20_000 }),

  analyze: (code: string, signal?: AbortSignal): Promise<AnalysisResult> =>
    requestJson('/api/v1/analyze', {
      method: 'POST',
      body: { code },
      schema: analysisSchema,
      signal,
      timeoutMs: 30_000,
    }),

  /** Start a run. The API runs it in the background; the client polls for status. */
  createRun: (payload: RunRequest, signal?: AbortSignal): Promise<RunRecord> =>
    requestJson('/runs', {
      method: 'POST',
      body: payload,
      schema: runRecordSchema,
      signal,
      timeoutMs: 30_000,
    }),

  getRun: (id: string, signal?: AbortSignal): Promise<RunRecord> =>
    requestJson(`/runs/${encodeURIComponent(id)}`, { schema: runRecordSchema, signal }),

  listRuns: (limit = 50, signal?: AbortSignal): Promise<RunRecord[]> =>
    requestJson(`/runs?limit=${limit}`, { schema: runListSchema, signal }),

  /** Total stored runs, read from the server's `X-Total-Count` header. */
  countRuns: async (signal?: AbortSignal): Promise<number> => {
    const response = await fetch('/runs?limit=1', {
      signal,
      headers: { Accept: 'application/json' },
    });
    if (!response.ok) {
      throw new Error(`Run count request failed with status ${response.status}`);
    }
    const raw = response.headers.get('X-Total-Count');
    const parsed = raw === null ? Number.NaN : Number.parseInt(raw, 10);
    if (Number.isFinite(parsed)) return parsed;
    const page = runListSchema.parse(await response.json());
    return page.length;
  },

  submitDecision: (
    id: string,
    decision: FeedbackDecision,
    comment?: string,
    signal?: AbortSignal,
  ): Promise<RunRecord> =>
    requestJson(`/runs/${encodeURIComponent(id)}/decision`, {
      method: 'POST',
      body: { decision, comment: comment ?? null },
      schema: runRecordSchema,
      signal,
    }),

  /** Markdown report rendered by the server from the stored run record. */
  report: (id: string, signal?: AbortSignal): Promise<string> =>
    requestText(`/runs/${encodeURIComponent(id)}/report`, { signal }),
};
