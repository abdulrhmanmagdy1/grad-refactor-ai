import type { ReactNode } from 'react';

import { cn } from '@/shared/lib/cn';
import { formatDelta, formatNumber } from '@/shared/lib/format';
import { Button } from './Button';

export type BadgeTone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info';

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-surface-2 text-fg-muted border-edge',
  accent: 'bg-accent-soft text-accent border-transparent',
  success: 'bg-success-soft text-success border-transparent',
  warning: 'bg-warning-soft text-warning border-transparent',
  danger: 'bg-danger-soft text-danger border-transparent',
  info: 'bg-info-soft text-info border-transparent',
};

/** Small status chip. */
export function Badge({
  children,
  tone = 'neutral',
  className,
  title,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium whitespace-nowrap',
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const RUN_STATUS_TONE: Record<string, BadgeTone> = {
  queued: 'neutral',
  analyzing: 'info',
  generating: 'info',
  verifying: 'accent',
  completed: 'success',
  failed: 'danger',
};

/** Badge that renders a run status with the matching semantic colour. */
export function RunStatusBadge({ status, className }: { status: string; className?: string }) {
  return (
    <Badge tone={RUN_STATUS_TONE[status] ?? 'neutral'} className={className}>
      <span
        aria-hidden="true"
        className={cn(
          'size-1.5 rounded-full',
          status === 'completed'
            ? 'bg-success'
            : status === 'failed'
              ? 'bg-danger'
              : 'bg-current opacity-70',
        )}
      />
      {status}
    </Badge>
  );
}

/** Verdict badge for the review agent (approved / rejected / uncertain). */
export function VerdictBadge({ verdict, className }: { verdict: string; className?: string }) {
  const tone: BadgeTone =
    verdict === 'approved' ? 'success' : verdict === 'rejected' ? 'danger' : 'warning';
  return (
    <Badge tone={tone} className={className}>
      {verdict}
    </Badge>
  );
}

/** Placeholder block shown while data is loading. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn('animate-pulse rounded-md bg-surface-2', className ?? 'h-3 w-full')}
    />
  );
}

/** Friendly zero-state for an empty panel. */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-col items-center justify-center gap-2 px-6 py-10 text-center', className)}>
      {icon ? <div className="text-fg-subtle">{icon}</div> : null}
      <p className="text-sm font-medium">{title}</p>
      {description ? <p className="max-w-sm text-xs text-fg-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

/** Error state with an optional retry action. */
export function ErrorState({
  title = 'Something went wrong',
  message,
  onRetry,
  retryLabel = 'Retry',
  className,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
  retryLabel?: string;
  className?: string;
}) {
  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center gap-2 rounded-md border border-danger/40 bg-danger-soft px-6 py-8 text-center',
        className,
      )}
    >
      <p className="text-sm font-semibold text-danger">{title}</p>
      <p className="max-w-md text-xs text-fg-muted">{message}</p>
      {onRetry ? (
        <Button size="sm" variant="secondary" onClick={onRetry} className="mt-1">
          {retryLabel}
        </Button>
      ) : null}
    </div>
  );
}

/** Determinate progress bar. */
export function ProgressBar({
  value,
  max = 100,
  label,
  className,
}: {
  value: number;
  max?: number;
  label?: string;
  className?: string;
}) {
  const percent = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(percent)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label}
      className={cn('h-1.5 w-full overflow-hidden rounded-full bg-surface-3', className)}
    >
      <div
        className="h-full rounded-full bg-accent transition-[width] duration-300"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}

/** Keyboard hint, e.g. `Ctrl` + `K`. */
export function Kbd({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        'inline-flex h-5 min-w-5 items-center justify-center rounded border border-edge bg-surface-2 px-1.5 font-mono text-[10px] text-fg-muted',
        className,
      )}
    >
      {children}
    </kbd>
  );
}

/** Metric cell that colours positive/negative deltas. */
export function DeltaValue({
  value,
  digits = 2,
  invert = false,
  className,
}: {
  value: number | null | undefined;
  digits?: number;
  invert?: boolean;
  className?: string;
}) {
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return <span className={cn('font-mono text-xs tabular-nums text-fg-subtle', className)}>—</span>;
  }
  const improved = invert ? value < 0 : value > 0;
  const worsened = invert ? value > 0 : value < 0;
  return (
    <span
      className={cn(
        'font-mono text-xs tabular-nums',
        improved ? 'text-success' : worsened ? 'text-danger' : 'text-fg-muted',
        className,
      )}
    >
      {formatDelta(value, digits)}
    </span>
  );
}

/** Plain numeric metric cell. */
export function MetricValue({
  value,
  digits = 2,
  className,
}: {
  value: number | null | undefined;
  digits?: number;
  className?: string;
}) {
  return (
    <span className={cn('font-mono text-xs tabular-nums text-fg', className)}>
      {formatNumber(value, digits)}
    </span>
  );
}
