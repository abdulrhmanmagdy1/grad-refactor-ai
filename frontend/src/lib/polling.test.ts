// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type { RunRecord, RunStatus } from "../api/contracts";
import { pendingRecord, runRecord } from "../test/fixtures";
import { DEFAULT_POLL_OPTIONS, type PollEvent, maxWaitForRun, nextDelay, pollRun } from "./polling";

const networkError = () =>
  new ApiError({ kind: "network", code: "network_error", message: "Cannot reach the refactoring service." });

/** A fetcher that answers with the given statuses in order and records the call times. */
function scripted(statuses: Array<RunStatus | ApiError | Error>) {
  const times: number[] = [];
  const signals: AbortSignal[] = [];
  const fetchRun = vi.fn(async (_runId: string, signal: AbortSignal): Promise<RunRecord> => {
    times.push(Date.now());
    signals.push(signal);
    const next = statuses.shift();
    if (next === undefined) throw new Error("No scripted answer left");
    if (next instanceof Error) throw next;
    return next === "completed" ? runRecord() : pendingRecord(next);
  });
  return { fetchRun, times, signals };
}

describe("pollRun", () => {
  let start: number;

  beforeEach(() => {
    vi.useFakeTimers();
    start = Date.now();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("waits the initial delay before the first request", async () => {
    const { fetchRun } = scripted(["queued"]);
    pollRun("run-1", fetchRun, () => undefined, { initialStatus: "queued" });
    await vi.advanceTimersByTimeAsync(749);
    expect(fetchRun).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(fetchRun).toHaveBeenCalledTimes(1);
    expect(fetchRun.mock.calls[0]![0]).toBe("run-1");
  });

  it("grows the delay by 1.5x up to 3 s while the status stays the same", async () => {
    const { fetchRun, times } = scripted(["queued", "queued", "queued", "queued", "queued", "queued"]);
    const handle = pollRun("run-1", fetchRun, () => undefined, { initialStatus: "queued" });
    // The sixth request is due at 12,095 ms and the seventh would be at 15,095 ms.
    await vi.advanceTimersByTimeAsync(12_100);
    handle.stop();
    const offsets = times.map((time) => time - start);
    expect(offsets).toEqual([750, 750 + 1125, 750 + 1125 + 1688, 750 + 1125 + 1688 + 2532, 9095, 12095]);
  });

  it("returns to the initial delay when the status changes", async () => {
    const { fetchRun, times } = scripted(["queued", "analyzing", "analyzing", "generating", "generating"]);
    const handle = pollRun("run-1", fetchRun, () => undefined, { initialStatus: "queued" });
    await vi.advanceTimersByTimeAsync(5_000);
    handle.stop();
    const gaps = times.slice(1).map((time, index) => time - times[index]!);
    // queued (unchanged) -> 1125, analyzing (changed) -> 750, analyzing -> 1125, generating -> 750
    expect(gaps).toEqual([1125, 750, 1125, 750]);
  });

  it("reports updates and stops for good on a terminal status", async () => {
    const events: PollEvent[] = [];
    const { fetchRun } = scripted(["analyzing", "completed"]);
    const handle = pollRun("run-1", fetchRun, (event) => events.push(event), { initialStatus: "queued" });
    await vi.advanceTimersByTimeAsync(60_000);
    expect(events.map((event) => event.type)).toEqual(["update", "terminal"]);
    expect(fetchRun).toHaveBeenCalledTimes(2);
    expect(handle.stopped).toBe(true);
  });

  it("treats failed as terminal", async () => {
    const events: PollEvent[] = [];
    pollRun("run-1", scripted(["failed"]).fetchRun, (event) => events.push(event));
    await vi.advanceTimersByTimeAsync(10_000);
    expect(events).toHaveLength(1);
    expect(events[0]!.type).toBe("terminal");
  });

  it("stop() cancels the next request and aborts the one in flight", async () => {
    const events: PollEvent[] = [];
    let release: ((record: RunRecord) => void) | undefined;
    let seenSignal: AbortSignal | undefined;
    const fetchRun = vi.fn(
      (_runId: string, signal: AbortSignal) =>
        new Promise<RunRecord>((resolve) => {
          seenSignal = signal;
          release = resolve;
        }),
    );
    const handle = pollRun("run-1", fetchRun, (event) => events.push(event));
    await vi.advanceTimersByTimeAsync(750);
    expect(fetchRun).toHaveBeenCalledTimes(1);
    handle.stop();
    expect(seenSignal?.aborted).toBe(true);
    release?.(runRecord());
    await vi.advanceTimersByTimeAsync(60_000);
    expect(events).toEqual([]);
    expect(fetchRun).toHaveBeenCalledTimes(1);
  });

  it("stop() before the first request means no request at all", async () => {
    const { fetchRun } = scripted(["queued"]);
    pollRun("run-1", fetchRun, () => undefined).stop();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetchRun).not.toHaveBeenCalled();
  });

  it("gives up after the maximum wait and reports how long it waited", async () => {
    const events: PollEvent[] = [];
    const fetchRun = vi.fn(async () => pendingRecord("generating"));
    pollRun("run-1", fetchRun, (event) => events.push(event), { maxWaitMs: 10_000 });
    await vi.advanceTimersByTimeAsync(10_000);
    const calls = fetchRun.mock.calls.length;
    await vi.advanceTimersByTimeAsync(60_000);
    expect(fetchRun.mock.calls.length).toBe(calls);
    const last = events[events.length - 1]!;
    expect(last).toEqual({ type: "timeout", waitedMs: 10_000, lastError: null });
  });

  it("retries network errors with backoff, keeps going and recovers", async () => {
    const events: PollEvent[] = [];
    const { fetchRun, times } = scripted([networkError(), networkError(), "verifying", "completed"]);
    pollRun("run-1", fetchRun, (event) => events.push(event), { initialStatus: "generating" });
    await vi.advanceTimersByTimeAsync(30_000);
    expect(events.map((event) => event.type)).toEqual(["retrying", "retrying", "update", "terminal"]);
    const retry = events[1] as Extract<PollEvent, { type: "retrying" }>;
    expect(retry.attempt).toBe(2);
    expect(retry.error.code).toBe("network_error");
    const gaps = times.slice(1).map((time, index) => time - times[index]!);
    expect(gaps).toEqual([1125, 1688, 750]);
  });

  it("includes the last error when it gives up while the service is unreachable", async () => {
    const events: PollEvent[] = [];
    const fetchRun = vi.fn(async (): Promise<RunRecord> => {
      throw networkError();
    });
    pollRun("run-1", fetchRun, (event) => events.push(event), { maxWaitMs: 5_000 });
    await vi.advanceTimersByTimeAsync(5_000);
    const last = events[events.length - 1] as Extract<PollEvent, { type: "timeout" }>;
    expect(last.type).toBe("timeout");
    expect(last.lastError?.code).toBe("network_error");
  });

  it("retries busy and proxy errors but stops on a missing run", async () => {
    const busy = new ApiError({ kind: "http", status: 503, code: "busy", message: "Queue full" });
    const notFound = new ApiError({ kind: "http", status: 404, code: "run_not_found", message: "Run not found." });
    const events: PollEvent[] = [];
    const { fetchRun } = scripted([busy, notFound, "completed"]);
    pollRun("run-1", fetchRun, (event) => events.push(event));
    await vi.advanceTimersByTimeAsync(30_000);
    expect(events.map((event) => event.type)).toEqual(["retrying", "fatal"]);
    expect(fetchRun).toHaveBeenCalledTimes(2);
  });

  it("treats an unexpected exception as fatal instead of retrying forever", async () => {
    const events: PollEvent[] = [];
    pollRun("run-1", scripted([new TypeError("boom")]).fetchRun, (event) => events.push(event));
    await vi.advanceTimersByTimeAsync(10_000);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ type: "fatal", error: { code: "client_error", message: "boom" } });
  });

  it("supports an immediate first request", async () => {
    const { fetchRun } = scripted(["completed"]);
    pollRun("run-1", fetchRun, () => undefined, { firstDelayMs: 0 });
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchRun).toHaveBeenCalledTimes(1);
  });
});

describe("polling helpers", () => {
  it("caps the delay", () => {
    expect(nextDelay(750, DEFAULT_POLL_OPTIONS)).toBe(1125);
    expect(nextDelay(2532, DEFAULT_POLL_OPTIONS)).toBe(3000);
    expect(nextDelay(3000, DEFAULT_POLL_OPTIONS)).toBe(3000);
  });

  it("waits at least 20 minutes and at least twice the run's own time limit", () => {
    expect(maxWaitForRun(undefined)).toBe(20 * 60_000);
    expect(maxWaitForRun(600)).toBe(20 * 60_000);
    expect(maxWaitForRun(3600)).toBe(2 * 3600 * 1000);
    expect(maxWaitForRun(-5)).toBe(20 * 60_000);
  });
});
