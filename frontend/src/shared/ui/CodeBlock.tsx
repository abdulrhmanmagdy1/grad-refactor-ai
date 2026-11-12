import { useMemo } from 'react';

import { cn } from '@/shared/lib/cn';

/**
 * Read-only code viewer.
 *
 * Code is rendered as text nodes only — never as HTML — so submitted source
 * can never be interpreted as markup (XSS). Monaco is used for the editable
 * buffers; this component covers read-only output (tests, generated code).
 */
export function CodeBlock({
  code,
  showLineNumbers = true,
  maxHeight,
  className,
  emptyLabel = 'Nothing to show yet.',
}: {
  code: string | null | undefined;
  showLineNumbers?: boolean;
  maxHeight?: number | string;
  className?: string;
  emptyLabel?: string;
}) {
  const lines = useMemo(() => (code ? code.replace(/\n$/, '').split('\n') : []), [code]);

  if (!code) {
    return <p className="px-3 py-2 text-xs text-fg-subtle">{emptyLabel}</p>;
  }

  return (
    <div
      className={cn('scroll-thin overflow-auto rounded-md border border-edge bg-code-bg', className)}
      style={maxHeight ? { maxHeight } : undefined}
    >
      <pre className="min-w-full font-mono text-[12px] leading-relaxed">
        <code>
          {lines.map((line, index) => (
            <div key={index} className="flex">
              {showLineNumbers ? (
                <span
                  aria-hidden="true"
                  className="sticky left-0 w-10 shrink-0 border-r border-edge bg-surface-2/60 pr-2 text-right text-[11px] text-fg-subtle select-none"
                >
                  {index + 1}
                </span>
              ) : null}
              <span className="px-2 whitespace-pre">{line || ' '}</span>
            </div>
          ))}
        </code>
      </pre>
    </div>
  );
}

/** Unified diff rendered with add/remove colouring. */
export function DiffBlock({
  diff,
  maxHeight,
  className,
}: {
  diff: string | null | undefined;
  maxHeight?: number | string;
  className?: string;
}) {
  const lines = useMemo(() => (diff ? diff.split('\n') : []), [diff]);

  if (!diff) {
    return <p className="px-3 py-2 text-xs text-fg-subtle">No diff was produced for this run.</p>;
  }

  return (
    <div
      className={cn('scroll-thin overflow-auto rounded-md border border-edge bg-code-bg', className)}
      style={maxHeight ? { maxHeight } : undefined}
    >
      <pre className="min-w-full font-mono text-[12px] leading-relaxed">
        <code>
          {lines.map((line, index) => {
            const added = line.startsWith('+') && !line.startsWith('+++');
            const removed = line.startsWith('-') && !line.startsWith('---');
            const hunk = line.startsWith('@@');
            return (
              <div
                key={index}
                className={cn(
                  'whitespace-pre px-2',
                  added && 'bg-diff-add',
                  removed && 'bg-diff-del',
                  hunk && 'text-accent',
                )}
              >
                {line || ' '}
              </div>
            );
          })}
        </code>
      </pre>
    </div>
  );
}
