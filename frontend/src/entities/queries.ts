/**
 * Server-state hooks.
 *
 * All network state lives in the TanStack Query cache: health, provider
 * availability, run records and the run history. Components never call
 * `fetch` themselves, so caching, retries, invalidation and request
 * cancellation are handled in exactly one place.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type FeedbackDecision, type RunRequest } from '@/shared/api/endpoints';
import { isTerminalStatus } from '@/shared/api/contract';
import { errorMessage } from '@/shared/api/http';
import type { RunStats } from '@/shared/api/contract';

export const queryKeys = {
  stats: ['stats'] as const,
  health: ['health'] as const,
  providers: ['providers'] as const,
  runs: ['runs'] as const,
  runList: (limit: number) => ['runs', 'list', limit] as const,
  runTotal: ['runs', 'total'] as const,
  run: (id: string) => ['runs', 'detail', id] as const,
};

/** Service health; polled gently so the status pill stays truthful. */
export function useHealth(enabled = true) {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => api.health(signal),
    enabled,
    staleTime: 5_000,
    refetchInterval: 30_000,
    retry: 0,
  });
}

/** Provider catalog with live availability (probed server-side, cached 15s). */
export function useProviders(enabled = true) {
  return useQuery({
    queryKey: queryKeys.providers,
    queryFn: ({ signal }) => api.providers(signal),
    enabled,
    staleTime: 20_000,
  });
}

/** One run record; polls while the run is still executing. */
export function useRun(id: string | null) {
  return useQuery({
    queryKey: queryKeys.run(id ?? ''),
    queryFn: ({ signal }) => api.getRun(id as string, signal),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && !isTerminalStatus(status) ? 700 : false;
    },
  });
}

/** Aggregate statistics measured over the stored runs. */
export function useStats(enabled = true) {
  return useQuery({
    queryKey: queryKeys.stats,
    queryFn: async ({ signal }) => {
      const response = await fetch('/api/v1/stats', { signal, headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error(`Stats request failed with status ${response.status}`);
      return (await response.json()) as RunStats;
    },
    enabled,
    staleTime: 10_000,
  });
}

/** Run history, newest first. */
export function useRunHistory(limit = 50) {
  return useQuery({
    queryKey: queryKeys.runList(limit),
    queryFn: ({ signal }) => api.listRuns(limit, signal),
    staleTime: 5_000,
  });
}

/** Total stored runs (from the server's `X-Total-Count`), for honest paging. */
export function useRunTotal() {
  return useQuery({
    queryKey: queryKeys.runTotal,
    queryFn: ({ signal }) => api.countRuns(signal),
    staleTime: 5_000,
  });
}

/** Start a run; the API executes it in the background. */
export function useCreateRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RunRequest) => api.createRun(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
  });
}

/** Record the user decision (accept/reject) for a run. */
export function useDecision() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      decision,
      comment,
    }: {
      id: string;
      decision: FeedbackDecision;
      comment?: string;
    }) => api.submitDecision(id, decision, comment),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.run(updated.id), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.runs });
    },
  });
}

/** Static analysis of the current buffer. */
export function useAnalyze() {
  return useMutation({
    mutationFn: (code: string) => api.analyze(code),
  });
}

export { errorMessage };
