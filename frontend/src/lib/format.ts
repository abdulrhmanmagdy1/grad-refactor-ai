/** Formatting helpers. Output is English with fixed locales so it does not follow the OS language. */

const DATE_TIME = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const TIME = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const NUMBER = new Intl.NumberFormat("en-US");

/**
 * Parses an ISO 8601 timestamp from the service. Fractional seconds are reduced to
 * milliseconds and a timestamp without a zone designator is read as UTC.
 */
export function parseServerTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const trimmed = value.trim();
  const millis = trimmed.replace(/\.(\d+)/, (_match, digits: string) => `.${`${digits}000`.slice(0, 3)}`);
  const hasZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(millis);
  const parsed = Date.parse(hasZone ? millis : `${millis}Z`);
  return Number.isNaN(parsed) ? null : parsed;
}

export function formatDateTime(value: string | null | undefined): string {
  const parsed = parseServerTime(value);
  return parsed === null ? "Not recorded" : DATE_TIME.format(parsed);
}

export function formatTime(value: string | null | undefined): string {
  const parsed = parseServerTime(value);
  return parsed === null ? "Not recorded" : TIME.format(parsed);
}

export function formatCount(value: number): string {
  return NUMBER.format(value);
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${formatCount(count)} ${count === 1 ? singular : pluralForm}`;
}

const pad2 = (value: number) => String(value).padStart(2, "0");

/** A measured duration in seconds, for example "420 ms", "4.2 s" or "2 min 05 s". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "Not recorded";
  if (seconds < 0.001) return "< 1 ms";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 10) return `${seconds.toFixed(1)} s`;
  const total = Math.round(seconds);
  if (total < 60) return `${total} s`;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (hours > 0) return `${hours} h ${pad2(minutes)} min`;
  return `${minutes} min ${pad2(total % 60)} s`;
}

/** A ticking elapsed time in whole seconds, for example "7 s" or "1 min 05 s". */
export function formatElapsed(milliseconds: number): string {
  const total = Math.max(0, Math.floor(milliseconds / 1000));
  if (total < 60) return `${total} s`;
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) return `${hours} h ${pad2(minutes)} min ${pad2(seconds)} s`;
  return `${minutes} min ${pad2(seconds)} s`;
}

/** Seconds between two server timestamps, or null when either is missing. */
export function secondsBetween(start: string | null | undefined, end: string | null | undefined): number | null {
  const from = parseServerTime(start);
  const to = parseServerTime(end);
  if (from === null || to === null || to < from) return null;
  return (to - from) / 1000;
}

export function shortId(id: string, length = 8): string {
  return id.length > length ? id.slice(0, length) : id;
}

export function shortHash(hash: string, length = 12): string {
  return hash.length > length ? `${hash.slice(0, length)}…` : hash;
}
