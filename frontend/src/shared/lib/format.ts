/** Formatting helpers shared by every panel. All of them are total functions. */

const EM_DASH = '—';

/** Human readable duration for millisecond values. */
export function formatDuration(ms: number | null | undefined): string {
  if (typeof ms !== 'number' || !Number.isFinite(ms)) return EM_DASH;
  if (ms < 1) return '<1 ms';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

/** Compact token counts (1234 -> "1.2k"). */
export function formatTokens(tokens: number | null | undefined): string {
  if (typeof tokens !== 'number' || !Number.isFinite(tokens)) return EM_DASH;
  if (tokens < 1000) return String(Math.round(tokens));
  if (tokens < 1_000_000) return `${(tokens / 1000).toFixed(1)}k`;
  return `${(tokens / 1_000_000).toFixed(1)}M`;
}

/** Fixed-precision number with a locale-independent decimal separator. */
export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return EM_DASH;
  return value.toFixed(digits);
}

/** Signed delta, e.g. "+12.5" / "-3.0" / "0.0". */
export function formatDelta(value: number | null | undefined, digits = 2): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return EM_DASH;
  const fixed = value.toFixed(digits);
  return value > 0 ? `+${fixed}` : fixed;
}

/** Percentage with one decimal. */
export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (typeof value !== 'number' || !Number.isFinite(value)) return EM_DASH;
  return `${value.toFixed(digits)}%`;
}

/** ISO timestamp -> "just now" / "4 min ago" / "2 days ago". */
export function formatRelativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return EM_DASH;
  const timestamp = Date.parse(iso);
  if (Number.isNaN(timestamp)) return EM_DASH;
  const diffSeconds = Math.round((now - timestamp) / 1000);
  if (diffSeconds < 45) return 'just now';
  if (diffSeconds < 3600) return `${Math.round(diffSeconds / 60)} min ago`;
  if (diffSeconds < 86_400) return `${Math.round(diffSeconds / 3600)} h ago`;
  const days = Math.round(diffSeconds / 86_400);
  return days === 1 ? 'yesterday' : `${days} days ago`;
}

/** Absolute local timestamp (used in tooltips). */
export function formatAbsoluteTime(iso: string | null | undefined): string {
  if (!iso) return EM_DASH;
  const timestamp = Date.parse(iso);
  if (Number.isNaN(timestamp)) return EM_DASH;
  return new Date(timestamp).toLocaleString();
}

/** First 8 characters of an identifier — enough to recognise a run. */
export function shortId(id: string | null | undefined): string {
  if (!id) return EM_DASH;
  return id.slice(0, 8);
}

/** Byte size for download hints. */
export function formatBytes(bytes: number | null | undefined): string {
  if (typeof bytes !== 'number' || !Number.isFinite(bytes)) return EM_DASH;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Metric key -> human label (used by the metrics tables). */
export function humanizeMetric(key: string): string {
  const overrides: Record<string, string> = {
    maintainability_index: 'Maintainability index',
    total_cyclomatic_complexity: 'Cyclomatic complexity',
    max_cognitive_complexity: 'Cognitive complexity',
    max_nesting_depth: 'Max nesting depth',
    lines_of_code: 'Lines of code',
    functions_count: 'Functions',
    classes_count: 'Classes',
    maintainability_index_delta: 'Maintainability delta',
  };
  if (overrides[key]) return overrides[key];
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (character) => character.toUpperCase())
    .replace(/^Mi\b/, 'MI');
}
