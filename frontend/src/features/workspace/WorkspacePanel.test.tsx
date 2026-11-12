import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { WorkspacePanel } from './WorkspacePanel';
import { useWorkspaceStore } from './workspace.store';
import { renderWithProviders } from '@/test/render';

// Monaco cannot run inside jsdom: the editor is replaced by a plain textarea
// that keeps the same accessible name and change contract.
vi.mock('@/features/workspace/CodeEditor', () => ({
  CodeEditor: ({
    value,
    onChange,
    ariaLabel,
  }: {
    value: string;
    onChange?: (value: string) => void;
    ariaLabel: string;
  }) => (
    <textarea
      aria-label={ariaLabel}
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
    />
  ),
}));

const ANALYSIS = {
  syntax_valid: true,
  findings: [
    {
      rule: 'long-function',
      line: 3,
      end_line: 40,
      node_type: 'FunctionDef',
      message: 'Function spans 40 lines (limit 30).',
      rationale: 'Long functions are hard to test.',
    },
  ],
  error: null,
  engine: 'static-heuristics-v2',
  metrics: {},
  ast_graph: null,
};

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('WorkspacePanel', () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      code: 'def f():\n    return 1\n',
      testCode: '',
      analysis: null,
      analysisError: null,
      provider: 'mock',
      refactoringType: null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('exposes both buffers with accessible names', async () => {
    renderWithProviders(<WorkspacePanel />);

    expect(screen.getByRole('textbox', { name: 'Source code editor' })).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /test_input\.py/ }));
    expect(screen.getByRole('textbox', { name: 'Test code editor' })).toBeInTheDocument();
  });

  it('runs the analyzer and lists the findings', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) => jsonResponse(ANALYSIS));
    vi.stubGlobal('fetch', fetchMock);

    renderWithProviders(<WorkspacePanel />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Analyze' }));

    expect(await screen.findByText('Function spans 40 lines (limit 30).')).toBeInTheDocument();
    const requested = fetchMock.mock.calls.map((call) => String(call[0] ?? ''));
    expect(requested.some((url) => url.includes('/api/v1/analyze'))).toBe(true);
  });

  it('offers the detected rule as the requested refactoring type', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(ANALYSIS)));

    renderWithProviders(<WorkspacePanel />);
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: 'Analyze' }));
    await screen.findByText('Function spans 40 lines (limit 30).');

    await user.click(screen.getByRole('button', { name: 'request this type' }));
    await waitFor(() => expect(useWorkspaceStore.getState().refactoringType).toBe('long-function'));
    expect(await screen.findByText('requested type')).toBeInTheDocument();
  });

  it('exposes the FR08 budgets as editable fields', async () => {
    renderWithProviders(<WorkspacePanel />);
    const user = userEvent.setup();

    await user.click(screen.getByText(/Run budgets \(FR08\)/));

    const calls = screen.getByLabelText('Max model calls');
    await user.clear(calls);
    await user.type(calls, '4');

    await waitFor(() => expect(useWorkspaceStore.getState().limits.maxModelCalls).toBe(4));
  });
});
