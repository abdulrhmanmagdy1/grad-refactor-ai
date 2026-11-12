import { describe, expect, it } from 'vitest';

import { formatDelta, formatDuration, formatRelativeTime, formatTokens, humanizeMetric } from './format';
import { parseDiffStats, splitDiffHunks } from './diff';

describe('formatDuration', () => {
  it('scales the unit with the magnitude', () => {
    expect(formatDuration(0.4)).toBe('<1 ms');
    expect(formatDuration(845)).toBe('845 ms');
    expect(formatDuration(1500)).toBe('1.50 s');
    expect(formatDuration(90_000)).toBe('1m 30s');
  });

  it('renders missing values as an em dash', () => {
    expect(formatDuration(null)).toBe('—');
    expect(formatDuration(undefined)).toBe('—');
    expect(formatDuration(Number.NaN)).toBe('—');
  });
});

describe('formatTokens', () => {
  it('abbreviates thousands and millions', () => {
    expect(formatTokens(0)).toBe('0');
    expect(formatTokens(999)).toBe('999');
    expect(formatTokens(1234)).toBe('1.2k');
    expect(formatTokens(2_500_000)).toBe('2.5M');
  });
});

describe('formatDelta', () => {
  it('signs positive values only', () => {
    expect(formatDelta(2)).toBe('+2.00');
    expect(formatDelta(-2)).toBe('-2.00');
    expect(formatDelta(0)).toBe('0.00');
  });
});

describe('formatRelativeTime', () => {
  it('describes recent timestamps relatively', () => {
    const now = Date.parse('2026-10-21T12:00:00Z');
    expect(formatRelativeTime('2026-10-21T11:59:40Z', now)).toBe('just now');
    expect(formatRelativeTime('2026-10-21T11:55:00Z', now)).toBe('5 min ago');
    expect(formatRelativeTime('2026-10-21T09:00:00Z', now)).toBe('3 h ago');
    expect(formatRelativeTime('not-a-date', now)).toBe('—');
  });
});

describe('humanizeMetric', () => {
  it('uses readable names for the known metrics', () => {
    expect(humanizeMetric('maintainability_index')).toBe('Maintainability index');
    expect(humanizeMetric('total_cyclomatic_complexity')).toBe('Cyclomatic complexity');
    expect(humanizeMetric('custom_metric')).toBe('Custom Metric');
  });
});

describe('parseDiffStats', () => {
  it('counts added, removed and hunk markers', () => {
    const diff = ['--- a/x.py', '+++ b/x.py', '@@ -1,2 +1,3 @@', '+added', '-removed', ' kept'].join(
      '\n',
    );
    expect(parseDiffStats(diff)).toEqual({ added: 1, removed: 1, hunks: 1 });
  });

  it('returns zeroes for a missing diff', () => {
    expect(parseDiffStats(null)).toEqual({ added: 0, removed: 0, hunks: 0 });
  });
});

describe('splitDiffHunks', () => {
  it('groups the lines under their hunk header', () => {
    const diff = ['@@ -1 +1 @@', '+one', '@@ -5 +5 @@', '+two'].join('\n');
    const hunks = splitDiffHunks(diff);
    expect(hunks).toHaveLength(2);
    expect(hunks[0].lines).toEqual(['+one']);
    expect(hunks[1].header).toContain('@@ -5');
  });
});
