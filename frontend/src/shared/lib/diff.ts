/** Unified-diff statistics computed from the diff text stored with a run. */

export interface DiffStats {
  added: number;
  removed: number;
  hunks: number;
}

/**
 * Count added/removed lines and hunks in a unified diff.
 *
 * The API stores the diff as text only, so the numbers are derived here and
 * are always consistent with the diff the user actually sees.
 */
export function parseDiffStats(diff: string | null | undefined): DiffStats {
  const stats: DiffStats = { added: 0, removed: 0, hunks: 0 };
  if (!diff) return stats;

  for (const line of diff.split('\n')) {
    if (line.startsWith('+++') || line.startsWith('---')) continue;
    if (line.startsWith('@@')) {
      stats.hunks += 1;
      continue;
    }
    if (line.startsWith('+')) stats.added += 1;
    else if (line.startsWith('-')) stats.removed += 1;
  }
  return stats;
}

/** Split a unified diff into per-hunk blocks for a compact renderer. */
export interface DiffHunk {
  header: string;
  lines: string[];
}

export function splitDiffHunks(diff: string | null | undefined): DiffHunk[] {
  if (!diff) return [];
  const hunks: DiffHunk[] = [];
  let current: DiffHunk | null = null;

  for (const line of diff.split('\n')) {
    if (line.startsWith('@@')) {
      current = { header: line, lines: [] };
      hunks.push(current);
      continue;
    }
    if (current) current.lines.push(line);
  }
  return hunks;
}
