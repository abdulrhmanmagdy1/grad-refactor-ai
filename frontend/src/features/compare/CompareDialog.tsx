import { useMemo, useState } from 'react';

import { useRunHistory } from '@/entities/queries';
import type { RunRecord } from '@/shared/api/contract';
import { formatDuration, formatTokens, shortId } from '@/shared/lib/format';
import { Badge, DeltaValue, EmptyState, MetricValue, RunStatusBadge, VerdictBadge } from '@/shared/ui/Feedback';
import { Dialog } from '@/shared/ui/Overlays';
import { Select } from '@/shared/ui/Inputs';

interface ComparisonRow {
  label: string;
  render: (run: RunRecord) => React.ReactNode;
}

const ROWS: ComparisonRow[] = [
  { label: 'Status', render: (run) => <RunStatusBadge status={run.status} /> },
  { label: 'Verdict', render: (run) => <VerdictBadge verdict={run.verification?.review_verdict ?? '—'} /> },
  { label: 'Refactoring type', render: (run) => run.refactoring_type ?? '—' },
  {
    label: 'Provider / model',
    render: (run) => (
      <span className="font-mono text-xs">
        {String(run.metrics.provider ?? '—')} / {String(run.metrics.model ?? '—')}
      </span>
    ),
  },
  { label: 'Duration', render: (run) => formatDuration(Number(run.metrics.total_duration_ms ?? 0)) },
  { label: 'Tokens', render: (run) => formatTokens(Number(run.metrics.total_tokens ?? 0)) },
  { label: 'Retries', render: (run) => String(run.metrics.retries_used ?? 0) },
  {
    label: 'Maintainability index',
    render: (run) => <MetricValue value={run.metrics_before?.maintainability_index as number} />,
  },
  {
    label: 'Lines of code (after)',
    render: (run) => <MetricValue value={run.metrics_after?.lines_of_code as number} />,
  },
  {
    label: 'Complexity (after)',
    render: (run) => <MetricValue value={run.metrics_after?.total_cyclomatic_complexity as number} />,
  },
  {
    label: 'MI delta',
    render: (run) => <DeltaValue value={run.metrics_delta?.maintainability_index as number} />,
  },
  {
    label: 'User decision',
    render: (run) => (run.user_feedback ? <Badge tone="neutral">{run.user_feedback}</Badge> : '—'),
  },
];

/**
 * Side-by-side comparison of two stored runs.
 *
 * The comparison is built from the records the API already returned — no new
 * endpoint and no derived claims: every cell is a measured value of that run.
 */
export function CompareDialog({
  open,
  onClose,
  initialRunId,
}: {
  open: boolean;
  onClose: () => void;
  initialRunId?: string | null;
}) {
  const history = useRunHistory(50);
  const runs = useMemo(() => history.data ?? [], [history.data]);
  const [leftId, setLeftId] = useState<string>(initialRunId ?? '');
  const [rightId, setRightId] = useState<string>('');

  const left = useMemo(() => runs.find((run) => run.id === leftId) ?? null, [runs, leftId]);
  const right = useMemo(() => runs.find((run) => run.id === rightId) ?? null, [runs, rightId]);

  const options = runs.map((run) => ({
    value: run.id,
    label: `${shortId(run.id)} · ${run.status} · ${run.verification?.review_verdict ?? 'no verdict'}`,
  }));

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Compare two runs"
      description="Both columns are read straight from the stored run records."
      size="lg"
    >
      {runs.length === 0 ? (
        <EmptyState title="No runs yet" description="Run the pipeline first, then compare two runs." />
      ) : (
        <div className="flex flex-col gap-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <Select
              label="Run A"
              value={leftId || (options[0]?.value ?? '')}
              onChange={setLeftId}
              options={options}
            />
            <Select
              label="Run B"
              value={rightId}
              onChange={setRightId}
              options={[{ value: '', label: 'Pick a run…' }, ...options]}
            />
          </div>

          {left && right ? (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="text-left text-[11px] tracking-wider text-fg-subtle uppercase">
                    <th scope="col" className="py-1.5 pr-3 font-semibold">
                      Measure
                    </th>
                    <th scope="col" className="py-1.5 pr-3 font-semibold">
                      {shortId(left.id)}
                    </th>
                    <th scope="col" className="py-1.5 font-semibold">
                      {shortId(right.id)}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-edge">
                  {ROWS.map((row) => (
                    <tr key={row.label}>
                      <th scope="row" className="py-1.5 pr-3 text-left font-normal text-fg-muted">
                        {row.label}
                      </th>
                      <td className="py-1.5 pr-3">{row.render(left)}</td>
                      <td className="py-1.5">{row.render(right)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="Pick two runs"
              description="Choose a run in column A and a different run in column B to compare their measured values."
            />
          )}
        </div>
      )}
    </Dialog>
  );
}
