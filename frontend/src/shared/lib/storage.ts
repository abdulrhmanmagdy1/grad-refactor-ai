/** Namespaced, failure-tolerant localStorage access. */
const PREFIX = 'refactor-ai:';

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Read a JSON value; returns `fallback` when missing or corrupted. */
export function readJson<T>(key: string, fallback: T): T {
  const store = storage();
  if (!store) return fallback;
  try {
    const raw = store.getItem(PREFIX + key);
    if (raw === null) return fallback;
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

/** Persist a JSON value; failures (private mode, quota) are ignored. */
export function writeJson(key: string, value: unknown): void {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Persistence is a convenience, never a requirement.
  }
}

/** Remove a stored value. */
export function removeValue(key: string): void {
  const store = storage();
  if (!store) return;
  try {
    store.removeItem(PREFIX + key);
  } catch {
    // Ignore.
  }
}
