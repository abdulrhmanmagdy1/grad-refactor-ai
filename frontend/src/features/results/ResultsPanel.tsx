import { useEffect, useRef } from 'react';
import { Check, Copy, Download, FileText, Link2, X } from 'lucide-react';

import { useDecision, useRun } from '@/entities/queries';
import { api } from '@/shared/api/endpoints';
import { errorMessage } from '@/shared/api/http';
import { useResultsStore, type ResultTab } from '@/features/results/results.store';
import {
  DiffTab,
  GraphTab,
  MetricsTab,
  TestsTab,
  TracesTab,
  VerificationTab,
} from '@/features/results/tabs';
import { copyText, downloadText } from '@/shared/lib/download';
import { currentRunLink } from '@/features/results/useUrlSync';
import { formatAbsoluteTime, formatDuration, formatTokens, shortId } from '@/shared/lib/format';
import { Button, IconButton, Spinner } from '@/shared/ui/Button';
import { Badge, EmptyState, ErrorState, RunStatusBadge, VerdictBadge } from '@/shared/ui/Feedback';
import { Panel, PanelHeader } from '@/shared/ui/Surface';
import { TabPanel, Tabs, type TabDefinition } from '@/shared/ui/Tabs';
import { toast } from '@/shared/ui/toast.store';

const TABS: TabDefinition<ResultTab>[] = [
  { id: 'diff', label: 'Diff' },
  { id: 'verification', label: 'Verification' },
  { id: 'metrics', label: 'Metrics' },
  { id: 'traces', label: 'Traces' },
  { id: 'tests', label: 'Tests' },
  { id: 'graph', label: 'Graph' },
];

/** Inspector for the selected run: metadata, actions and the six result views. */
export function ResultsPanel({ className }: { className?: string }) {
  const currentRunId = useResultsStore((state) => state.currentRunId);
  const tab = useResultsStore((state) => state.tab);
  const setTab = useResultsStore((state) => state.setTab);
  const runQuery = useRun(currentRunId);
  const decision = useDecision();
  const lastStatus = useRef<string | null>(null);

  const run = runQuery.data;

  // Announce the verdict once, when the run reaches a terminal state.
  useEffect(() => {
    if (!run) return;
    if (run.status !== 'completed' && run.status !== 'failed') return;
    if (lastStatus.current === run.status) return;
    lastStatus.current = run.status;

    if (run.status === 'failed') {
      toast.error('Run failed.', run.errors ?? 'No diagnostic was recorded.');
      return;
    }
    const verdict = run.verification?.review_verdict ?? 'unknown';
    if (verdict === 'approved') toast.success('Run completed — verdict: approved.');
    else if (verdict === 'rejected') toast.error('Run completed — verdict: rejected.');
    else toast.info(`Run completed — verdict: ${verdict}.`);
  }, [run]);

  const onCopy = async () => {
    if (!run?.output_code) return;
    const copied = await copyText(run.output_code);
    if (copied) toast.success('Candidate code copied to the clipboard.');
    else toast.warning('The clipboard is unavailable in this browser context.');
  };

  const onDownload = () => {
    if (!run?.output_code) return;
    downloadText(`refactored_${shortId(run.id)}.py`, run.output_code, 'text/x-python');
  };

  const onExportReport = async () => {
    if (!run) return;
    try {
      const markdown = await api.report(run.id);
      downloadText(`run-${shortId(run.id)}.md`, markdown, 'text/markdown');
      toast.success('Markdown report exported from the stored run record.');
    } catch (error) {
      toast.error('The report could not be exported.', errorMessage(error));
    }
  };

  const onDecision = async (value: 'accepted' | 'rejected') => {
    if (!run) return;
    try {
      await decision.mutateAsync({ id: run.id, decision: value });
      toast.success(`Decision recorded: ${value}.`);
    } catch (error) {
      toast.error('The decision could not be recorded.', errorMessage(error));
    }
  };

  return (
    <Panel className={className}>
      <PanelHeader
        title="Results"
        meta={
          run ? (
            <span className="flex flex-wrap items-center gap-2">
              <RunStatusBadge status={run.status} />
              <span className="font-mono">{shortId(run.id)}</span>
              {run.verification ? <VerdictBadge verdict={run.verification.review_verdict} /> : null}
            </span>
          ) : (
            'no run selected'
          )
        }
        actions={
          run ? (
            <>
              <IconButton label="Copy candidate code" onClick={() => void onCopy()} disabled={!run.output_code}>
                <Copy size={14} aria-hidden="true" />
              </IconButton>
              <IconButton label="Download refactored file" onClick={onDownload} disabled={!run.output_code}>
                <Download size={14} aria-hidden="true" />
              </IconButton>
              <IconButton label="Export Markdown report" onClick={() => void onExportReport()}>
                <FileText size={14} aria-hidden="true" />
              </IconButton>
              <IconButton
                label="Copy link to this run"
                onClick={() => {
                  void copyText(currentRunLink(run.id, tab)).then((copied) => {
                    if (copied) toast.success('Link to this run copied.');
                    else toast.warning('The clipboard is unavailable in this browser context.');
                  });
                }}
              >
                <Link2 size={14} aria-hidden="true" />
              </IconButton>
              <Button
                size="sm"
                variant="success"
                icon={<Check size={13} aria-hidden="true" />}
                onClick={() => void onDecision('accepted')}
                loading={decision.isPending}
                disabled={run.user_feedback === 'accepted'}
              >
                Accept
              </Button>
              <Button
                size="sm"
                variant="danger"
                icon={<X size={13} aria-hidden="true" />}
                onClick={() => void onDecision('rejected')}
                loading={decision.isPending}
                disabled={run.user_feedback === 'rejected'}
              >
                Reject
              </Button>
            </>
          ) : null
        }
      />

      {run ? (
        <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-edge px-3 py-1.5 text-[11px] text-fg-subtle">
          <span>
            provider <code className="font-mono">{String(run.metrics.provider ?? '—')}</code>
          </span>
          <span>
            model <code className="font-mono">{String(run.metrics.model ?? '—')}</code>
          </span>
          <span>duration {formatDuration(Number(run.metrics.total_duration_ms ?? 0))}</span>
          <span>tokens {formatTokens(Number(run.metrics.total_tokens ?? 0))}</span>
          <span>retries {String(run.metrics.retries_used ?? 0)}</span>
          {run.metrics.limits && typeof run.metrics.limits === 'object' ? (
            <span title="Budgets enforced by the service for this run (FR08)">
              budget{' '}
              <code className="font-mono">
                {String(
                  (run.metrics.limits as Record<string, unknown>).max_model_calls ?? '—',
                )}
                {' calls / '}
                {String(
                  (run.metrics.limits as Record<string, unknown>).max_total_tokens ?? '—',
                )}
                {' tok / '}
                {String(
                  (run.metrics.limits as Record<string, unknown>).max_duration_seconds ?? '—',
                )}
                s
              </code>
            </span>
          ) : null}
          <span title={formatAbsoluteTime(run.created_at)}>created {formatAbsoluteTime(run.created_at)}</span>
          {run.refactoring_type ? <Badge tone="accent">{run.refactoring_type}</Badge> : null}
        </div>
      ) : null}

      {run ? (
        <>
          <div className="shrink-0 border-b border-edge px-2 py-1.5">
            <Tabs tabs={TABS} value={tab} onChange={setTab} label="Run results" />
          </div>
          <TabPanel id="diff" active={tab === 'diff'}>
            <DiffTab run={run} />
          </TabPanel>
          <TabPanel id="verification" active={tab === 'verification'}>
            <VerificationTab run={run} />
          </TabPanel>
          <TabPanel id="metrics" active={tab === 'metrics'}>
            <MetricsTab run={run} />
          </TabPanel>
          <TabPanel id="traces" active={tab === 'traces'}>
            <TracesTab run={run} />
          </TabPanel>
          <TabPanel id="tests" active={tab === 'tests'}>
            <TestsTab run={run} />
          </TabPanel>
          <TabPanel id="graph" active={tab === 'graph'}>
            <GraphTab run={run} />
          </TabPanel>
        </>
      ) : runQuery.isError ? (
        <div className="p-3">
          <ErrorState
            title="The run could not be loaded"
            message={errorMessage(runQuery.error)}
            onRetry={() => void runQuery.refetch()}
          />
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center gap-2">
          {runQuery.isFetching ? <Spinner size={16} /> : null}
          <EmptyState
            title="No run selected"
            description="Run the pipeline from the source panel, or open a previous run from the history drawer."
          />
        </div>
      )}
    </Panel>
  );
}
