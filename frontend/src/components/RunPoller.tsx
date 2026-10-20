import { useEffect, useLayoutEffect, useRef } from "react";
import { getRun } from "../api/client";
import type { RunStatus } from "../api/contracts";
import { type PollEvent, pollRun } from "../lib/polling";

interface RunPollerProps {
  runId: string;
  /** A new generation starts a fresh poller (first start, reopen, "Check again"). */
  generation: number;
  initialStatus: RunStatus | null;
  maxWaitMs: number;
  onEvent: (runId: string, event: PollEvent) => void;
}

/**
 * Polls one run while mounted. Unmounting (the run finished, was deleted, or the page
 * closed) stops the timer and aborts the request in flight.
 */
export function RunPoller({ runId, generation, initialStatus, maxWaitMs, onEvent }: RunPollerProps) {
  const latest = useRef({ onEvent, initialStatus, maxWaitMs });
  useLayoutEffect(() => {
    latest.current = { onEvent, initialStatus, maxWaitMs };
  });

  useEffect(() => {
    const handle = pollRun(runId, getRun, (event) => latest.current.onEvent(runId, event), {
      initialStatus: latest.current.initialStatus,
      maxWaitMs: latest.current.maxWaitMs,
    });
    return () => handle.stop();
  }, [runId, generation]);

  return null;
}
