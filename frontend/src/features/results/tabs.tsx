import { useMemo, useState } from 'react';

import type { AstGraph, RunRecord } from '@/shared/api/contract';
import { DiffViewer, type DiffLayout } from '@/features/results/DiffViewer';
import { parseDiffStats } from '@/shared/lib/diff';
import { formatDuration, humanizeMetric } from '@/shared/lib/format';
import { Badge, DeltaValue, EmptyState, MetricValue, VerdictBadge } from '@/shared/ui/Feedback';
import { CodeBlock, DiffBlock } from '@/shared/ui/CodeBlock';

/** Diff of the submitted code against the proposed candidate. */
export function DiffTab({ run }: { run: RunRecord }) {
  const [layout, setLayout] = useState<DiffLayout>('split');
  const stats = useMemo(() => parseDiffStats(run.diff), [run.diff]);

  if (!run.diff || !run.output_code) {
    return (
      <EmptyState
        title="No candidate diff"
        description="This run did not produce a refactored candidate, so there is nothing to compare."
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-edge px-3 py-1.5 text-[11px] text-fg-muted">
        <Badge tone="success">+{stats.added} added</Badge>
        <Badge tone="danger">-{stats.removed} removed</Badge>
        <Badge tone="neutral">{stats.hunks} hunk(s)</Badge>
        {run.refactoring_type ? <Badge tone="accent">{run.refactoring_type}</Badge> : null}
      </div>
      <div className="min-h-0 flex-1">
        <DiffViewer
          original={run.input_code}
          modified={run.output_code}
          layout={layout}
          onLayoutChange={setLayout}
        />
      </div>
      {run.explanation ? (
        <p className="shrink-0 border-t border-edge px-3 py-2 text-xs text-fg-muted">
          {run.explanation}
        </p>
      ) : null}
    </div>
  );
}

/** Deterministic verification checks and the review agent's verdict. */
export function VerificationTab({ run }: { run: RunRecord }) {
  const verification = run.verification;

  if (!verification) {
    return (
      <EmptyState
        title="No verification record"
        description={
          run.errors
            ? 'The run failed before verification could complete.'
            : 'The pipeline did not reach the verification stage.'
        }
      />
    );
  }

  const checks: { label: string; passed: boolean; hint?: string }[] = [
    {
      label: 'Syntax valid',
      passed: verification.syntax_valid,
      hint: 'The candidate parses as Python.',
    },
    {
      label: 'Symbols preserved',
      passed: verification.preserved_symbols,
      hint: 'Public functions and classes are still present.',
    },
    {
      label: 'Tests available',
      passed: verification.tests_available,
      hint: 'A test file was supplied for the sandbox.',
    },
    {
      label: 'Tests passed',
      passed: verification.tests_passed,
      hint: 'The isolated sandbox executed the tests successfully.',
    },
    {
      label: 'Auto-generated tests',
      passed: verification.auto_generated_tests,
      hint: 'Behavioural equivalence tests were synthesised.',
    },
  ];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto scroll-thin p-3">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <VerdictBadge verdict={verification.review_verdict} />
        {run.user_feedback ? <Badge tone="neutral">user: {run.user_feedback}</Badge> : null}
      </div>

      <ul className="grid gap-2 sm:grid-cols-2">
        {checks.map((check) => (
          <li
            key={check.label}
            className="flex items-start gap-2 rounded-md border border-edge bg-surface-2 px-2.5 py-2"
          >
            <span
              aria-hidden="true"
              className={`mt-0.5 size-2 shrink-0 rounded-full ${
                check.passed ? 'bg-success' : 'bg-fg-subtle'
              }`}
            />
            <span className="min-w-0">
              <span className="block text-xs font-medium">{check.label}</span>
              <span className="block text-[11px] text-fg-subtle">{check.hint}</span>
            </span>
            <span className="sr-only">{check.passed ? 'passed' : 'not satisfied'}</span>
          </li>
        ))}
      </ul>

      <div className="mt-3">
        <h3 className="mb-1 text-[11px] font-semibold tracking-wider text-fg-subtle uppercase">
          Review notes
        </h3>
        <p className="text-xs leading-relaxed text-fg-muted">{verification.review_notes}</p>
      </div>

      {verification.critique_feedback ? (
        <div className="mt-3 rounded-md border border-warning/40 bg-warning-soft p-2.5">
          <h3 className="mb-1 text-[11px] font-semibold tracking-wider text-warning uppercase">
            Critique fed back on retry
          </h3>
          <p className="text-xs leading-relaxed text-fg-muted">{verification.critique_feedback}</p>
        </div>
      ) : null}

      {run.errors ? (
        <div className="mt-3 rounded-md border border-danger/40 bg-danger-soft p-2.5">
          <h3 className="mb-1 text-[11px] font-semibold tracking-wider text-danger uppercase">
            Errors
          </h3>
          <pre className="scroll-thin overflow-auto font-mono text-[11px] whitespace-pre-wrap text-fg-muted">
            {run.errors}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

/** Software metrics before, after and the measured delta. */
export function MetricsTab({ run }: { run: RunRecord }) {
  const before = run.metrics_before;
  const after = run.metrics_after;
  const delta = run.metrics_delta;
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after), ...Object.keys(delta)]));

  if (keys.length === 0) {
    return (
      <EmptyState
        title="No metrics snapshot"
        description="The run did not capture software metrics for this code."
      />
    );
  }

  const lowerIsBetter = new Set([
    'total_cyclomatic_complexity',
    'max_cognitive_complexity',
    'max_nesting_depth',
    'lines_of_code',
  ]);

  return (
    <div className="h-full overflow-y-auto scroll-thin p-3">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="text-left text-[11px] tracking-wider text-fg-subtle uppercase">
            <th scope="col" className="py-1.5 pr-2 font-semibold">
              Metric
            </th>
            <th scope="col" className="py-1.5 pr-2 text-right font-semibold">
              Before
            </th>
            <th scope="col" className="py-1.5 pr-2 text-right font-semibold">
              After
            </th>
            <th scope="col" className="py-1.5 text-right font-semibold">
              Δ
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-edge">
          {keys.map((key) => {
            const beforeValue = before[key];
            const afterValue = after[key];
            const deltaValue = delta[key];
            const numeric =
              typeof beforeValue === 'number' || typeof afterValue === 'number';
            return (
              <tr key={key}>
                <th scope="row" className="py-1.5 pr-2 text-left font-normal text-fg-muted">
                  {humanizeMetric(key)}
                </th>
                <td className="py-1.5 pr-2 text-right">
                  {numeric ? <MetricValue value={beforeValue as number} /> : String(beforeValue ?? '—')}
                </td>
                <td className="py-1.5 pr-2 text-right">
                  {numeric ? <MetricValue value={afterValue as number} /> : String(afterValue ?? '—')}
                </td>
                <td className="py-1.5 text-right">
                  {numeric ? (
                    <DeltaValue value={deltaValue as number} invert={lowerIsBetter.has(key)} />
                  ) : (
                    String(deltaValue ?? '—')
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** The reasoning trace exchanged between the agents. */
export function TracesTab({ run }: { run: RunRecord }) {
  if (run.agent_traces.length === 0) {
    return (
      <EmptyState
        title="No agent trace"
        description="This run did not record any reasoning steps."
      />
    );
  }

  return (
    <ol className="h-full overflow-y-auto scroll-thin p-3">
      {run.agent_traces.map((trace, index) => (
        <li key={`${trace.agent}-${index}`} className="relative border-l border-edge pb-4 pl-4 last:pb-0">
          <span
            aria-hidden="true"
            className="absolute top-1 -left-[5px] size-2.5 rounded-full border-2 border-surface bg-accent"
          />
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="accent">{trace.agent}</Badge>
            <span className="text-[11px] text-fg-subtle">{trace.phase}</span>
            {typeof trace.duration_ms === 'number' ? (
              <span className="font-mono text-[11px] text-fg-subtle">
                {formatDuration(trace.duration_ms)}
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-xs leading-relaxed">{trace.summary}</p>
          {Object.keys(trace.details).length > 0 ? (
            <details className="mt-1">
              <summary className="cursor-pointer text-[11px] text-fg-subtle">Evidence</summary>
              <pre className="scroll-thin mt-1 max-h-48 overflow-auto rounded-md border border-edge bg-surface-2 p-2 font-mono text-[11px] whitespace-pre-wrap text-fg-muted">
                {JSON.stringify(trace.details, null, 2)}
              </pre>
            </details>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

/** The behavioural tests synthesised or supplied for the sandbox. */
export function TestsTab({ run }: { run: RunRecord }) {
  if (!run.auto_generated_tests) {
    return (
      <EmptyState
        title="No test source stored"
        description="This run did not store generated tests. The sandbox still executed any supplied test file."
      />
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col p-3">
      <p className="mb-2 text-[11px] text-fg-subtle">
        Executed inside the isolated sandbox runner — the API process never runs this code.
      </p>
      <CodeBlock code={run.auto_generated_tests} className="min-h-0 flex-1" />
    </div>
  );
}

interface GraphNodePosition {
  id: string;
  label: string;
  type: string;
  line: number;
  complexity: number;
  hasSmell: boolean;
  x: number;
  y: number;
}

/** 2D structure graph of the analysed module (deterministic tidy layout). */
export function GraphTab({ run }: { run: RunRecord }) {
  const graph: AstGraph | null = run.ast_graph_before ?? run.ast_graph_after;

  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [] as GraphNodePosition[], edges: [] as [string, string][] };
    const children = new Map<string, string[]>();
    const isChild = new Set<string>();
    for (const edge of graph.edges) {
      const list = children.get(edge.source) ?? [];
      list.push(edge.target);
      children.set(edge.source, list);
      isChild.add(edge.target);
    }
    const roots = graph.nodes.filter((node) => !isChild.has(node.id));
    const positions: GraphNodePosition[] = [];
    let column = 0;
    const visit = (id: string, depth: number) => {
      const node = graph.nodes.find((entry) => entry.id === id);
      if (!node) return;
      const kids = children.get(id) ?? [];
      if (kids.length === 0) {
        positions.push({
          id: node.id,
          label: node.label,
          type: node.type,
          line: node.line,
          complexity: node.complexity,
          hasSmell: node.has_smell,
          x: column * 190,
          y: depth * 76,
        });
        column += 1;
        return;
      }
      for (const kid of kids) visit(kid, depth + 1);
      const first = positions[positions.length - kids.length];
      const last = positions[positions.length - 1];
      positions.push({
        id: node.id,
        label: node.label,
        type: node.type,
        line: node.line,
        complexity: node.complexity,
        hasSmell: node.has_smell,
        x: ((first?.x ?? 0) + (last?.x ?? 0)) / 2,
        y: depth * 76,
      });
    };
    for (const root of roots) visit(root.id, 0);
    const byId = new Map(positions.map((entry) => [entry.id, entry]));
    const drawn = graph.edges
      .map((edge) => [edge.source, edge.target] as [string, string])
      .filter(([source, target]) => byId.has(source) && byId.has(target));
    return { nodes: positions, edges: drawn };
  }, [graph]);

  if (!graph || nodes.length === 0) {
    return (
      <EmptyState
        title="No structure graph"
        description="This run did not store an AST structure graph for the analysed module."
      />
    );
  }

  const width = Math.max(...nodes.map((node) => node.x)) + 200;
  const height = Math.max(...nodes.map((node) => node.y)) + 90;

  return (
    <div className="h-full overflow-auto scroll-thin p-3">
      <svg
        role="img"
        aria-label="Structure graph of the analysed module"
        viewBox={`0 0 ${width} ${height}`}
        width={width}
        height={height}
        className="max-w-full"
      >
        {edges.map(([source, target]) => {
          const from = nodes.find((node) => node.id === source);
          const to = nodes.find((node) => node.id === target);
          if (!from || !to) return null;
          return (
            <line
              key={`${source}-${target}`}
              x1={from.x + 80}
              y1={from.y + 26}
              x2={to.x + 80}
              y2={to.y}
              stroke="currentColor"
              strokeOpacity={0.25}
              strokeWidth={1.5}
            />
          );
        })}
        {nodes.map((node) => (
          <g key={node.id} transform={`translate(${node.x}, ${node.y})`}>
            <rect
              width={160}
              height={52}
              rx={8}
              className={node.hasSmell ? 'fill-danger-soft stroke-danger' : 'fill-surface-2 stroke-edge'}
              strokeWidth={1}
            />
            <text x={10} y={20} className="fill-fg text-[11px] font-medium">
              {node.label.length > 22 ? `${node.label.slice(0, 21)}…` : node.label}
            </text>
            <text x={10} y={38} className="fill-fg-subtle text-[10px]">
              {node.type} · line {node.line} · cc {node.complexity}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

/** Raw unified diff fallback (used when the candidate has no Monaco diff). */
export function RawDiffTab({ run }: { run: RunRecord }) {
  return <DiffBlock diff={run.diff} className="m-3" />;
}
