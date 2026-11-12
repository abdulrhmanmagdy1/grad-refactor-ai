import { create } from 'zustand';

export type ResultTab = 'diff' | 'verification' | 'metrics' | 'traces' | 'tests' | 'graph';

interface ResultsState {
  /** Identifier of the run currently inspected in the results panel. */
  currentRunId: string | null;
  tab: ResultTab;
  setTab: (tab: ResultTab) => void;
  openRun: (runId: string | null) => void;
}

export const useResultsStore = create<ResultsState>((set) => ({
  currentRunId: null,
  tab: 'diff',
  setTab: (tab) => set({ tab }),
  openRun: (currentRunId) => set({ currentRunId, tab: 'diff' }),
}));
