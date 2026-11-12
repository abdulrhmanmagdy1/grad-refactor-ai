import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

import type { AnalysisResult } from '@/shared/api/contract';

export type SourceFile = 'input' | 'tests';

/** Budgets enforced by the service for every run (FR08). */
export interface RunLimits {
  maxModelCalls: number;
  maxTotalTokens: number;
  maxDurationSeconds: number;
  maxRetries: number;
}

const DEFAULT_LIMITS: RunLimits = {
  maxModelCalls: 2,
  maxTotalTokens: 4096,
  maxDurationSeconds: 120,
  maxRetries: 1,
};

interface WorkspaceState {
  /** Source buffer submitted to the analyzer and the refactoring pipeline. */
  code: string;
  /** Optional trusted test file executed in the isolated sandbox. */
  testCode: string;
  activeFile: SourceFile;
  /** Selected provider id ("" = pick automatically). */
  provider: string;
  /** Budgets sent with every run (FR08). */
  limits: RunLimits;
  /** Refactoring type requested for the next run (set from the analysis). */
  refactoringType: string | null;
  /** Last analysis result for the current buffer. */
  analysis: AnalysisResult | null;
  /** The exact buffer the stored analysis was produced from. */
  analyzedCode: string | null;
  analysisError: string | null;
  setCode: (code: string) => void;
  setTestCode: (code: string) => void;
  setActiveFile: (file: SourceFile) => void;
  setProvider: (provider: string) => void;
  setLimits: (limits: Partial<RunLimits>) => void;
  setRefactoringType: (refactoringType: string | null) => void;
  resetLimits: () => void;
  setAnalysis: (analysis: AnalysisResult | null, analyzedCode?: string | null) => void;
  setAnalysisError: (message: string | null) => void;
  resetBuffers: () => void;
}

/**
 * Editor buffers and provider selection.
 *
 * The buffers are persisted so a refresh never loses the user's work; the
 * analysis result is intentionally *not* persisted because it must always
 * correspond to the code currently in the editor.
 */
export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      code: '',
      testCode: '',
      activeFile: 'input',
      provider: '',
      limits: DEFAULT_LIMITS,
      refactoringType: null,
      analysis: null,
      analyzedCode: null,
      analysisError: null,
      setCode: (code) => set({ code }),
      setTestCode: (testCode) => set({ testCode }),
      setActiveFile: (activeFile) => set({ activeFile }),
      setProvider: (provider) => set({ provider }),
      setLimits: (limits) => set((state) => ({ limits: { ...state.limits, ...limits } })),
      setRefactoringType: (refactoringType) => set({ refactoringType }),
      resetLimits: () => set({ limits: DEFAULT_LIMITS }),
      setAnalysis: (analysis, analyzedCode = null) => set({ analysis, analyzedCode, analysisError: null }),
      setAnalysisError: (analysisError) => set({ analysisError }),
      resetBuffers: () =>
        set({ code: '', testCode: '', analysis: null, analyzedCode: null, analysisError: null }),
    }),
    {
      name: 'refactor-ai-workspace',
      storage: createJSONStorage(() => window.localStorage),
      partialize: (state) => ({
        code: state.code,
        testCode: state.testCode,
        provider: state.provider,
        limits: state.limits,
      }),
    },
  ),
);
