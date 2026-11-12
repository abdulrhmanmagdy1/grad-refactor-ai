import type { ButtonHTMLAttributes, ReactNode } from 'react';

import { cn } from '@/shared/lib/cn';

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success';
export type ButtonSize = 'sm' | 'md';

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-accent text-on-accent hover:bg-accent-strong disabled:hover:bg-accent shadow-sm border border-transparent',
  secondary:
    'bg-surface-2 text-fg hover:bg-surface-3 border border-edge disabled:hover:bg-surface-2',
  ghost: 'bg-transparent text-fg-muted hover:bg-surface-2 hover:text-fg border border-transparent',
  danger: 'bg-danger-soft text-danger hover:bg-danger hover:text-on-accent border border-transparent',
  success: 'bg-success-soft text-success hover:bg-success hover:text-on-accent border border-transparent',
};

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-7 px-2.5 text-xs gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-2',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shows a spinner and blocks interaction while the action is running. */
  loading?: boolean;
  icon?: ReactNode;
}

/** Primary interactive control used across the interface. */
export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  icon,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center rounded-md font-medium transition-colors duration-150',
        'disabled:cursor-not-allowed disabled:opacity-55',
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Spinner size={14} /> : icon}
      {children}
    </button>
  );
}

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Required: rendered as the accessible name and the native tooltip. */
  label: string;
  size?: ButtonSize;
  active?: boolean;
}

/** Compact icon-only control; the label is mandatory for accessibility. */
export function IconButton({
  label,
  size = 'sm',
  active = false,
  className,
  type = 'button',
  ...rest
}: IconButtonProps) {
  return (
    <button
      type={type}
      title={label}
      aria-label={label}
      className={cn(
        'inline-flex items-center justify-center rounded-md transition-colors duration-150',
        'disabled:cursor-not-allowed disabled:opacity-45',
        size === 'sm' ? 'h-7 w-7' : 'h-9 w-9',
        active
          ? 'bg-accent-soft text-accent'
          : 'text-fg-muted hover:bg-surface-2 hover:text-fg',
        className,
      )}
      {...rest}
    />
  );
}

export interface SpinnerProps {
  size?: number;
  className?: string;
  label?: string;
}

/** Indeterminate progress indicator. */
export function Spinner({ size = 16, className, label }: SpinnerProps) {
  return (
    <span
      role={label ? 'status' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      className={cn(
        'inline-block animate-spin rounded-full border-2 border-current border-t-transparent',
        className,
      )}
      style={{ width: size, height: size }}
    />
  );
}
