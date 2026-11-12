import type { ReactNode } from 'react';

import { cn } from '@/shared/lib/cn';

/** Card-like container used by every workspace panel. */
export function Panel({
  children,
  className,
  as: Tag = 'section',
}: {
  children: ReactNode;
  className?: string;
  as?: 'section' | 'div' | 'aside';
}) {
  return (
    <Tag
      className={cn(
        'flex min-h-0 flex-col overflow-hidden rounded-lg border border-edge bg-surface shadow-sm',
        className,
      )}
    >
      {children}
    </Tag>
  );
}

/** Sticky panel header with an optional title, meta and actions. */
export function PanelHeader({
  title,
  meta,
  actions,
  children,
  className,
}: {
  title?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        'flex min-h-11 shrink-0 items-center gap-2 border-b border-edge px-3 py-1.5',
        className,
      )}
    >
      {title ? <h2 className="text-sm font-semibold tracking-tight">{title}</h2> : null}
      {meta ? <div className="truncate text-xs text-fg-subtle">{meta}</div> : null}
      {children}
      {actions ? <div className="ml-auto flex items-center gap-1">{actions}</div> : null}
    </header>
  );
}

/** Scrollable panel body. */
export function PanelBody({
  children,
  className,
  padded = true,
}: {
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <div
      className={cn(
        'min-h-0 flex-1 overflow-y-auto scroll-thin',
        padded && 'p-3',
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Small uppercase section label used inside panels. */
export function SectionLabel({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cn('text-[11px] font-semibold uppercase tracking-wider text-fg-subtle', className)}>
      {children}
    </p>
  );
}

/** Two-column key/value row used by the metric and overview tables. */
export function KeyValue({
  label,
  value,
  tone = 'default',
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  tone?: 'default' | 'positive' | 'negative' | 'muted';
  className?: string;
}) {
  const toneClass =
    tone === 'positive'
      ? 'text-success'
      : tone === 'negative'
        ? 'text-danger'
        : tone === 'muted'
          ? 'text-fg-subtle'
          : 'text-fg';
  return (
    <div className={cn('flex items-baseline justify-between gap-3 py-1', className)}>
      <span className="text-xs text-fg-muted">{label}</span>
      <span className={cn('font-mono text-xs tabular-nums', toneClass)}>{value}</span>
    </div>
  );
}
