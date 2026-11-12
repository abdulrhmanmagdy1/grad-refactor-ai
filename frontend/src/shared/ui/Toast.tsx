import { AlertTriangle, CheckCircle2, Info, X, XCircle } from 'lucide-react';

import { cn } from '@/shared/lib/cn';
import { IconButton } from './Button';
import { useToastStore, type ToastKind } from './toast.store';

const ICONS: Record<ToastKind, typeof Info> = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

const TONES: Record<ToastKind, string> = {
  success: 'text-success',
  error: 'text-danger',
  warning: 'text-warning',
  info: 'text-info',
};

/** Live region that renders transient notifications. */
export function Toaster() {
  const toasts = useToastStore((state) => state.toasts);
  const dismiss = useToastStore((state) => state.dismiss);

  return (
    <div
      aria-live="polite"
      aria-atomic="false"
      className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-full max-w-sm flex-col gap-2"
    >
      {toasts.map((item) => {
        const Icon = ICONS[item.kind];
        return (
          <div
            key={item.id}
            role={item.kind === 'error' ? 'alert' : 'status'}
            className={cn(
              'pointer-events-auto flex items-start gap-2.5 rounded-lg border border-edge bg-surface p-3 shadow-md',
              'animate-[fade-in_160ms_ease-out]',
            )}
          >
            <Icon size={16} className={cn('mt-0.5 shrink-0', TONES[item.kind])} aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="text-xs leading-snug font-medium break-words">{item.text}</p>
              {item.detail ? (
                <p className="mt-0.5 text-[11px] leading-snug text-fg-muted break-words">{item.detail}</p>
              ) : null}
            </div>
            <IconButton label="Dismiss notification" onClick={() => dismiss(item.id)}>
              <X size={13} aria-hidden="true" />
            </IconButton>
          </div>
        );
      })}
    </div>
  );
}
