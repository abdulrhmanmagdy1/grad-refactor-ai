import type { RunRecord } from '@/shared/api/contract';

/**
 * Export helpers for the run history.
 *
 * The exports contain only values the API already returned — the JSON export
 * is the raw records, the CSV export flattens the measured columns. Nothing is
 * derived, so an exported file can be quoted as evidence (NFR06).
 */

export const HISTORY_CSV_COLUMNS = [
  'id',
  'created_at',
  'status',
  'refactoring_type',
  'review_verdict',
  'tests_passed',
  'duration_ms',
  'total_tokens',
  'provider',
  'model',
  'user_feedback',
] as const;

function cell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

/** Flatten run records into a CSV table of the measured columns. */
export function historyToCsv(runs: RunRecord[]): string {
  const lines = [HISTORY_CSV_COLUMNS.join(',')];
  for (const run of runs) {
    const metrics = run.metrics as Record<string, unknown>;
    lines.push(
      [
        run.id,
        run.created_at,
        run.status,
        run.refactoring_type ?? '',
        run.verification?.review_verdict ?? '',
        run.verification?.tests_passed ?? '',
        metrics.total_duration_ms ?? '',
        metrics.total_tokens ?? '',
        metrics.provider ?? '',
        metrics.model ?? '',
        run.user_feedback ?? '',
      ]
        .map(cell)
        .join(','),
    );
  }
  return lines.join('\n') + '\n';
}

/** Pretty-printed JSON export of the run records. */
export function historyToJson(runs: RunRecord[]): string {
  return JSON.stringify(runs, null, 2) + '\n';
}
