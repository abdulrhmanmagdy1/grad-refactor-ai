import { useMemo, useRef, useState } from 'react';
import { FileCode2, FlaskConical, Play, ScanSearch, Sparkles } from 'lucide-react';
import type { editor as MonacoEditorType } from 'monaco-editor';

import { useAnalyze, useProviders } from '@/entities/queries';
import { useRunPipeline } from '@/features/workspace/useRunPipeline';
import { useWorkspaceStore, type SourceFile } from '@/features/workspace/workspace.store';
import { PRESETS } from '@/features/workspace/presets';
import { CodeEditor } from '@/features/workspace/CodeEditor';
import { errorMessage } from '@/shared/api/http';
import { cn } from '@/shared/lib/cn';
import { Button, Spinner } from '@/shared/ui/Button';
import { Badge, EmptyState, ErrorState } from '@/shared/ui/Feedback';
import { NumberField, Select } from '@/shared/ui/Inputs';
import { Panel, PanelHeader } from '@/shared/ui/Surface';
import { toast } from '@/shared/ui/toast.store';

/**
 * Source workspace: buffers, static analysis and the run controls.
 *
 * The editor is the single source of truth for the submitted code: the
 * analyzer, the pipeline and the report all read the very same buffer.
 */
export function WorkspacePanel({ className }: { className?: string }) {
  const code = useWorkspaceStore((state) => state.code);
  const testCode = useWorkspaceStore((state) => state.testCode);
  const activeFile = useWorkspaceStore((state) => state.activeFile);
  const setActiveFile = useWorkspaceStore((state) => state.setActiveFile);
  const setCode = useWorkspaceStore((state) => state.setCode);
  const setTestCode = useWorkspaceStore((state) => state.setTestCode);
  const analysis = useWorkspaceStore((state) => state.analysis);
  const analyzedCode = useWorkspaceStore((state) => state.analyzedCode);
  const analysisError = useWorkspaceStore((state) => state.analysisError);
  const setAnalysis = useWorkspaceStore((state) => state.setAnalysis);
  const setAnalysisError = useWorkspaceStore((state) => state.setAnalysisError);
  const limits = useWorkspaceStore((state) => state.limits);
  const setLimits = useWorkspaceStore((state) => state.setLimits);
  const refactoringType = useWorkspaceStore((state) => state.refactoringType);
  const setRefactoringType = useWorkspaceStore((state) => state.setRefactoringType);
  const providerId = useWorkspaceStore((state) => state.provider);
  const providers = useProviders();

  const analyze = useAnalyze();
  const { runPipeline, isRunning } = useRunPipeline();
  const editorRef = useRef<MonacoEditorType.IStandaloneCodeEditor | null>(null);
  const [presetId, setPresetId] = useState('');

  const value = activeFile === 'input' ? code : testCode;

  const selectedProvider =
    providers.data?.find((entry) => entry.id === providerId) ?? providers.data?.[0] ?? null;

  // The dominant rule is the most frequent finding of the current analysis.
  const dominantRule = useMemo(() => {
    const findings = analysis?.findings ?? [];
    if (findings.length === 0) return null;
    const counts = new Map<string, number>();
    for (const finding of findings) {
      counts.set(finding.rule, (counts.get(finding.rule) ?? 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] ?? null;
  }, [analysis]);

  const onAnalyze = async () => {
    if (!code.trim()) {
      toast.error('The input buffer is empty — add some Python first.');
      return;
    }
    setAnalysisError(null);
    try {
      const result = await analyze.mutateAsync(code);
      setAnalysis(result, code);
      if (result.syntax_valid) {
        toast.success(`Analysis complete — ${result.findings.length} finding(s) detected.`);
      } else {
        toast.error(`Syntax error: ${result.error ?? 'invalid Python source'}`);
      }
    } catch (error) {
      const message = errorMessage(error);
      setAnalysisError(message);
      toast.error('The analysis request failed.', message);
    }
  };

  const onLoadPreset = (id: string) => {
    setPresetId(id);
    const preset = PRESETS.find((entry) => entry.id === id);
    if (!preset) return;
    setCode(preset.code);
    setTestCode(preset.testCode);
    setActiveFile('input');
    setAnalysis(null);
    toast.info(`Loaded example: ${preset.title}`);
  };

  const revealFinding = (line: number) => {
    const editor = editorRef.current;
    if (!editor) return;
    editor.revealLineInCenter(line);
    editor.setPosition({ lineNumber: line, column: 1 });
    editor.focus();
  };

  return (
    <Panel className={cn('min-h-0', className)}>
      <PanelHeader
        title="Source"
        meta={activeFile === 'input' ? 'input.py' : 'test_input.py'}
        actions={
          <>
            <Select
              label="Example"
              className="w-40"
              value={presetId}
              onChange={onLoadPreset}
              options={[
                { value: '', label: 'Load example…' },
                ...PRESETS.map((preset) => ({ value: preset.id, label: preset.title })),
              ]}
            />
            <Button
              size="sm"
              icon={<ScanSearch size={13} aria-hidden="true" />}
              onClick={() => void onAnalyze()}
              loading={analyze.isPending}
              disabled={isRunning}
            >
              Analyze
            </Button>
            <Button
              size="sm"
              variant="primary"
              icon={<Play size={13} aria-hidden="true" />}
              onClick={() => void runPipeline()}
              loading={isRunning}
              title="Run the multi-agent pipeline (Ctrl+Enter)"
            >
              Run
            </Button>
          </>
        }
      />

      <div className="flex shrink-0 items-center gap-1 border-b border-edge px-2 py-1">
        {(['input', 'tests'] as SourceFile[]).map((file) => (
          <button
            key={file}
            type="button"
            aria-pressed={activeFile === file}
            onClick={() => setActiveFile(file)}
            className={cn(
              'inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors',
              activeFile === file ? 'bg-surface-2 text-fg' : 'text-fg-muted hover:text-fg',
            )}
          >
            {file === 'input' ? (
              <FileCode2 size={13} aria-hidden="true" />
            ) : (
              <FlaskConical size={13} aria-hidden="true" />
            )}
            {file === 'input' ? 'input.py' : 'test_input.py'}
          </button>
        ))}
        {activeFile === 'tests' ? (
          <span className="ml-2 text-[11px] text-fg-subtle">
            Executed in the isolated sandbox — never in the API process.
          </span>
        ) : null}
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-edge px-3 py-1.5 text-[11px] text-fg-subtle">
        {selectedProvider ? (
          <span className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className={cn('size-1.5 rounded-full', selectedProvider.available ? 'bg-success' : 'bg-danger')}
            />
            <span className="text-fg-muted">{selectedProvider.label}</span>
            <span className="font-mono">{selectedProvider.engine}</span>
            {!selectedProvider.available ? (
              <span className="text-warning">{selectedProvider.detail}</span>
            ) : null}
          </span>
        ) : null}

        {dominantRule ? (
          <span className="flex items-center gap-1.5">
            <span className="text-fg-muted">Detected</span>
            <Badge tone="accent">{dominantRule}</Badge>
            <button
              type="button"
              onClick={() => setRefactoringType(dominantRule)}
              className={cn(
                'rounded border px-1.5 py-0.5 text-[10px] transition-colors',
                refactoringType === dominantRule
                  ? 'border-accent bg-accent-soft text-accent'
                  : 'border-edge hover:border-accent hover:text-accent',
              )}
            >
              {refactoringType === dominantRule ? 'requested' : 'request this type'}
            </button>
          </span>
        ) : null}

        {refactoringType ? (
          <span className="flex items-center gap-1.5">
            <span className="text-fg-muted">requested type</span>
            <Badge tone="info">{refactoringType}</Badge>
            <button
              type="button"
              onClick={() => setRefactoringType(null)}
              className="text-[10px] text-fg-subtle underline hover:text-fg"
            >
              clear
            </button>
          </span>
        ) : null}
      </div>

      <details className="group shrink-0 border-b border-edge px-3 py-1.5">
        <summary className="cursor-pointer text-[11px] font-medium text-fg-muted select-none">
          Run budgets (FR08) — max calls {limits.maxModelCalls} · max tokens {limits.maxTotalTokens} · max{' '}
          {limits.maxDurationSeconds}s · retries {limits.maxRetries}
        </summary>
        <div className="mt-2 grid gap-2 sm:grid-cols-4">
          <NumberField
            label="Max model calls"
            value={limits.maxModelCalls}
            min={1}
            max={4}
            onChange={(value) => setLimits({ maxModelCalls: value })}
          />
          <NumberField
            label="Max total tokens"
            value={limits.maxTotalTokens}
            min={1}
            max={100000}
            step={256}
            onChange={(value) => setLimits({ maxTotalTokens: value })}
          />
          <NumberField
            label="Max duration"
            value={limits.maxDurationSeconds}
            min={1}
            max={600}
            suffix="seconds"
            onChange={(value) => setLimits({ maxDurationSeconds: value })}
          />
          <NumberField
            label="Max retries"
            value={limits.maxRetries}
            min={0}
            max={1}
            onChange={(value) => setLimits({ maxRetries: value })}
          />
        </div>
      </details>

      <div className="min-h-[240px] flex-1 overflow-hidden">
        <CodeEditor
          value={value}
          onChange={(next) => (activeFile === 'input' ? setCode(next) : setTestCode(next))}
          onMount={(editor) => {
            editorRef.current = editor;
          }}
          ariaLabel={activeFile === 'input' ? 'Source code editor' : 'Test code editor'}
          className="h-full"
        />
      </div>

      <div className="max-h-[38%] shrink-0 overflow-y-auto scroll-thin border-t border-edge">
        {analyze.isPending ? (
          <div className="flex items-center gap-2 px-3 py-3 text-xs text-fg-subtle">
            <Spinner size={13} />
            Analyzing…
          </div>
        ) : null}

        {analysisError ? (
          <div className="p-3">
            <ErrorState title="Analysis failed" message={analysisError} onRetry={() => void onAnalyze()} />
          </div>
        ) : null}

        {analysis && analyzedCode !== null && analyzedCode !== code ? (
          <div className="flex items-center justify-between gap-2 border-b border-warning/40 bg-warning-soft px-3 py-1.5 text-[11px] text-warning">
            <span>The buffer changed since the last analysis — the findings below are stale.</span>
            <button
              type="button"
              onClick={() => void onAnalyze()}
              className="shrink-0 rounded border border-warning/50 px-1.5 py-0.5 hover:bg-warning hover:text-on-accent"
            >
              Re-analyze
            </button>
          </div>
        ) : null}

        {analysis && !analysisError ? (
          analysis.findings.length === 0 ? (
            <EmptyState
              icon={<Sparkles size={18} aria-hidden="true" />}
              title="No findings"
              description={
                analysis.syntax_valid
                  ? 'The analyzer found no smell in the current buffer.'
                  : 'The submitted code does not parse — fix the syntax error first.'
              }
            />
          ) : (
            <ul className="divide-y divide-edge">
              {analysis.findings.map((finding, index) => (
                <li key={`${finding.rule}-${finding.line}-${index}`}>
                  <button
                    type="button"
                    onClick={() => revealFinding(finding.line)}
                    className="flex w-full items-start gap-2 px-3 py-2 text-left transition-colors hover:bg-surface-2"
                  >
                    <Badge tone="accent" className="mt-0.5 shrink-0">
                      {finding.rule}
                    </Badge>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-xs">{finding.message}</span>
                      <span className="block truncate text-[11px] text-fg-subtle">
                        line {finding.line}
                        {finding.end_line ? `–${finding.end_line}` : ''} · {finding.node_type} ·{' '}
                        {finding.rationale}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )
        ) : null}

        {!analysis && !analysisError && !analyze.isPending ? (
          <EmptyState
            icon={<ScanSearch size={18} aria-hidden="true" />}
            title="No analysis yet"
            description="Run the analyzer to see the detected smells in the current buffer."
          />
        ) : null}
      </div>
    </Panel>
  );
}
