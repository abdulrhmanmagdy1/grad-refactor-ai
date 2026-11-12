import { describe, expect, it } from 'vitest';

import { isTerminalStatus, runRecordSchema } from './contract';

const RUN = {
  id: 'run-1',
  created_at: '2026-10-21T10:00:00+00:00',
  status: 'completed',
  input_code: 'def f():\n    return 1\n',
  refactoring_type: 'extract-function',
  output_code: 'def f():\n    return 1\n',
  diff: '@@ -1 +1 @@\n-a\n+b',
  explanation: 'Extracted a helper.',
  metrics: { provider: 'mock', model: 'mock-refactor-v2', total_duration_ms: 12.5 },
  metrics_before: { lines_of_code: 2 },
  metrics_after: { lines_of_code: 2 },
  metrics_delta: { lines_of_code: 0 },
  agent_traces: [
    {
      agent: 'analysis',
      phase: 'analyze',
      summary: 'Found a long function.',
      details: { findings: 1 },
      duration_ms: 1.25,
    },
  ],
  auto_generated_tests: 'def test_f():\n    assert True\n',
  ast_graph_before: { nodes: [], edges: [] },
  ast_graph_after: null,
  errors: null,
  user_feedback: null,
  feedback_comment: null,
  verification: {
    syntax_valid: true,
    tests_available: false,
    tests_passed: false,
    review_verdict: 'approved',
    review_notes: 'Behaviour preserved.',
    preserved_symbols: true,
    critique_feedback: null,
    auto_generated_tests: true,
    metrics_before: {},
    metrics_after: {},
    metrics_delta: {},
    details: {},
  },
  findings: [
    {
      rule: 'long-function',
      line: 1,
      end_line: 40,
      node_type: 'FunctionDef',
      message: 'Function is too long.',
      rationale: 'Hard to test.',
    },
  ],
};

describe('runRecordSchema', () => {
  it('accepts a complete run record', () => {
    const parsed = runRecordSchema.safeParse(RUN);
    expect(parsed.success).toBe(true);
  });

  it('rejects an unknown status so contract drift is visible', () => {
    const parsed = runRecordSchema.safeParse({ ...RUN, status: 'halting' });
    expect(parsed.success).toBe(false);
  });

  it('rejects a record missing the audit fields', () => {
    const { created_at: _createdAt, ...withoutCreatedAt } = RUN;
    expect(runRecordSchema.safeParse(withoutCreatedAt).success).toBe(false);
  });
});

describe('isTerminalStatus', () => {
  it('marks only completed and failed as terminal', () => {
    expect(isTerminalStatus('completed')).toBe(true);
    expect(isTerminalStatus('failed')).toBe(true);
    expect(isTerminalStatus('analyzing')).toBe(false);
    expect(isTerminalStatus('queued')).toBe(false);
  });
});
