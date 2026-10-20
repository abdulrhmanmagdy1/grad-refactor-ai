import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { type ApiError, toApiError } from "../api/client";

export interface ResourceState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
}

/**
 * Loads data on mount, whenever `key` changes, on refresh() and optionally every
 * refreshMs. Only the latest request may update the state; an older answer arriving late
 * is ignored, and the last good data is kept when a refresh fails.
 */
export function useResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  options: { refreshMs?: number; key?: string | number } = {},
): ResourceState<T> & { refresh: () => void } {
  const [state, setState] = useState<ResourceState<T>>({ data: null, error: null, loading: true });
  const loadRef = useRef(load);
  const controllerRef = useRef<AbortController | null>(null);

  useLayoutEffect(() => {
    loadRef.current = load;
  });

  const refresh = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setState((previous) => ({ ...previous, loading: true }));
    loadRef.current(controller.signal).then(
      (data) => {
        if (controllerRef.current === controller) setState({ data, error: null, loading: false });
      },
      (error: unknown) => {
        if (controllerRef.current === controller) {
          setState((previous) => ({ data: previous.data, error: toApiError(error), loading: false }));
        }
      },
    );
  }, []);

  const { refreshMs, key } = options;
  useEffect(() => {
    refresh();
    const id = refreshMs ? setInterval(refresh, refreshMs) : null;
    return () => {
      if (id !== null) clearInterval(id);
      controllerRef.current?.abort();
      controllerRef.current = null;
    };
  }, [refresh, refreshMs, key]);

  return { ...state, refresh };
}
