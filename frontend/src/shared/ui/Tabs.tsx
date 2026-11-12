import { useRef, type ReactNode } from 'react';

import { cn } from '@/shared/lib/cn';

export interface TabDefinition<T extends string> {
  id: T;
  label: string;
  icon?: ReactNode;
  badge?: ReactNode;
}

/**
 * Accessible tab bar (WAI-ARIA tabs pattern).
 *
 * Arrow keys move between tabs, Home/End jump to the first/last tab, and the
 * active tab is always reachable with a single Tab stop.
 */
export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
  label,
  className,
}: {
  tabs: TabDefinition<T>[];
  value: T;
  onChange: (id: T) => void;
  label: string;
  className?: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);

  const focusTab = (index: number) => {
    const buttons = listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
    buttons?.[index]?.focus();
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = tabs.findIndex((tab) => tab.id === value);
    if (currentIndex < 0) return;

    let nextIndex: number | null = null;
    if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % tabs.length;
    else if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = tabs.length - 1;

    if (nextIndex === null) return;
    event.preventDefault();
    onChange(tabs[nextIndex].id);
    focusTab(nextIndex);
  };

  return (
    <div
      ref={listRef}
      role="tablist"
      aria-label={label}
      tabIndex={-1}
      onKeyDown={onKeyDown}
      className={cn('flex items-center gap-1 overflow-x-auto', className)}
    >
      {tabs.map((tab) => {
        const selected = tab.id === value;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={selected}
            aria-controls={`tabpanel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            className={cn(
              'inline-flex h-8 shrink-0 items-center gap-1.5 rounded-md px-2.5 text-xs font-medium transition-colors',
              selected
                ? 'bg-surface-2 text-fg'
                : 'text-fg-muted hover:bg-surface-2/60 hover:text-fg',
            )}
          >
            {tab.icon ? <span aria-hidden="true">{tab.icon}</span> : null}
            {tab.label}
            {tab.badge}
          </button>
        );
      })}
    </div>
  );
}

/** Body of a tab; `tabpanel` wiring matches the ids produced by `Tabs`. */
export function TabPanel({
  id,
  active,
  children,
  className,
}: {
  id: string;
  active: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      role="tabpanel"
      id={`tabpanel-${id}`}
      aria-labelledby={`tab-${id}`}
      hidden={!active}
      tabIndex={0}
      className={cn('min-h-0 flex-1 focus-visible:outline-none', className)}
    >
      {active ? children : null}
    </div>
  );
}
