// @vitest-environment node
/**
 * Optional end-to-end check of the API client and poller against a running service.
 * Skipped unless REFACTOR_AI_E2E_URL is set, for example:
 *
 *   REFACTOR_AI_E2E_URL=http://127.0.0.1:8000 npm test -- src/test/e2e.test.ts
 *
 * It creates and deletes its own runs. With the fake provider its results are plumbing
 * evidence only, never evidence of model behavior.
 */
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createRun,
  deleteRun,
  fetchProposal,
  getHealth,
  getRun,
  listReferenceCases,
  listRuns,
  recordDecision,
} from "../api/client";
import { type ReferenceCaseSummary, type RunRecord, hasProposal } from "../api/contracts";
import { buildSplitRows, parseUnifiedDiff } from "../lib/diff";
import { pollRun } from "../lib/polling";

const base = process.env.REFACTOR_AI_E2E_URL;
const created: string[] = [];

function waitForTerminal(runId: string): Promise<RunRecord> {
  return new Promise((resolve, reject) => {
    pollRun(
      runId,
      getRun,
      (event) => {
        if (event.type === "terminal") resolve(event.record);
        if (event.type === "fatal") reject(event.error);
        if (event.type === "timeout") reject(new Error(`Run ${runId} did not finish`));
      },
      { maxWaitMs: 120_000 },
    );
  });
}

const realFetch = globalThis.fetch;

/** The client uses page-relative URLs; in Node they are sent to the service under test. */
function useServiceBase() {
  vi.stubGlobal("fetch", (input: RequestInfo | URL, init?: RequestInit) =>
    realFetch(typeof input === "string" && input.startsWith("/") ? `${base}${input}` : input, init),
  );
}

describe.skipIf(!base)("end to end against a running service", () => {
  let cases: ReferenceCaseSummary[] = [];

  beforeAll(async () => {
    useServiceBase();
    cases = await listReferenceCases();
  });

  // The test configuration restores stubbed globals before every test.
  beforeEach(useServiceBase);

  afterAll(async () => {
    useServiceBase();
    for (const runId of created) {
      await deleteRun(runId).catch(() => undefined);
    }
    vi.unstubAllGlobals();
  });

  it("reports health with an explicit provider mode", async () => {
    const health = await getHealth();
    expect(["fake", "local_model"]).toContain(health.mode);
    expect(health.queue.max_pending).toBeGreaterThan(0);
  });

  it("runs a demonstration case to a verified result with a parseable diff", { timeout: 150_000 }, async () => {
    expect(cases.length).toBeGreaterThan(0);
    const demo = cases[0]!;
    const accepted = await createRun({
      code: demo.code,
      task_type: "guard_clauses",
      workflow_mode: "multi_role",
      reference_case_id: demo.case_id,
    });
    created.push(accepted.run_id);
    const record = await waitForTerminal(accepted.run_id);
    expect(record.status).toBe("completed");
    expect(record.verification).not.toBeNull();
    if (hasProposal(record)) {
      const parsed = parseUnifiedDiff(record.diff);
      expect(parsed.hunks.length).toBeGreaterThan(0);
      expect(buildSplitRows(record.original_code, record.proposed_code!, parsed)).not.toBeNull();
      const file = await fetchProposal(record.run_id);
      expect(await file.blob.text()).toBe(record.proposed_code);
      expect(file.filename).toBe(`proposal-${record.run_id}.py`);
      const decided = await recordDecision(record.run_id, "rejected");
      expect(decided?.human_decision).toBe("rejected");
      expect((await getRun(record.run_id)).original_code).toBe(demo.code.replace(/\r\n?/g, "\n"));
    }
    const list = await listRuns(5);
    expect(list.runs.some((run) => run.run_id === record.run_id)).toBe(true);
  });

  it("runs single-role without a review", { timeout: 150_000 }, async () => {
    const demo = cases[0]!;
    const accepted = await createRun({ code: demo.code, task_type: "guard_clauses", workflow_mode: "single_role", reference_case_id: null });
    created.push(accepted.run_id);
    const record = await waitForTerminal(accepted.run_id);
    expect(record.workflow_mode).toBe("single_role");
    expect(record.verification?.model_review.status).toBe("not_run");
    expect(record.verification?.reference_tests.status).not.toBe("pass");
  });

  it("returns the documented errors", async () => {
    const syntax = await createRun({ code: "def f(:\n    pass\n" }).catch((error: unknown) => error);
    expect(syntax).toBeInstanceOf(ApiError);
    expect((syntax as ApiError).code).toBe("invalid_syntax");
    expect((syntax as ApiError).details[0]).toMatchObject({ line: 1 });

    const demo = cases[0]!;
    const mismatch = await createRun({ code: `${demo.code}x = 1\n`, reference_case_id: demo.case_id }).catch((error: unknown) => error);
    expect((mismatch as ApiError).code).toBe("reference_case_mismatch");

    const unknown = await createRun({ code: demo.code, reference_case_id: "no_such_case" }).catch((error: unknown) => error);
    expect((unknown as ApiError).code).toBe("unknown_reference_case");

    const missing = await getRun("0".repeat(32)).catch((error: unknown) => error);
    expect((missing as ApiError).code).toBe("run_not_found");
    expect((missing as ApiError).status).toBe(404);
  });

  it("deletes a run", { timeout: 150_000 }, async () => {
    const demo = cases[0]!;
    const accepted = await createRun({ code: demo.code, workflow_mode: "single_role" });
    await waitForTerminal(accepted.run_id);
    await deleteRun(accepted.run_id);
    const gone = await getRun(accepted.run_id).catch((error: unknown) => error);
    expect((gone as ApiError).code).toBe("run_not_found");
  });
});
