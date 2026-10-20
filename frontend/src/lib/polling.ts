/**
 * Bounded polling of GET /api/v1/runs/{run_id}.
 *
 * One request at a time: the next poll is scheduled only after the previous one settles.
 * The delay starts at 750 ms, grows by 1.5x up to 3 s while the status stays the same and
 * returns to 750 ms whenever the status changes. Polling stops on a terminal status, on
 * stop() (for example when the component unmounts), on an error that a retry cannot fix
 * (such as 404 run_not_found) and after the maximum wait. Network problems and busy or
 * proxy errors are retried with the same backoff; the last known record is kept by the
 * caller, so nothing is lost while the connection recovers.
 */

import { type ApiError, toApiError } from "../api/client";
import { type RunRecord, type RunStatus, isTerminalStatus } from "../api/contracts";

export interface PollOptions {
  /** First and post-status-change delay. */
  initialDelayMs: number;
  /** Upper bound of the delay. */
  maxDelayMs: number;
  /** Growth factor applied while the status is unchanged or a request fails. */
  backoffFactor: number;
  /** Polling gives up after this long. */
  maxWaitMs: number;
  /** Delay before the very first request; defaults to initialDelayMs. */
  firstDelayMs?: number;
  /** Status already known to the caller (for example from RunAccepted). */
  initialStatus?: RunStatus | null;
}

export const DEFAULT_POLL_OPTIONS: Readonly<PollOptions> = {
  initialDelayMs: 750,
  maxDelayMs: 3_000,
  backoffFactor: 1.5,
  maxWaitMs: 20 * 60_000,
};

/**
 * Maximum wait for a run: at least the default, and at least twice the run's own
 * time budget (WorkflowSettings.run_timeout_s) so queue time is covered as well.
 */
export function maxWaitForRun(runTimeoutSeconds: number | null | undefined): number {
  const budget =
    typeof runTimeoutSeconds === "number" && Number.isFinite(runTimeoutSeconds) && runTimeoutSeconds > 0
      ? runTimeoutSeconds * 2_000
      : 0;
  return Math.max(DEFAULT_POLL_OPTIONS.maxWaitMs, budget);
}

export function nextDelay(currentMs: number, options: Pick<PollOptions, "maxDelayMs" | "backoffFactor">): number {
  return Math.min(options.maxDelayMs, Math.round(currentMs * options.backoffFactor));
}

export type RunFetcher = (runId: string, signal: AbortSignal) => Promise<RunRecord>;

export type PollEvent =
  | { type: "update"; record: RunRecord }
  | { type: "terminal"; record: RunRecord }
  | { type: "retrying"; error: ApiError; attempt: number; delayMs: number }
  | { type: "fatal"; error: ApiError }
  | { type: "timeout"; waitedMs: number; lastError: ApiError | null };

export interface PollHandle {
  stop(): void;
  readonly stopped: boolean;
}

export function pollRun(
  runId: string,
  fetchRun: RunFetcher,
  onEvent: (event: PollEvent) => void,
  overrides: Partial<PollOptions> = {},
): PollHandle {
  const options: PollOptions = { ...DEFAULT_POLL_OPTIONS, ...overrides };
  const startedAt = Date.now();
  let delay = options.initialDelayMs;
  let lastStatus: RunStatus | null = options.initialStatus ?? null;
  let failures = 0;
  let lastError: ApiError | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let controller: AbortController | null = null;
  let stopped = false;

  const stop = () => {
    stopped = true;
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
    controller?.abort();
    controller = null;
  };

  const schedule = (ms: number) => {
    if (stopped) return;
    const remaining = options.maxWaitMs - (Date.now() - startedAt);
    // Wake up no later than the deadline so the timeout is reported promptly.
    timer = setTimeout(() => void tick(), Math.max(0, Math.min(ms, remaining)));
  };

  const tick = async () => {
    timer = null;
    if (stopped) return;
    const waited = Date.now() - startedAt;
    if (waited >= options.maxWaitMs) {
      stop();
      onEvent({ type: "timeout", waitedMs: waited, lastError });
      return;
    }

    const current = new AbortController();
    controller = current;
    let record: RunRecord;
    try {
      record = await fetchRun(runId, current.signal);
    } catch (error) {
      if (stopped) return;
      controller = null;
      const apiError = toApiError(error);
      if (!apiError.transient) {
        stop();
        onEvent({ type: "fatal", error: apiError });
        return;
      }
      failures += 1;
      lastError = apiError;
      delay = nextDelay(delay, options);
      onEvent({ type: "retrying", error: apiError, attempt: failures, delayMs: delay });
      schedule(delay);
      return;
    }
    if (stopped) return;
    controller = null;
    failures = 0;
    lastError = null;

    if (isTerminalStatus(record.status)) {
      stop();
      onEvent({ type: "terminal", record });
      return;
    }
    delay = record.status === lastStatus ? nextDelay(delay, options) : options.initialDelayMs;
    lastStatus = record.status;
    onEvent({ type: "update", record });
    schedule(delay);
  };

  schedule(options.firstDelayMs ?? options.initialDelayMs);

  return {
    stop,
    get stopped() {
      return stopped;
    },
  };
}
