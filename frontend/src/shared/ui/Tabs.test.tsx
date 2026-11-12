import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Tabs } from './Tabs';

const TABS = [
  { id: 'diff', label: 'Diff' },
  { id: 'metrics', label: 'Metrics' },
  { id: 'traces', label: 'Traces' },
];

describe('Tabs', () => {
  it('marks the active tab and wires the panel ids', () => {
    render(<Tabs tabs={TABS} value="diff" onChange={() => {}} label="Run results" />);

    const list = screen.getByRole('tablist', { name: 'Run results' });
    expect(list).toBeInTheDocument();

    const diff = screen.getByRole('tab', { name: 'Diff' });
    expect(diff).toHaveAttribute('aria-selected', 'true');
    expect(diff).toHaveAttribute('aria-controls', 'tabpanel-diff');
    expect(screen.getByRole('tab', { name: 'Metrics' })).toHaveAttribute('aria-selected', 'false');
  });

  it('moves to the next tab with the arrow keys', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Tabs tabs={TABS} value="diff" onChange={onChange} label="Run results" />);

    await user.click(screen.getByRole('tab', { name: 'Diff' }));
    await user.keyboard('{ArrowRight}');

    expect(onChange).toHaveBeenCalledWith('metrics');
  });

  it('jumps to the last tab with End', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Tabs tabs={TABS} value="diff" onChange={onChange} label="Run results" />);

    await user.click(screen.getByRole('tab', { name: 'Diff' }));
    await user.keyboard('{End}');
    expect(onChange).toHaveBeenCalledWith('traces');
  });
});
