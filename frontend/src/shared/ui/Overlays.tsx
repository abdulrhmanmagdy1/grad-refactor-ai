import { useEffect, useId, useRef, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

import { cn } from '@/shared/lib/cn';
import { IconButton } from './Button';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'textarea:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

/** Move focus into the overlay and keep it trapped while it is open. */
function useFocusTrap(open: boolean, onClose: () => void) {
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return undefined;

    const previouslyFocused = document.activeElement as HTMLElement | null;
    const panel = panelRef.current;
    const first = panel?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
    (first ?? panel)?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !panel) return;
      const items = Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
        (element) => element.offsetParent !== null,
      );
      if (items.length === 0) return;
      const firstItem = items[0];
      const lastItem = items[items.length - 1];
      if (event.shiftKey && document.activeElement === firstItem) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && document.activeElement === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown, true);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.body.style.overflow = previousOverflow;
      previouslyFocused?.focus?.();
    };
  }, [open, onClose]);

  return panelRef;
}

export interface DialogProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  size?: 'sm' | 'md' | 'lg';
}

/** Accessible modal dialog: focus is trapped, Escape closes, focus is restored. */
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = 'md',
}: DialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useFocusTrap(open, onClose);

  if (!open) return null;

  const width = size === 'sm' ? 'max-w-sm' : size === 'lg' ? 'max-w-3xl' : 'max-w-xl';

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-overlay backdrop-blur-[2px]" aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        className={cn(
          'relative z-10 flex max-h-[85vh] w-full flex-col overflow-hidden rounded-lg border border-edge bg-surface shadow-lg',
          width,
        )}
      >
        <div className="flex items-start gap-3 border-b border-edge px-4 py-3">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-sm font-semibold">
              {title}
            </h2>
            {description ? (
              <p id={descriptionId} className="mt-0.5 text-xs text-fg-muted">
                {description}
              </p>
            ) : null}
          </div>
          <IconButton label="Close dialog" onClick={onClose}>
            <span aria-hidden="true">✕</span>
          </IconButton>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto scroll-thin p-4">{children}</div>
        {footer ? (
          <div className="flex items-center justify-end gap-2 border-t border-edge bg-surface-2 px-4 py-3">
            {footer}
          </div>
        ) : null}
      </div>
    </div>,
    document.body,
  );
}

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  width?: string;
  side?: 'right' | 'left';
}

/** Slide-over panel used for the run history and the comparison view. */
export function Drawer({ open, onClose, title, children, width = 'w-[26rem]', side = 'right' }: DrawerProps) {
  const titleId = useId();
  const panelRef = useFocusTrap(open, onClose);

  if (!open) return null;

  return createPortal(
    <div className="fixed inset-0 z-40 flex">
      <div className="absolute inset-0 bg-overlay" aria-hidden="true" />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className={cn(
          'relative z-10 ml-auto flex h-full flex-col border-edge bg-surface shadow-lg',
          side === 'right' ? 'border-l' : 'mr-auto border-r',
          width,
        )}
      >
        <div className="flex shrink-0 items-center gap-2 border-b border-edge px-3 py-2.5">
          <h2 id={titleId} className="text-sm font-semibold">
            {title}
          </h2>
          <IconButton label="Close panel" className="ml-auto" onClick={onClose}>
            <span aria-hidden="true">✕</span>
          </IconButton>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto scroll-thin">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
