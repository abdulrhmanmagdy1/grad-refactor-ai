import { useEffect } from 'react';

import { useResultsStore, type ResultTab } from '@/features/results/results.store';

const TABS: ResultTab[] = ['diff', 'verification', 'metrics', 'traces', 'tests', 'graph'];

/**
 * Keeps the run and the active tab in the URL.
 *
 * A link such as `/?run=<id>&tab=diff` opens exactly the same view, so a run
 * can be bookmarked or pasted into the academic report and reproduce what the
 * author saw. The URL is the only state shared with the outside world; no run
 * data is stored in it.
 */
export function useUrlSync(): void {
  const currentRunId = useResultsStore((state) => state.currentRunId);
  const tab = useResultsStore((state) => state.tab);
  const openRun = useResultsStore((state) => state.openRun);
  const setTab = useResultsStore((state) => state.setTab);

  // Restore the state encoded in the URL on first load.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const run = params.get('run');
    const requestedTab = params.get('tab');

    if (run) openRun(run);
    if (requestedTab && TABS.includes(requestedTab as ResultTab)) {
      setTab(requestedTab as ResultTab);
    }
    // Restoration happens once, on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Write the current state back into the URL.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (currentRunId) params.set('run', currentRunId);
    else params.delete('run');
    if (tab) params.set('tab', tab);
    const query = params.toString();
    const next = `${window.location.pathname}${query ? `?${query}` : ''}`;
    window.history.replaceState(null, '', next);
  }, [currentRunId, tab]);
}

/** Absolute link to the currently inspected run. */
export function currentRunLink(runId: string | null, tab: string): string {
  const params = new URLSearchParams();
  if (runId) params.set('run', runId);
  if (tab) params.set('tab', tab);
  return `${window.location.origin}${window.location.pathname}?${params.toString()}`;
}
