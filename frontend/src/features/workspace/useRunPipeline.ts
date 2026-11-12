import { useCallback } from 'react';

import { useAnalyze, useCreateRun } from '@/entities/queries';
import { useResultsStore } from '@/features/results/results.store';
import { useWorkspaceStore } from '@/features/workspace/workspace.store';
import { errorMessage } from '@/shared/api/http';
import { toast } from '@/shared/ui/toast.store';

/**
 * Starts a multi-agent run.
 *
 * The API executes the run in the background; the client then polls the run
 * record so the phase (analyzing → generating → verifying) stays visible.
 */
export function useRunPipeline() {
  const createRun = useCreateRun();
  const analyze = useAnalyze();
  const openRun = useResultsStore((state) => state.openRun);
  const code = useWorkspaceStore((state) => state.code);
  const testCode = useWorkspaceStore((state) => state.testCode);
  const provider = useWorkspaceStore((state) => state.provider);
  const limits = useWorkspaceStore((state) => state.limits);
  const refactoringType = useWorkspaceStore((state) => state.refactoringType);
  const analyzedCode = useWorkspaceStore((state) => state.analyzedCode);
  const setAnalysis = useWorkspaceStore((state) => state.setAnalysis);

  const runPipeline = useCallback(async () => {
    if (!code.trim()) {
      toast.error('The input buffer is empty — add some Python first.');
      return;
    }
    try {
      // Pre-flight: refresh the static analysis when the buffer changed since
      // the last one, so the findings on screen always describe the code that
      // is about to be submitted.
      if (analyzedCode !== code) {
        const analysis = await analyze.mutateAsync(code);
        setAnalysis(analysis, code);
        if (!analysis.syntax_valid) {
          toast.error(
            'The submitted code does not parse — fix the syntax error before running.',
          );
          return;
        }
      }

      const record = await createRun.mutateAsync({
        code,
        test_code: testCode.trim() ? testCode : null,
        provider: provider || null,
        refactoring_type: refactoringType || null,
        max_retries: limits.maxRetries,
        max_model_calls: limits.maxModelCalls,
        max_total_tokens: limits.maxTotalTokens,
        max_duration_seconds: limits.maxDurationSeconds,
      });
      openRun(record.id);
      toast.info('Run started — the multi-agent pipeline is executing.');
    } catch (error) {
      toast.error('The run could not be started.', errorMessage(error));
    }
  }, [
    code,
    testCode,
    provider,
    refactoringType,
    limits,
    analyzedCode,
    analyze,
    setAnalysis,
    createRun,
    openRun,
  ]);

  return { runPipeline, isRunning: createRun.isPending };
}
