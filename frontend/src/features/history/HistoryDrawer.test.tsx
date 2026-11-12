import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '@/test/render';
import { runFixture } from '@/test/fixtures';
import { HistoryDrawer } from './HistoryDrawer';

/**
 * The drawer must page honestly: it shows how many of the stored runs it has
 * loaded and asks the server for more only when the user does. The numbers come
 * from `X-Total-Count`, so the label never guesses that the history ended.
 */
const TOTAL = 222;

vi.mock('@/entities/queries', () => ({
  useRunHistory: (limit: number) => ({
    data: Array.from({ length: Math.min(limit, TOTAL) }, (_, index) =>
      runFixture({ id: `run-${String(index).padStart(3, '0')}` }),
    ),
  }),
  useRunTotal: () => ({ data: TOTAL }),
  useStats: () => ({ data: undefined, isLoading: false }),
}));

describe('HistoryDrawer paging', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reports the loaded window against the stored total', () => {
    renderWithProviders(<HistoryDrawer open onClose={() => {}} />);

    expect(screen.getByText('Showing 50 of 222 stored run(s)')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Load 50 more' })).toBeInTheDocument();
  });

  it('loads the next page only after the user asks for it', async () => {
    renderWithProviders(<HistoryDrawer open onClose={() => {}} />);
    const user = userEvent.setup();

    expect(screen.queryByText('run-060')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Load 50 more' }));

    expect(await screen.findByText('Showing 100 of 222 stored run(s)')).toBeInTheDocument();
    expect(screen.getByText('run-060')).toBeInTheDocument();
  });
});
