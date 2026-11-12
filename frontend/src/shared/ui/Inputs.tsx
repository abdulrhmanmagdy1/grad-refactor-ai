import { useId, type ReactNode } from 'react';

import { cn } from '@/shared/lib/cn';

/** Labelled native select styled to match the design system. */
export function Select<T extends string>({
  label,
  value,
  onChange,
  options,
  disabled,
  className,
  hint,
}: {
  label: string;
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: string; disabled?: boolean }[];
  disabled?: boolean;
  className?: string;
  hint?: ReactNode;
}) {
  const id = useId();
  const hintId = useId();
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <label htmlFor={id} className="text-[11px] font-medium text-fg-muted">
        {label}
      </label>
      <select
        id={id}
        value={value}
        disabled={disabled}
        aria-describedby={hint ? hintId : undefined}
        onChange={(event) => onChange(event.target.value as T)}
        className="h-8 rounded-md border border-edge bg-surface-2 px-2 text-xs text-fg transition-colors hover:bg-surface-3 disabled:opacity-50"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
      {hint ? (
        <p id={hintId} className="text-[11px] text-fg-subtle">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** Search input with an optional leading icon. */
export function SearchInput({
  value,
  onChange,
  placeholder = 'Search',
  label,
  className,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  label: string;
  className?: string;
}) {
  const id = useId();
  return (
    <div className={cn('relative', className)}>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <input
        id={id}
        type="search"
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className="h-8 w-full rounded-md border border-edge bg-surface-2 pl-2.5 pr-2 text-xs text-fg placeholder:text-fg-subtle focus:border-accent"
      />
    </div>
  );
}

/** Segmented control used for view switches (list/detail, inline/side-by-side). */
export function Segmented<T extends string>({
  label,
  value,
  onChange,
  options,
  className,
}: {
  label: string;
  value: T;
  onChange: (value: T) => void;
  options: { value: T; label: ReactNode; title?: string }[];
  className?: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={cn('inline-flex items-center gap-0.5 rounded-md border border-edge bg-surface-2 p-0.5', className)}
    >
      {options.map((option) => {
        const selected = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={selected}
            title={option.title}
            onClick={() => onChange(option.value)}
            className={cn(
              'inline-flex h-6 items-center gap-1 rounded-sm px-2 text-[11px] font-medium transition-colors',
              selected ? 'bg-surface text-fg shadow-sm' : 'text-fg-muted hover:text-fg',
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/** Numeric field with an inline unit suffix, used for the run budgets. */
export function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
  suffix,
  hint,
  className,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  suffix?: string;
  hint?: string;
  className?: string;
}) {
  const id = useId();
  const hintId = useId();
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <label htmlFor={id} className="text-[11px] font-medium text-fg-muted">
        {label}
      </label>
      <div className="flex items-center gap-1.5">
        <input
          id={id}
          type="number"
          value={value}
          min={min}
          max={max}
          step={step}
          aria-describedby={hint ? hintId : undefined}
          onChange={(event) => {
            const next = Number(event.target.value);
            if (Number.isFinite(next)) onChange(Math.min(max, Math.max(min, next)));
          }}
          className="h-8 w-full rounded-md border border-edge bg-surface-2 px-2 font-mono text-xs text-fg"
        />
        {suffix ? <span className="text-[11px] text-fg-subtle">{suffix}</span> : null}
      </div>
      {hint ? (
        <p id={hintId} className="text-[11px] text-fg-subtle">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** Two-state switch expressed as a toggle button. */
export function Toggle({
  label,
  checked,
  onChange,
  className,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn(
        'relative h-5 w-9 rounded-full border transition-colors',
        checked ? 'border-accent bg-accent' : 'border-edge bg-surface-3',
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          'absolute top-0.5 size-3.5 rounded-full bg-white transition-transform',
          checked ? 'translate-x-4' : 'translate-x-0.5',
        )}
      />
    </button>
  );
}
