import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ResultsPanel } from './ResultsPanel';
import { useResultsStore } from './results.store';
import { runFixture } from '@/test/fixtures';
import { renderWithProviders } from '@/test/render';

const RUN = runFixture();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'req-1' },
  });
}

describe('ResultsPanel', () => {
  beforeEach(() => {
    useResultsStore.setState({ currentRunId: RUN.id, tab: 'diff' });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the verdict, the meta strip and the six result tabs', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(RUN));
    vi.stubGlobal('fetch', fetchMock);

    renderWithProviders(<ResultsPanel />);

    expect(await screen.findByText('approved')).toBeInTheDocument();
    expect(screen.getByText('mock-refactor-v2')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Diff' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Verification' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Metrics' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Traces' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Tests' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Graph' })).toBeInTheDocument();
  });

  it('shows the measured metrics with their deltas', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(RUN)));

    renderWithProviders(<ResultsPanel />);
    await screen.findByText('approved');

    useResultsStore.setState({ tab: 'metrics' });
    const user = userEvent.setup();
    await user.click(screen.getByRole('tab', { name: 'Metrics' }));

    expect(await screen.findByText('Maintainability index')).toBeInTheDocument();
    expect(screen.getByText('+12.70')).toBeInTheDocument();
  });

  it('records the user decision against the API', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (String(url).includes('/decision')) {
        return jsonResponse({ ...RUN, user_feedback: 'accepted' });
      }
      return jsonResponse(RUN);
    });
    vi.stubGlobal('fetch', fetchMock);

    renderWithProviders(<ResultsPanel />);
    await screen.findByText('approved');

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Accept/ }));

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url]) => String(url).includes('/decision'));
      expect(call).toBeTruthy();
    });
  });

  it('surfaces a failing run with its recorded diagnostic', async () => {
    const failed = runFixture({ status: 'failed', errors: 'Generated-token limit of 1 exceeded.' });
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(failed)));
    useResultsStore.setState({ tab: 'verification' });

    renderWithProviders(<ResultsPanel />);

    expect(await screen.findByText('Generated-token limit of 1 exceeded.')).toBeInTheDocument();
  });
});
