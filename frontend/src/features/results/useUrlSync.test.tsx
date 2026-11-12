import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { act, render } from '@testing-library/react';

import { useUrlSync, currentRunLink } from './useUrlSync';
import { useResultsStore } from './results.store';

function Harness() {
  useUrlSync();
  return null;
}

describe('useUrlSync', () => {
  beforeEach(() => {
    useResultsStore.setState({ currentRunId: null, tab: 'diff' });
    window.history.replaceState(null, '', '/');
  });

  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  it('restores the run and the tab encoded in the URL', () => {
    window.history.replaceState(null, '', '/?run=run-42&tab=metrics');
    render(<Harness />);

    expect(useResultsStore.getState().currentRunId).toBe('run-42');
    expect(useResultsStore.getState().tab).toBe('metrics');
  });

  it('ignores an unknown tab value', () => {
    window.history.replaceState(null, '', '/?run=run-7&tab=not-a-tab');
    render(<Harness />);

    expect(useResultsStore.getState().currentRunId).toBe('run-7');
    expect(useResultsStore.getState().tab).toBe('diff');
  });

  it('writes the current state back into the URL', () => {
    render(<Harness />);
    act(() => {
      useResultsStore.setState({ currentRunId: 'run-9', tab: 'traces' });
    });

    expect(window.location.search).toContain('run=run-9');
    expect(window.location.search).toContain('tab=traces');
  });

  it('builds an absolute link to a run', () => {
    const link = currentRunLink('run-3', 'diff');
    expect(link).toContain('run=run-3');
    expect(link).toContain('tab=diff');
    expect(link.startsWith(window.location.origin)).toBe(true);
  });
});
