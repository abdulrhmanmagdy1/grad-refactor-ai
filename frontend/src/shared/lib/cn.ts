/** Tiny class-name joiner (no runtime dependency, stable ordering). */
export type ClassValue = string | number | false | null | undefined;

/** Join class names, skipping falsy values. */
export function cn(...values: ClassValue[]): string {
  return values.filter(Boolean).join(' ');
}
