// @vitest-environment node
import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { DISCOUNT_CASE, SHIPPING_CASE, accepted, failedRecord, pendingRecord, runRecord } from "../test/fixtures";
import { editorReducer, initialEditorState, linkedCase } from "./editor";
import { initialRunsState, isAnyRunActive, runsReducer, selectedEntry } from "./runs";

const request = { code: "def f(x):\n    return x\n", task_type: "guard_clauses" as const, workflow_mode: "multi_role" as const, reference_case_id: null };
const networkError = new ApiError({ kind: "network", code: "network_error", message: "offline" });

describe("runsReducer", () => {
  it("tracks a submitted run as active and selected", () => {
    const state = runsReducer(initialRunsState, { type: "submitted", accepted: accepted({ run_id: "r1" }), request, now: 1000 });
    const entry = selectedEntry(state)!;
    expect(entry).toMatchObject({ runId: "r1", poll: "polling", pollGeneration: 1, knownStatus: "queued", trackedSince: 1000 });
    expect(entry.statusTrail).toEqual(["queued"]);
    expect(isAnyRunActive(state)).toBe(true);
  });

  it("records poll updates, keeps a distinct status trail and finishes on a terminal record", () => {
    let state = runsReducer(initialRunsState, { type: "submitted", accepted: accepted({ run_id: "r1" }), request, now: 0 });
    const update = (status: "analyzing" | "generating" | "verifying") =>
      runsReducer(state, { type: "poll", runId: "r1", event: { type: "update", record: pendingRecord(status, { run_id: "r1" }) } });
    state = update("analyzing");
    state = update("analyzing");
    state = update("generating");
    state = update("verifying");
    state = update("generating");
    expect(selectedEntry(state)!.statusTrail).toEqual(["queued", "analyzing", "generating", "verifying", "generating"]);
    state = runsReducer(state, { type: "poll", runId: "r1", event: { type: "terminal", record: runRecord({ run_id: "r1" }) } });
    expect(selectedEntry(state)!.poll).toBe("done");
    expect(isAnyRunActive(state)).toBe(false);
  });

  it("keeps the last record while retrying, and records timeouts and fatal errors", () => {
    let state = runsReducer(initialRunsState, { type: "submitted", accepted: accepted({ run_id: "r1" }), request, now: 0 });
    state = runsReducer(state, { type: "poll", runId: "r1", event: { type: "update", record: pendingRecord("generating", { run_id: "r1" }) } });
    state = runsReducer(state, { type: "poll", runId: "r1", event: { type: "retrying", error: networkError, attempt: 2, delayMs: 1688 } });
    expect(selectedEntry(state)!.record?.status).toBe("generating");
    expect(selectedEntry(state)!.retry?.attempt).toBe(2);
    const timedOut = runsReducer(state, { type: "poll", runId: "r1", event: { type: "timeout", waitedMs: 1200000, lastError: networkError } });
    expect(selectedEntry(timedOut)).toMatchObject({ poll: "timed_out", timedOutAfterMs: 1200000, error: networkError, retry: null });
    const resumed = runsReducer(timedOut, { type: "resume", runId: "r1" });
    expect(selectedEntry(resumed)).toMatchObject({ poll: "polling", pollGeneration: 2, error: null, timedOutAfterMs: null });
    const notFound = new ApiError({ kind: "http", status: 404, code: "run_not_found", message: "Run not found." });
    const fatal = runsReducer(state, { type: "poll", runId: "r1", event: { type: "fatal", error: notFound } });
    expect(selectedEntry(fatal)).toMatchObject({ poll: "failed", error: notFound });
  });

  it("ignores poll events after polling stopped", () => {
    let state = runsReducer(initialRunsState, { type: "submitted", accepted: accepted({ run_id: "r1" }), request, now: 0 });
    state = runsReducer(state, { type: "poll", runId: "r1", event: { type: "terminal", record: runRecord({ run_id: "r1" }) } });
    const late = runsReducer(state, { type: "poll", runId: "r1", event: { type: "update", record: pendingRecord("generating", { run_id: "r1" }) } });
    expect(late).toBe(state);
  });

  it("opens a stored run, loads it and starts polling only when it is unfinished", () => {
    let state = runsReducer(initialRunsState, { type: "open", runId: "done", now: 5 });
    expect(selectedEntry(state)).toMatchObject({ loading: true, poll: "idle", record: null });
    state = runsReducer(state, { type: "loaded", record: runRecord({ run_id: "done" }) });
    expect(selectedEntry(state)).toMatchObject({ loading: false, poll: "done" });

    state = runsReducer(state, { type: "open", runId: "busy", now: 6 });
    state = runsReducer(state, { type: "loaded", record: pendingRecord("verifying", { run_id: "busy" }) });
    expect(selectedEntry(state)).toMatchObject({ poll: "polling", pollGeneration: 1, knownStatus: "verifying" });
    expect(isAnyRunActive(state)).toBe(true);
  });

  it("records load failures and ignores records for runs it does not track", () => {
    let state = runsReducer(initialRunsState, { type: "open", runId: "r9", now: 0 });
    state = runsReducer(state, { type: "load_failed", runId: "r9", error: networkError });
    expect(selectedEntry(state)).toMatchObject({ loading: false, error: networkError });
    const untouched = runsReducer(state, { type: "loaded", record: runRecord({ run_id: "unknown" }) });
    expect(untouched).toBe(state);
  });

  it("does not restart polling when an active run is opened again", () => {
    let state = runsReducer(initialRunsState, { type: "submitted", accepted: accepted({ run_id: "r1" }), request, now: 0 });
    state = runsReducer(state, { type: "select", runId: null });
    state = runsReducer(state, { type: "open", runId: "r1", now: 9 });
    expect(selectedEntry(state)).toMatchObject({ runId: "r1", poll: "polling", pollGeneration: 1, loading: false });
  });

  it("forgets a deleted run and clears the selection", () => {
    let state = runsReducer(initialRunsState, { type: "open", runId: "r1", now: 0 });
    state = runsReducer(state, { type: "loaded", record: failedRecord({ run_id: "r1" }) });
    state = runsReducer(state, { type: "removed", runId: "r1" });
    expect(state).toEqual({ entries: {}, selectedId: null });
  });
});

describe("editorReducer", () => {
  it("links a loaded case until the code is edited, and relinks when the edit is undone", () => {
    let state = editorReducer(initialEditorState, { type: "load_case", referenceCase: SHIPPING_CASE });
    expect(state.code).toBe(SHIPPING_CASE.code);
    expect(linkedCase(state)?.case_id).toBe("shipping_cost");
    state = editorReducer(state, { type: "edit", code: `${SHIPPING_CASE.code}# note\n` });
    expect(linkedCase(state)).toBeNull();
    expect(state.loadedCase?.case_id).toBe("shipping_cost");
    state = editorReducer(state, { type: "edit", code: SHIPPING_CASE.code });
    expect(linkedCase(state)?.case_id).toBe("shipping_cost");
  });

  it("keeps the link when only trailing whitespace changes, as the service does", () => {
    let state = editorReducer(initialEditorState, { type: "load_case", referenceCase: SHIPPING_CASE });
    state = editorReducer(state, { type: "edit", code: `${SHIPPING_CASE.code}\n\n` });
    expect(linkedCase(state)?.case_id).toBe("shipping_cost");
  });

  it("offers the replaced code back, and restores it with its own case link", () => {
    let state = editorReducer(initialEditorState, { type: "edit", code: "def mine():\n    return 1\n" });
    state = editorReducer(state, { type: "load_case", referenceCase: SHIPPING_CASE });
    expect(state.restore?.code).toBe("def mine():\n    return 1\n");
    // Loading a second case keeps the person's own code as the restore point.
    state = editorReducer(state, { type: "load_case", referenceCase: DISCOUNT_CASE });
    expect(state.restore?.code).toBe("def mine():\n    return 1\n");
    state = editorReducer(state, { type: "restore" });
    expect(state).toMatchObject({ code: "def mine():\n    return 1\n", loadedCase: null, restore: null });
  });

  it("does not offer a restore point for blank or identical content", () => {
    const fromBlank = editorReducer(initialEditorState, { type: "load_case", referenceCase: SHIPPING_CASE });
    expect(fromBlank.restore).toBeNull();
    const same = editorReducer(
      { ...initialEditorState, code: SHIPPING_CASE.code },
      { type: "load_case", referenceCase: SHIPPING_CASE },
    );
    expect(same.restore).toBeNull();
  });

  it("loads a run's input with its workflow mode and normalized newlines", () => {
    const state = editorReducer(initialEditorState, {
      type: "load_input",
      code: "def f():\r\n    return 1\r\n",
      mode: "single_role",
      linkedCase: null,
      label: "run abc",
    });
    expect(state).toMatchObject({ code: "def f():\n    return 1\n", workflowMode: "single_role", loadedCase: null });
  });

  it("restores the case code and removes the link on request", () => {
    let state = editorReducer(initialEditorState, { type: "load_case", referenceCase: SHIPPING_CASE });
    state = editorReducer(state, { type: "edit", code: "changed" });
    state = editorReducer(state, { type: "reset_case_code" });
    expect(linkedCase(state)?.case_id).toBe("shipping_cost");
    state = editorReducer(state, { type: "unlink_case" });
    expect(state.loadedCase).toBeNull();
    expect(state.code).toBe(SHIPPING_CASE.code);
  });
});
