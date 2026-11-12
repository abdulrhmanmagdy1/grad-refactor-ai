import { useMemo, useState } from 'react';

import { useRunHistory, useRunTotal } from '@/entities/queries';
import { useResultsStore } from '@/features/results/results.store';
import { downloadText } from '@/shared/lib/download';
import { formatRelativeTime, shortId } from '@/shared/lib/format';
import { historyToCsv, historyToJson } from '@/features/history/historyExport';
import { Button } from '@/shared/ui/Button';
import { Badge, EmptyState, RunStatusBadge } from '@/shared/ui/Feedback';
import { SearchInput } from '@/shared/ui/Inputs';
import { Drawer } from '@/shared/ui/Overlays';
import { toast } from '@/shared/ui/toast.store';
import { InsightsPanel } from '@/features/insights/InsightsPanel';

type StatusFilter = 'all' | 'completed' | 'failed' | 'running';

/** Run history with filtering; selecting a run loads it into the results panel. */
export function HistoryDrawer({
  open,
  onClose,
  onCompare,
}: {
  open: boolean;
  onClose: () => void;
  onCompare?: (runId: string) => void;
}) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<StatusFilter>('all');
  const [visible, setVisible] = useState(50);
  const history = useRunHistory(visible);
  const total = useRunTotal().data ?? history.data?.length ?? 0;
  const loaded = history.data?.length ?? 0;
  const openRun = useResultsStore((state) => state.openRun);
  const currentRunId = useResultsStore((state) => state.currentRunId);

  const runs = useMemo(() => {
    const list = history.data ?? [];
    return list.filter((run) => {
      if (filter === 'running') {
        return !['completed', 'failed'].includes(run.status);
      }
      if (filter !== 'all' && run.status !== filter) return false;
      if (!query.trim()) return true;
      const needle = query.trim().toLowerCase();
      return (
        run.id.toLowerCase().includes(needle) ||
        (run.refactoring_type ?? '').toLowerCase().includes(needle) ||
        (run.verification?.review_verdict ?? '').toLowerCase().includes(needle)
      );
    });
  }, [history.data, query, filter]);

  const filters: { id: StatusFilter; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'completed', label: 'Completed' },
    { id: 'failed', label: 'Failed' },
    { id: 'running', label: 'In flight' },
  ];

  return (
    <Drawer open={open} onClose={onClose} title="Run history">
      <InsightsPanel />
      <div className="flex flex-col gap-2 border-b border-edge p-3">
        <SearchInput value={query} onChange={setQuery} label="Search runs" placeholder="Search id, type, verdict…" />
        <div className="flex flex-wrap items-center gap-1">
          {filters.map((entry) => (
            <button
              key={entry.id}
              type="button"
              aria-pressed={filter === entry.id}
              onClick={() => setFilter(entry.id)}
              className={`rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
                filter === entry.id
                  ? 'border-accent bg-accent-soft text-accent'
                  : 'border-edge text-fg-muted hover:text-fg'
              }`}
            >
              {entry.label}
            </button>
          ))}
          <span className="ml-auto flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                downloadText('run-history.csv', historyToCsv(runs), 'text/csv');
                toast.success(`Exported ${runs.length} run(s) as CSV.`);
              }}
              disabled={runs.length === 0}
            >
              CSV
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                downloadText('run-history.json', historyToJson(runs), 'application/json');
                toast.success(`Exported ${runs.length} run(s) as JSON.`);
              }}
              disabled={runs.length === 0}
            >
              JSON
            </Button>
          </span>
        </div>
      </div>

      {runs.length === 0 ? (
        <EmptyState title="No runs match" description="Adjust the filter or run the pipeline first." />
      ) : (
        <ul className="divide-y divide-edge">
          {runs.map((run) => (
            <li key={run.id}>
              <button
                type="button"
                onClick={() => {
                  openRun(run.id);
                  onClose();
                }}
                className={`flex w-full flex-col gap-1 px-3 py-2.5 text-left transition-colors hover:bg-surface-2 ${
                  currentRunId === run.id ? 'bg-accent-soft' : ''
                }`}
              >
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs">{shortId(run.id)}</span>
                  <RunStatusBadge status={run.status} />
                  {run.refactoring_type ? <Badge tone="neutral">{run.refactoring_type}</Badge> : null}
                  {run.user_feedback ? (
                    <Badge tone={run.user_feedback === 'accepted' ? 'success' : 'danger'}>
                      {run.user_feedback}
                    </Badge>
                  ) : null}
                </span>
                <span className="flex items-center justify-between gap-2">
                  <span className="text-[11px] text-fg-subtle">
                    {formatRelativeTime(run.created_at)} ·{' '}
                    {run.verification?.review_verdict ?? 'no verdict'}
                  </span>
                  {onCompare ? (
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        onCompare(run.id);
                      }}
                      className="rounded border border-edge px-1.5 py-0.5 text-[10px] text-fg-muted transition-colors hover:border-accent hover:text-accent"
                    >
                      Compare
                    </button>
                  ) : null}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-edge px-3 py-2 text-[11px] text-fg-subtle">
        <span>
          Showing {loaded} of {total} stored run(s)
        </span>
        {loaded < total ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setVisible((count) => Math.min(500, count + 50))}
            disabled={visible >= 500}
          >
            {visible >= 500 ? 'Page limit reached' : 'Load 50 more'}
          </Button>
        ) : null}
      </div>
    </Drawer>
  );
}
