import { describe, expect, it } from 'vitest';

import { historyToCsv, historyToJson, HISTORY_CSV_COLUMNS } from './historyExport';
import { runFixture } from '@/test/fixtures';

describe('history export', () => {
  it('writes a header and one row per run', () => {
    const runs = [runFixture(), runFixture({ id: 'second', status: 'failed' })];
    const csv = historyToCsv(runs);
    const lines = csv.trim().split('\n');

    expect(lines[0]).toBe(HISTORY_CSV_COLUMNS.join(','));
    expect(lines).toHaveLength(3);
    expect(lines[1]).toContain('approved');
    expect(lines[2]).toContain('failed');
  });

  it('escapes values that contain a comma', () => {
    const runs = [runFixture({ refactoring_type: 'extract,function' })];
    const csv = historyToCsv(runs);
    expect(csv).toContain('"extract,function"');
  });

  it('exports the raw records as JSON', () => {
    const runs = [runFixture()];
    const parsed = JSON.parse(historyToJson(runs)) as { id: string; status: string }[];
    expect(parsed).toHaveLength(1);
    expect(parsed[0].id).toBe(runs[0].id);
    expect(parsed[0].status).toBe('completed');
  });

  it('renders an empty history without breaking the format', () => {
    expect(historyToCsv([]).trim()).toBe(HISTORY_CSV_COLUMNS.join(','));
    expect(JSON.parse(historyToJson([]))).toEqual([]);
  });
});
