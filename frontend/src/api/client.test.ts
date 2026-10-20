// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MockServer, apiError, json } from "../test/mockServer";
import { SHIPPING_CASE, accepted, health, runRecord, runSummary } from "../test/fixtures";
import {
  ApiError,
  DEFAULT_TIMEOUT_MS,
  createRun,
  deleteRun,
  fetchProposal,
  filenameFromContentDisposition,
  getHealth,
  getRun,
  listReferenceCases,
  listRuns,
  parseRetryAfter,
  recordDecision,
  runPath,
  sanitizeFilename,
  toApiError,
} from "./client";

let server: MockServer;

beforeEach(() => {
  server = new MockServer().install();
});

afterEach(() => {
  vi.useRealTimers();
});

async function caught(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error("Expected the request to fail");
}

describe("requests", () => {
  it("uses relative URLs, JSON headers and no caching", async () => {
    server.onJson("GET", "/api/v1/runs/abc", runRecord({ run_id: "abc" }));
    await getRun("abc");
    const [input, init] = server.fetch.mock.calls[0]!;
    expect(input).toBe("/api/v1/runs/abc");
    expect(init?.method).toBe("GET");
    expect(init?.cache).toBe("no-store");
    expect(server.requests[0]!.headers.accept).toBe("application/json");
    expect(server.requests[0]!.headers["content-type"]).toBeUndefined();
  });

  it("encodes run identifiers in paths", () => {
    expect(runPath("a/b?c")).toBe("/api/v1/runs/a%2Fb%3Fc");
  });

  it("posts the run request as JSON exactly as given", async () => {
    server.on("POST", "/api/v1/runs", () => json(202, accepted({ run_id: "r1" })));
    const request = {
      code: "def f(x):\n    return x\n",
      task_type: "guard_clauses" as const,
      workflow_mode: "single_role" as const,
      reference_case_id: null,
    };
    const result = await createRun(request);
    expect(result).toEqual(accepted({ run_id: "r1" }));
    expect(server.requests[0]!.body).toEqual(request);
    expect(server.requests[0]!.headers["content-type"]).toBe("application/json");
  });

  it("reads the health report", async () => {
    server.onJson("GET", "/health", health("fake"));
    expect((await getHealth()).mode).toBe("fake");
  });

  it("asks for a bounded history page", async () => {
    server.onJson("GET", "/api/v1/runs", { runs: [runSummary()], limit: 50 });
    const list = await listRuns(50);
    expect(list.runs).toHaveLength(1);
    expect(server.requests[0]!.query.get("limit")).toBe("50");
  });

  it("accepts the reference cases as a bare list or wrapped in an object", async () => {
    server.onJson("GET", "/api/v1/reference-cases", [SHIPPING_CASE]);
    expect(await listReferenceCases()).toEqual([SHIPPING_CASE]);
    server.onJson("GET", "/api/v1/reference-cases", { cases: [SHIPPING_CASE] });
    expect(await listReferenceCases()).toEqual([SHIPPING_CASE]);
    server.onJson("GET", "/api/v1/reference-cases", { items: "nope" });
    expect((await caught(listReferenceCases())).kind).toBe("invalid_response");
  });

  it("treats 204 from DELETE as success", async () => {
    server.on("DELETE", "/api/v1/runs/r1", () => new Response(null, { status: 204 }));
    await expect(deleteRun("r1")).resolves.toBeUndefined();
    expect(server.requests[0]!.method).toBe("DELETE");
  });

  it("returns the updated record after a decision, or null when the body is not a record", async () => {
    server.onJson("POST", "/api/v1/runs/r1/decision", runRecord({ run_id: "r1", human_decision: "accepted" }));
    expect((await recordDecision("r1", "accepted"))?.human_decision).toBe("accepted");
    expect(server.requests[0]!.body).toEqual({ decision: "accepted" });
    server.on("POST", "/api/v1/runs/r1/decision", () => new Response(null, { status: 204 }));
    expect(await recordDecision("r1", "rejected")).toBeNull();
  });
});

describe("errors", () => {
  it("keeps the code, message and details of an ErrorResponse", async () => {
    server.on("POST", "/api/v1/runs", () =>
      apiError(422, "invalid_syntax", "The code is not valid Python: invalid syntax (line 1, column 26).", [
        { line: 1, column: 26, message: "invalid syntax" },
      ]),
    );
    const error = await caught(createRun({ code: "def f(:" }));
    expect(error).toMatchObject({
      kind: "http",
      status: 422,
      code: "invalid_syntax",
      message: "The code is not valid Python: invalid syntax (line 1, column 26).",
    });
    expect(error.details).toEqual([{ line: 1, column: 26, message: "invalid syntax" }]);
    expect(error.transient).toBe(false);
  });

  it("reads the retry delay of a busy service from the header or the details", async () => {
    server.on("POST", "/api/v1/runs", () =>
      apiError(503, "busy", "The run queue is full (4 unfinished runs). Try again later.", [
        { max_pending: 4, retry_after_s: 10 },
      ], { "Retry-After": "12" }),
    );
    const fromHeader = await caught(createRun({ code: "x" }));
    expect(fromHeader).toMatchObject({ code: "busy", status: 503, retryAfterSeconds: 12 });
    expect(fromHeader.transient).toBe(true);

    server.on("POST", "/api/v1/runs", () =>
      apiError(503, "busy", "The run queue is full.", [{ max_pending: 4, retry_after_s: 10 }]),
    );
    expect((await caught(createRun({ code: "x" }))).retryAfterSeconds).toBe(10);
  });

  it("understands FastAPI's default validation body", async () => {
    server.on("POST", "/api/v1/runs", () =>
      json(422, { detail: [{ loc: ["body", "code"], msg: "String should have at most 20000 characters", type: "string_too_long" }] }),
    );
    const error = await caught(createRun({ code: "x" }));
    expect(error.code).toBe("validation_error");
    expect(error.message).toBe("code: String should have at most 20000 characters");
  });

  it("describes a proxy error without a JSON body", async () => {
    server.on("GET", "/health", () => new Response("Bad Gateway", { status: 502 }));
    const error = await caught(getHealth());
    expect(error).toMatchObject({ kind: "http", status: 502, code: "bad_gateway" });
    expect(error.message).toMatch(/backend is running/);
    expect(error.transient).toBe(true);
  });

  it("reports a network failure as a transient network error", async () => {
    server.fetch.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const error = await caught(getHealth());
    expect(error).toMatchObject({ kind: "network", code: "network_error" });
    expect(error.transient).toBe(true);
  });

  it("times out a request that does not answer", async () => {
    vi.useFakeTimers();
    server.fetch.mockImplementationOnce(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        }),
    );
    const pending = caught(getHealth());
    await vi.advanceTimersByTimeAsync(DEFAULT_TIMEOUT_MS);
    const error = await pending;
    expect(error).toMatchObject({ kind: "timeout", code: "timeout" });
    expect(error.transient).toBe(true);
  });

  it("reports cancellation by the caller as aborted", async () => {
    server.fetch.mockImplementationOnce(
      (_input, init) =>
        new Promise<Response>((_resolve, reject) => {
          init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        }),
    );
    const controller = new AbortController();
    const pending = caught(getRun("r1", controller.signal));
    controller.abort();
    expect((await pending).kind).toBe("aborted");
  });

  it("rejects a success response that is not JSON or not a run", async () => {
    server.on("GET", "/api/v1/runs/r1", () => new Response("<!doctype html><title>index</title>", { status: 200 }));
    expect((await caught(getRun("r1"))).kind).toBe("invalid_response");
    server.onJson("GET", "/api/v1/runs/r1", { run_id: "r1", status: "sleeping" });
    const error = await caught(getRun("r1"));
    expect(error.kind).toBe("invalid_response");
    expect(error.transient).toBe(false);
  });

  it("wraps unknown exceptions", () => {
    expect(toApiError(new Error("odd"))).toMatchObject({ kind: "invalid_response", code: "client_error", message: "odd" });
    const original = new ApiError({ kind: "network", code: "network_error", message: "x" });
    expect(toApiError(original)).toBe(original);
  });
});

describe("proposal download", () => {
  it("returns the file with the name from Content-Disposition", async () => {
    server.on(
      "GET",
      "/api/v1/runs/r1/proposal",
      () =>
        new Response("def f():\n    return 1\n", {
          status: 200,
          headers: {
            "Content-Type": "text/x-python; charset=utf-8",
            "Content-Disposition": 'attachment; filename="proposal-r1.py"',
          },
        }),
    );
    const file = await fetchProposal("r1");
    expect(file.filename).toBe("proposal-r1.py");
    expect(await file.blob.text()).toBe("def f():\n    return 1\n");
  });

  it("falls back to a safe name and reports 409 proposal_unavailable", async () => {
    server.on("GET", "/api/v1/runs/r1/proposal", () => new Response("x = 1\n", { status: 200 }));
    expect((await fetchProposal("r1")).filename).toBe("proposal-r1.py");
    server.on("GET", "/api/v1/runs/r1/proposal", () =>
      apiError(409, "proposal_unavailable", "No proposal is available: The run finished without a proposal."),
    );
    expect((await caught(fetchProposal("r1"))).code).toBe("proposal_unavailable");
  });
});

describe("header helpers", () => {
  it.each([
    ['attachment; filename="proposal-1.py"', "proposal-1.py"],
    ["attachment; filename=plain.py", "plain.py"],
    ["attachment; filename*=UTF-8''caf%C3%A9.py", "café.py"],
    ['attachment; filename="fallback.py"; filename*=UTF-8\'\'better.py', "better.py"],
    ['attachment; filename="..\\\\..\\\\evil.py"', "evil.py"],
    ['attachment; filename="../../etc/passwd"', "passwd"],
    ["attachment", null],
    [null, null],
  ])("reads %j as %j", (header, expected) => {
    expect(filenameFromContentDisposition(header)).toBe(expected);
  });

  it("refuses empty or dot-only names", () => {
    expect(sanitizeFilename("..")).toBeNull();
    expect(sanitizeFilename("  ")).toBeNull();
    expect(sanitizeFilename('a<b>:c"|?*.py')).toBe("abc.py");
  });

  it("parses Retry-After seconds and dates", () => {
    expect(parseRetryAfter(null)).toBeNull();
    expect(parseRetryAfter("10")).toBe(10);
    expect(parseRetryAfter("soon")).toBeNull();
    const now = Date.parse("2026-10-20T09:00:00Z");
    expect(parseRetryAfter("Tue, 20 Oct 2026 09:00:30 GMT", now)).toBe(30);
  });
});
