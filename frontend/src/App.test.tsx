import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { RunRecord, RunSummary } from "./api/contracts";
import {
  DISCOUNT_CASE,
  ORIGINAL_CODE,
  PROPOSED_CODE,
  RUN_ID,
  SHIPPING_CASE,
  accepted,
  failedRecord,
  health,
  pendingRecord,
  runRecord,
  runSummary,
  verification,
} from "./test/fixtures";
import { MockServer, apiError, json } from "./test/mockServer";

// --- Helpers ----------------------------------------------------------------------------

function setupServer(options: { mode?: "fake" | "local_model"; runs?: () => RunSummary[] } = {}): MockServer {
  const server = new MockServer().install();
  server.onJson("GET", "/health", health(options.mode ?? "local_model"));
  server.onJson("GET", "/api/v1/reference-cases", [SHIPPING_CASE, DISCOUNT_CASE]);
  server.onJson("GET", "/api/v1/runs", () => ({ runs: options.runs ? options.runs() : [], limit: 20 }));
  return server;
}

/** Answers GET /api/v1/runs/{id} with the records in order, repeating the last one. */
function serveRun(server: MockServer, records: RunRecord[], runId = RUN_ID): void {
  const queue = [...records];
  server.on("GET", `/api/v1/runs/${runId}`, () => json(200, queue.length > 1 ? queue.shift() : queue[0]));
}

function useAppFakeTimers() {
  // Promise and stream internals keep their real scheduling; only timers and Date are faked.
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"] });
  vi.setSystemTime(new Date("2026-10-20T09:02:00Z"));
}

async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function flush() {
  for (let i = 0; i < 3; i += 1) await advance(0);
}

const editor = () => screen.getByLabelText("Python function") as HTMLTextAreaElement;
const submitButton = () => screen.getByRole("button", { name: "Improve code" });
const step = (key: string) => document.querySelector(`[data-step="${key}"]`);

function typeCode(code: string) {
  fireEvent.change(editor(), { target: { value: code } });
}

async function renderReady() {
  render(<App />);
  await screen.findByText("0 of 4 waiting");
  await screen.findByRole("option", { name: /Shipping cost with nested validation/ });
}

beforeEach(() => {
  Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:proposal"), configurable: true, writable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), configurable: true, writable: true });
});

afterEach(() => {
  vi.useRealTimers();
});

// --- Header ------------------------------------------------------------------------------

describe("service status header", () => {
  it("shows the provider, the exact model identity, the runner and the queue", async () => {
    setupServer();
    await renderReady();
    const status = screen.getByRole("region", { name: "Service status" });
    expect(within(status).getByText("AI model")).toBeInTheDocument();
    expect(within(status).getByText(/example-org\/example-code-model/)).toBeInTheDocument();
    expect(within(status).getByText(/at revision 0123456789ab…/)).toBeInTheDocument();
    expect(within(status).getByText("Device cuda:0")).toBeInTheDocument();
    expect(within(status).getByText("Fine-tuned LoRA adapter")).toBeInTheDocument();
    expect(
      within(status).getByText("guard-clauses-lora (sha256 ffffffffffff…). Analysis and review use the base model."),
    ).toBeInTheDocument();
    expect(within(status).getByText("Ready")).toBeInTheDocument();
    expect(within(status).queryByRole("status")).toBeNull();
    expect(within(status).getByText("Runner enabled")).toBeInTheDocument();
    expect(within(status).getByText("API 0.1.0")).toBeInTheDocument();
    expect(screen.queryByRole("note", { name: "Fake provider warning" })).toBeNull();
  });

  it("shows a persistent warning when the fake provider is active", async () => {
    setupServer({ mode: "fake" });
    await renderReady();
    const banner = screen.getByRole("note", { name: "Fake provider warning" });
    expect(banner).toHaveTextContent("Demo mode: results come from a test stub, not the AI model.");
    const status = screen.getByRole("region", { name: "Service status" });
    expect(within(status).getByText("Demo mode (no AI model)")).toBeInTheDocument();
    expect(within(status).getByText("Device none")).toBeInTheDocument();
    expect(within(status).getByText("Fixed rules (fake provider)")).toBeInTheDocument();
    expect(within(status).getByText("Runner disabled")).toBeInTheDocument();
    expect(within(status).getByText(/REFACTOR_AI_RUNNER=disabled/)).toBeInTheDocument();
  });

  it("says when the refactoring role uses the base model", async () => {
    const server = setupServer();
    server.onJson("GET", "/health", health("local_model", { refactor_use_adapter: false }));
    await renderReady();
    const status = screen.getByRole("region", { name: "Service status" });
    expect(within(status).getByText("Base model")).toBeInTheDocument();
    expect(within(status).getByText("Adapter guard-clauses-lora is configured but not used.")).toBeInTheDocument();
  });

  it("shows why the model is not ready while it loads", async () => {
    const server = setupServer();
    const loading = health();
    loading.provider = {
      ...loading.provider,
      ready: false,
      detail: "The model is loading in the background since startup; runs wait until it is ready.",
    };
    server.onJson("GET", "/health", loading);
    await renderReady();
    const status = screen.getByRole("region", { name: "Service status" });
    expect(within(status).getAllByText("Loading")[0]).toHaveAttribute("data-tone", "progress");
    expect(within(status).getByRole("status")).toHaveTextContent(
      "The model is loading. The model is loading in the background since startup; runs wait until it is ready.",
    );
  });

  it("warns that runs fail when the requested adapter is missing", async () => {
    const server = setupServer();
    const missing = health();
    missing.provider = {
      ...missing.provider,
      adapter_id: null,
      adapter_sha256: null,
      ready: false,
      detail:
        "REFACTOR_AI_REFACTOR_USE_ADAPTER=true, but the model provider has no LoRA adapter configured. Runs fail instead of using the base model.",
    };
    server.onJson("GET", "/health", missing);
    await renderReady();
    const status = screen.getByRole("region", { name: "Service status" });
    expect(within(status).getByText("Adapter requested, none configured")).toHaveAttribute("data-tone", "fail");
    expect(within(status).getAllByText("Adapter missing")[0]).toBeInTheDocument();
    expect(within(status).getByRole("status")).toHaveTextContent(
      "The fine-tuned adapter is missing. REFACTOR_AI_REFACTOR_USE_ADAPTER=true, but the model provider has no LoRA adapter configured.",
    );
  });

  it("reports an unreachable service and checks again on request", async () => {
    const server = setupServer();
    server.on("GET", "/health", () => {
      throw new TypeError("Failed to fetch");
    });
    render(<App />);
    expect(await screen.findByText("Service unreachable.")).toBeInTheDocument();
    server.onJson("GET", "/health", health());
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(await screen.findByText("0 of 4 waiting")).toBeInTheDocument();
    expect(screen.queryByText("Service unreachable.")).toBeNull();
  });
});

// --- Input ------------------------------------------------------------------------------

describe("input", () => {
  it("enables Propose refactoring only for non-blank code within the API limit", async () => {
    setupServer();
    await renderReady();
    expect(submitButton()).toBeDisabled();
    typeCode("   \n\t");
    expect(submitButton()).toBeDisabled();
    typeCode("def f(x):\n    return x\n");
    expect(submitButton()).toBeEnabled();
    expect(screen.getByText("23 of 20,000 characters")).toBeInTheDocument();
    expect(screen.getByText("2 lines")).toBeInTheDocument();
    typeCode("x".repeat(20_001));
    expect(submitButton()).toBeDisabled();
    expect(screen.getByText(/longer than the service accepts/)).toBeInTheDocument();
  });

  it("warns above the task limit but still allows submission", async () => {
    setupServer();
    await renderReady();
    typeCode(`def f(x):\n${"    x = 1\n".repeat(61)}`);
    expect(screen.getByText(/Longer input is accepted, but the run will end with no change/)).toBeInTheDocument();
    expect(submitButton()).toBeEnabled();
  });

  it("offers only the guard-clause task and defaults to the multi-role workflow", async () => {
    setupServer();
    await renderReady();
    const task = screen.getByLabelText("Refactoring task");
    expect(within(task).getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Flatten nested if statements (guard clauses)",
    ]);
    expect(screen.getByRole("radio", { name: /With review/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Fast/ })).not.toBeChecked();
  });
});

// --- Submission and progress -----------------------------------------------------------------

describe("running a refactoring", () => {
  it("submits, shows each stage and then the full result", async () => {
    useAppFakeTimers();
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () => json(202, accepted()));
    serveRun(server, [
      pendingRecord("analyzing"),
      pendingRecord("generating"),
      pendingRecord("verifying"),
      runRecord(),
    ]);
    render(<App />);
    await flush();

    typeCode(ORIGINAL_CODE);
    fireEvent.click(submitButton());
    await flush();

    expect(server.calls("POST", "/api/v1/runs")[0]!.body).toEqual({
      code: ORIGINAL_CODE,
      task_type: "guard_clauses",
      workflow_mode: "multi_role",
      reference_case_id: null,
    });
    expect(submitButton()).toBeDisabled();
    expect(screen.getByText(/Wait for the current run to finish/)).toBeInTheDocument();
    expect(step("queued")).toHaveAttribute("data-state", "current");
    expect(screen.getByText("Run status: Queued.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Result" })).toHaveFocus();

    await advance(750);
    expect(step("queued")).toHaveAttribute("data-state", "done");
    expect(step("analyzing")).toHaveAttribute("data-state", "current");
    expect(screen.getByText("Run status: Analyzing.")).toBeInTheDocument();
    expect(screen.getByText(/Elapsed 0 s|Elapsed 1 s/)).toBeInTheDocument();

    await advance(750);
    expect(step("generating")).toHaveAttribute("data-state", "current");
    await advance(750);
    expect(step("verifying")).toHaveAttribute("data-state", "current");
    expect(screen.getByText("Elapsed 2 s")).toBeInTheDocument();
    await advance(750);

    expect(screen.getByText("Run completed: Ready.")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Outcome: Ready" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: /Unified diff/ })).toBeInTheDocument();
    for (const name of ["Syntax", "Task rubric", "Reference tests", "Model review"]) {
      expect(screen.getByRole("article", { name })).toBeInTheDocument();
    }
    expect(screen.getByText("Inverted the weight check into a guard clause and removed the else branches.")).toBeInTheDocument();
    expect(screen.getByText("Lines 3–9")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download proposal" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept proposal" })).toBeInTheDocument();
    const record = screen.getByRole("heading", { name: "Run record" }).closest("section")!;
    const meta = (label: string) => within(record).getByText(label, { selector: "dt" }).nextElementSibling;
    expect(meta("Run ID")).toHaveTextContent(RUN_ID);
    expect(meta("Model calls")).toHaveTextContent("3 of at most 5");
    expect(meta("Stop reason")).toHaveTextContent("No correction needed (no_correction_needed)");
    expect(meta("Refactoring weights")).toHaveTextContent("Base model");
    const limits = within(record).getByRole("table", { name: "Generation limits per role" });
    expect(within(limits).getAllByRole("row").map((row) => row.textContent)).toEqual([
      "RoleMax new tokensMax input tokensTime limitTemperature",
      "Analysis38420481 min 00 s0",
      "Refactoring102420482 min 00 s0",
      "Review76840961 min 30 s0",
    ]);
    expect(meta("Created")).toHaveTextContent("20 Oct 2026, 09:02:00");
    expect(meta("Duration")).toHaveTextContent("1.0 s (400 ms queued, 600 ms processing)");
    expect(meta("Model")).toHaveTextContent("Adapter guard-clauses-lora");
    expect(within(record).getByRole("table", { name: "Stage timings" })).toBeInTheDocument();
    expect(within(record).getByRole("table", { name: "Generation attempts" })).toBeInTheDocument();

    // Finished: the poller stopped, the button is back and the input was never touched.
    const polls = server.calls("GET", `/api/v1/runs/${RUN_ID}`).length;
    await advance(30_000);
    expect(server.calls("GET", `/api/v1/runs/${RUN_ID}`)).toHaveLength(polls);
    expect(submitButton()).toBeEnabled();
    expect(editor().value).toBe(ORIGINAL_CODE);
    expect(server.calls("GET", "/api/v1/runs").length).toBeGreaterThanOrEqual(3);
  });

  it("sends single-role runs and shows no analysis step", async () => {
    useAppFakeTimers();
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () => json(202, accepted()));
    serveRun(server, [pendingRecord("generating", { workflow_mode: "single_role" })]);
    render(<App />);
    await flush();
    fireEvent.click(screen.getByRole("radio", { name: /Fast/ }));
    typeCode(ORIGINAL_CODE);
    fireEvent.click(submitButton());
    await flush();
    expect(server.calls("POST", "/api/v1/runs")[0]!.body).toMatchObject({ workflow_mode: "single_role" });
    await advance(750);
    expect(step("analyzing")).toBeNull();
    expect(step("generating")).toHaveAttribute("data-state", "current");
  });

  it("keeps the last state while the connection drops and recovers on its own", async () => {
    useAppFakeTimers();
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () => json(202, accepted()));
    let failures = 2;
    server.on("GET", `/api/v1/runs/${RUN_ID}`, () => {
      if (failures > 0) {
        failures -= 1;
        throw new TypeError("Failed to fetch");
      }
      return json(200, runRecord());
    });
    render(<App />);
    await flush();
    typeCode(ORIGINAL_CODE);
    fireEvent.click(submitButton());
    await flush();
    await advance(750);
    expect(screen.getByText(/Connection problem/)).toHaveTextContent("attempt 1");
    expect(editor().value).toBe(ORIGINAL_CODE);
    await advance(1125);
    expect(screen.getByText(/Connection problem/)).toHaveTextContent("attempt 2");
    await advance(1688);
    expect(screen.queryByText(/Connection problem/)).toBeNull();
    expect(screen.getByRole("region", { name: "Outcome: Ready" })).toBeInTheDocument();
  });

  it("stops checking after the maximum wait and resumes on request", async () => {
    useAppFakeTimers();
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () => json(202, accepted()));
    serveRun(server, [pendingRecord("generating")]);
    render(<App />);
    await flush();
    typeCode(ORIGINAL_CODE);
    fireEvent.click(submitButton());
    await flush();
    await advance(750);
    // Jump past the 20-minute limit in one step; the pending poll then sees the deadline.
    await act(async () => {
      vi.advanceTimersByTime(20 * 60_000);
    });
    await flush();
    expect(screen.getByText(/Stopped checking after 20 min 00 s/)).toBeInTheDocument();
    expect(submitButton()).toBeEnabled();
    const polls = server.calls("GET", `/api/v1/runs/${RUN_ID}`).length;
    serveRun(server, [runRecord()]);
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await advance(750);
    expect(server.calls("GET", `/api/v1/runs/${RUN_ID}`).length).toBe(polls + 1);
    expect(screen.getByRole("region", { name: "Outcome: Ready" })).toBeInTheDocument();
  });

  it("stops polling when the page is closed", async () => {
    useAppFakeTimers();
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () => json(202, accepted()));
    serveRun(server, [pendingRecord("generating")]);
    const { unmount } = render(<App />);
    await flush();
    typeCode(ORIGINAL_CODE);
    fireEvent.click(submitButton());
    await flush();
    await advance(750);
    expect(server.calls("GET", `/api/v1/runs/${RUN_ID}`)).toHaveLength(1);
    unmount();
    await advance(60_000);
    expect(server.calls("GET", `/api/v1/runs/${RUN_ID}`)).toHaveLength(1);
  });

  it("reports a run that disappeared while it was followed", async () => {
    useAppFakeTimers();
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () => json(202, accepted()));
    server.on("GET", `/api/v1/runs/${RUN_ID}`, () => apiError(404, "run_not_found", "Run not found."));
    render(<App />);
    await flush();
    typeCode(ORIGINAL_CODE);
    fireEvent.click(submitButton());
    await flush();
    await advance(750);
    expect(screen.getByText(/This run no longer exists on the server/)).toBeInTheDocument();
    await advance(30_000);
    expect(server.calls("GET", `/api/v1/runs/${RUN_ID}`)).toHaveLength(1);
    expect(editor().value).toBe(ORIGINAL_CODE);
  });
});

// --- Submission errors ------------------------------------------------------------------------

describe("submission errors keep the input", () => {
  it("shows invalid_syntax with its line and marks that line", async () => {
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () =>
      apiError(422, "invalid_syntax", "The code is not valid Python: invalid syntax (line 2, column 9).", [
        { line: 2, column: 9, message: "invalid syntax" },
      ]),
    );
    await renderReady();
    const code = "def f(x):\n    if x\n        return 1\n";
    typeCode(code);
    fireEvent.click(submitButton());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The code is not valid Python");
    expect(alert).toHaveTextContent("invalid syntax (line 2, column 9).");
    expect(alert).toHaveTextContent("Line 2, column 9.");
    expect(alert).toHaveTextContent("Your code was not changed.");
    expect(editor().value).toBe(code);
    expect(editor()).toHaveAttribute("aria-invalid", "true");
    const gutter = screen.getByTestId("editor-gutter");
    expect(gutter.children[1]).toHaveAttribute("data-error", "true");

    fireEvent.click(within(alert).getByRole("button", { name: "Go to line 2" }));
    expect(editor()).toHaveFocus();
    expect(editor().selectionStart).toBe(10);
    expect(editor().selectionEnd).toBe(18);

    typeCode(`${code}# edited\n`);
    expect(gutter.children[1]).not.toHaveAttribute("data-error");
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("shows validation errors from the service", async () => {
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () =>
      apiError(422, "validation_error", "Invalid request (code): code must not be blank", [
        { loc: ["body", "code"], message: "Value error, code must not be blank", type: "value_error" },
      ]),
    );
    await renderReady();
    typeCode("def f(): pass\n");
    fireEvent.click(submitButton());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The request was not accepted");
    expect(alert).toHaveTextContent("Invalid request (code): code must not be blank");
    expect(editor().value).toBe("def f(): pass\n");
  });

  it("explains a busy service with the retry delay and submits again on request", async () => {
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () =>
      apiError(503, "busy", "The run queue is full (4 unfinished runs). Try again later.", [
        { max_pending: 4, retry_after_s: 10 },
      ], { "Retry-After": "10" }),
    );
    await renderReady();
    typeCode(ORIGINAL_CODE);
    fireEvent.click(submitButton());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The service is busy");
    expect(alert).toHaveTextContent("Wait about 10 s for queued runs to finish, then submit again.");
    expect(alert).toHaveAttribute("data-tone", "warn");
    expect(editor().value).toBe(ORIGINAL_CODE);
    server.on("POST", "/api/v1/runs", () => json(202, accepted()));
    serveRun(server, [pendingRecord("queued")]);
    fireEvent.click(within(alert).getByRole("button", { name: "Submit again" }));
    await waitFor(() => expect(server.calls("POST", "/api/v1/runs")).toHaveLength(2));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  });

  it("explains that the service cannot be reached", async () => {
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () => {
      throw new TypeError("Failed to fetch");
    });
    await renderReady();
    typeCode(ORIGINAL_CODE);
    fireEvent.click(submitButton());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Cannot reach the service");
    expect(alert).toHaveTextContent("127.0.0.1:8000");
    expect(editor().value).toBe(ORIGINAL_CODE);
  });
});

// --- Demonstration cases ------------------------------------------------------------------

describe("demonstration cases", () => {
  async function loadCase(caseId = "shipping_cost") {
    fireEvent.change(screen.getByLabelText("Demonstration case"), { target: { value: caseId } });
    fireEvent.click(screen.getByRole("button", { name: "Load case" }));
  }

  it("fills the editor and links the case so its tests run", async () => {
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () => json(202, accepted()));
    serveRun(server, [pendingRecord("queued")]);
    await renderReady();
    expect(screen.getByRole("option", { name: "Shipping cost with nested validation (4 reference tests)" })).toBeInTheDocument();
    await loadCase();
    expect(editor().value).toBe(SHIPPING_CASE.code);
    expect(screen.getByText(/tests? will run\./)).toHaveTextContent(
      "Demo case Shipping cost with nested validation: 4 tests will run.",
    );
    fireEvent.click(submitButton());
    await waitFor(() => expect(server.calls("POST", "/api/v1/runs")).toHaveLength(1));
    expect(server.calls("POST", "/api/v1/runs")[0]!.body).toMatchObject({ reference_case_id: "shipping_cost" });
  });

  it("removes the link with a notice when the code is edited", async () => {
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () => json(202, accepted()));
    serveRun(server, [pendingRecord("queued")]);
    await renderReady();
    await loadCase();
    typeCode(SHIPPING_CASE.code.replace("weight * 3", "weight * 4"));
    expect(screen.queryByText(/tests? will run\./)).toBeNull();
    expect(screen.getByText(/You changed the demo code/)).toHaveTextContent(
      "You changed the demo code, so the tests of Shipping cost with nested validation will not run.",
    );
    fireEvent.click(submitButton());
    await waitFor(() => expect(server.calls("POST", "/api/v1/runs")).toHaveLength(1));
    expect(server.calls("POST", "/api/v1/runs")[0]!.body).toMatchObject({ reference_case_id: null });
  });

  it("can restore the case code after an edit", async () => {
    setupServer();
    await renderReady();
    await loadCase();
    typeCode("def changed():\n    return 0\n");
    fireEvent.click(screen.getByRole("button", { name: "Restore the case code" }));
    expect(editor().value).toBe(SHIPPING_CASE.code);
    expect(screen.getByText(/tests? will run\./)).toBeInTheDocument();
  });

  it("offers the previous code back after loading a case over it", async () => {
    setupServer();
    await renderReady();
    typeCode("def mine(x):\n    return x\n");
    await loadCase("member_discount");
    expect(editor().value).toBe(DISCOUNT_CASE.code);
    fireEvent.click(screen.getByRole("button", { name: "Restore previous code" }));
    expect(editor().value).toBe("def mine(x):\n    return x\n");
    expect(screen.queryByText(/tests? will run\./)).toBeNull();
  });

  it("lets the person remove the link after reference_case_mismatch", async () => {
    const server = setupServer();
    server.on("POST", "/api/v1/runs", () =>
      apiError(422, "reference_case_mismatch", "The submitted code differs from reference case 'shipping_cost'.", [
        { reference_case_id: "shipping_cost" },
      ]),
    );
    await renderReady();
    await loadCase();
    fireEvent.click(submitButton());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The code does not match the demonstration case");
    expect(editor().value).toBe(SHIPPING_CASE.code);
    fireEvent.click(within(alert).getByRole("button", { name: "Remove the case link" }));
    expect(screen.queryByText(/tests? will run\./)).toBeNull();
  });

  it("reports when the cases cannot be loaded", async () => {
    const server = setupServer();
    server.on("GET", "/api/v1/reference-cases", () =>
      apiError(500, "reference_cases_unavailable", "The demonstration reference cases could not be loaded. See the server log."),
    );
    render(<App />);
    expect(await screen.findByText(/Could not load the demonstration cases/)).toBeInTheDocument();
    expect(screen.getByLabelText("Demonstration case")).toBeDisabled();
    server.onJson("GET", "/api/v1/reference-cases", [SHIPPING_CASE]);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("option", { name: /Shipping cost/ })).toBeInTheDocument();
  });
});

// --- History, failures and decisions ----------------------------------------------------

describe("history", () => {
  const FAILED_ID = "0a1b2c3d4e5f46a7b8c9d0e1f2a3b4c5";

  function historyRuns(): RunSummary[] {
    return [
      runSummary({ run_id: FAILED_ID, status: "failed", disposition: "failed", created_at: "2026-10-20T09:09:00Z" }),
      runSummary({ provider_mode: "fake", human_decision: "accepted" }),
    ];
  }

  it("lists runs newest first with status and disposition chips", async () => {
    setupServer({ runs: historyRuns });
    await renderReady();
    await screen.findByText("Showing the 2 most recent runs.");
    const items = screen.getAllByRole("listitem").filter((item) => item.classList.contains("history-item"));
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("20 Oct 2026, 09:09:00");
    expect(within(items[0]!).getByText("Failed")).toBeInTheDocument();
    expect(within(items[1]!).getByText("Ready")).toBeInTheDocument();
    expect(within(items[1]!).getByText("Fake")).toBeInTheDocument();
    expect(within(items[1]!).getByText("Accepted by you")).toBeInTheDocument();
  });

  it("reopens a failed run with its error and retries the same input", async () => {
    const server = setupServer({ runs: historyRuns });
    serveRun(server, [failedRecord({ run_id: FAILED_ID })], FAILED_ID);
    server.on("POST", "/api/v1/runs", () => json(202, accepted({ run_id: "f".repeat(32) })));
    serveRun(server, [pendingRecord("queued", { run_id: "f".repeat(32) })], "f".repeat(32));
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Open the run from 20 Oct 2026, 09:09:00" }));
    const failure = await screen.findByRole("heading", { name: "Something went wrong" });
    const section = failure.closest("section")!;
    expect(section).toHaveTextContent("Runs are never restarted automatically.");
    expect(section).toHaveTextContent("Stopped while rewriting.");
    expect(screen.getByRole("region", { name: "Your code" })).toHaveTextContent("def shipping_cost(weight, express):");
    expect(step("generating")).toHaveAttribute("data-state", "failed");
    expect(screen.queryByRole("button", { name: "Download proposal" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Accept proposal" })).toBeNull();

    fireEvent.click(within(section).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(server.calls("POST", "/api/v1/runs")).toHaveLength(1));
    expect(server.calls("POST", "/api/v1/runs")[0]!.body).toEqual({
      code: ORIGINAL_CODE,
      task_type: "guard_clauses",
      workflow_mode: "multi_role",
      reference_case_id: "shipping_cost",
    });
    expect(editor().value).toBe("");
  });

  it("loads a run's input into the editor on request", async () => {
    const server = setupServer({ runs: historyRuns });
    serveRun(server, [failedRecord({ run_id: FAILED_ID })], FAILED_ID);
    await renderReady();
    typeCode("def other():\n    return 2\n");
    fireEvent.click(screen.getByRole("button", { name: "Open the run from 20 Oct 2026, 09:09:00" }));
    await screen.findByRole("heading", { name: "Something went wrong" });
    fireEvent.click(screen.getAllByRole("button", { name: "Edit this input" })[0]!);
    expect(editor().value).toBe(ORIGINAL_CODE);
    expect(editor()).toHaveFocus();
    expect(screen.getByText(/tests? will run\./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Restore previous code" }));
    expect(editor().value).toBe("def other():\n    return 2\n");
  });

  it("deletes a run only after confirmation", async () => {
    let runs = historyRuns();
    const server = setupServer({ runs: () => runs });
    server.on("DELETE", `/api/v1/runs/${FAILED_ID}`, () => {
      runs = runs.filter((run) => run.run_id !== FAILED_ID);
      return new Response(null, { status: 204 });
    });
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Delete the run from 20 Oct 2026, 09:09:00" }));
    const confirm = screen.getByRole("group", { name: "Confirm deleting the run from 20 Oct 2026, 09:09:00" });
    fireEvent.click(within(confirm).getByRole("button", { name: "Keep run" }));
    expect(server.calls("DELETE", `/api/v1/runs/${FAILED_ID}`)).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Delete the run from 20 Oct 2026, 09:09:00" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete run" }));
    await waitFor(() => expect(server.calls("DELETE", `/api/v1/runs/${FAILED_ID}`)).toHaveLength(1));
    await waitFor(() => expect(screen.queryByText("20 Oct 2026, 09:09:00")).toBeNull());
    expect(screen.getByText("Showing the only stored run.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "History" })).toHaveFocus();
  });

  it("keeps the run and explains when deletion fails", async () => {
    const server = setupServer({ runs: historyRuns });
    server.on("DELETE", `/api/v1/runs/${FAILED_ID}`, () => apiError(500, "internal_error", "Internal server error."));
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: "Delete the run from 20 Oct 2026, 09:09:00" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete run" }));
    expect(await screen.findByText("The run was not deleted: Internal server error.")).toBeInTheDocument();
    expect(screen.getByText("20 Oct 2026, 09:09:00")).toBeInTheDocument();
  });

  it("can show up to 50 runs", async () => {
    const many = Array.from({ length: 20 }, (_, index) =>
      runSummary({ run_id: index.toString(16).padStart(32, "0"), created_at: `2026-10-20T08:${String(index).padStart(2, "0")}:00Z` }),
    );
    const server = setupServer({ runs: () => many });
    await renderReady();
    fireEvent.click(await screen.findByRole("button", { name: "Show up to 50" }));
    await waitFor(() =>
      expect(server.calls("GET", "/api/v1/runs").some((request) => request.query.get("limit") === "50")).toBe(true),
    );
  });
});

describe("proposal controls", () => {
  async function openRecord(record: RunRecord) {
    const server = setupServer({ runs: () => [runSummary({ run_id: record.run_id })] });
    serveRun(server, [record], record.run_id);
    await renderReady();
    fireEvent.click(screen.getByRole("button", { name: /^Open the run from/ }));
    await screen.findByRole("heading", { name: "Run record" });
    return server;
  }

  it("hides copy, download and the decision when there is no proposal", async () => {
    await openRecord(
      runRecord({
        proposed_code: null,
        diff: null,
        verification: verification({ disposition: "no_change", disposition_reasons: ["no_opportunity: No nested conditional can be flattened with guard clauses."] }),
      }),
    );
    expect(screen.getByRole("region", { name: "Outcome: No change" })).toBeInTheDocument();
    expect(screen.getByText("Your code stays as it is.")).toBeInTheDocument();
    for (const name of ["Copy proposed code", "Download proposal", "Accept proposal", "Reject proposal"]) {
      expect(screen.queryByRole("button", { name })).toBeNull();
    }
  });

  it("shows them for a proposal that verification did not approve, with a warning", async () => {
    await openRecord(
      runRecord({
        verification: verification({
          disposition: "uncertain",
          reference_tests: { ...verification().reference_tests, status: "not_available", total: null, passed: null, failed: null, errored: null },
        }),
      }),
    );
    expect(screen.getByRole("button", { name: "Download proposal" })).toBeInTheDocument();
    expect(screen.getByText(/The checks say: Not sure/)).toBeInTheDocument();
  });

  it("downloads the proposal through the service", async () => {
    const server = await openRecord(runRecord());
    server.on(
      "GET",
      `/api/v1/runs/${RUN_ID}/proposal`,
      () =>
        new Response(PROPOSED_CODE, {
          status: 200,
          headers: { "Content-Disposition": `attachment; filename="proposal-${RUN_ID}.py"` },
        }),
    );
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    fireEvent.click(screen.getByRole("button", { name: "Download proposal" }));
    expect(await screen.findByText(`Download started: proposal-${RUN_ID}.py.`)).toBeInTheDocument();
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    const blob = vi.mocked(URL.createObjectURL).mock.calls[0]![0] as Blob;
    expect(await blob.text()).toBe(PROPOSED_CODE);
    const anchor = click.mock.contexts[0] as HTMLAnchorElement;
    expect(anchor.download).toBe(`proposal-${RUN_ID}.py`);
    expect(anchor.isConnected).toBe(false);
  });

  it("explains a failed download", async () => {
    const server = await openRecord(runRecord());
    server.on("GET", `/api/v1/runs/${RUN_ID}/proposal`, () =>
      apiError(409, "proposal_unavailable", "No proposal is available: The run finished without a proposal."),
    );
    fireEvent.click(screen.getByRole("button", { name: "Download proposal" }));
    expect(await screen.findByText(/Download failed: No proposal is available/)).toBeInTheDocument();
  });

  it("copies the proposed code to the clipboard", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    try {
      await openRecord(runRecord());
      fireEvent.click(screen.getByRole("button", { name: "Copy proposed code" }));
      expect(await screen.findByText("Proposed code copied to the clipboard.")).toBeInTheDocument();
      expect(writeText).toHaveBeenCalledWith(PROPOSED_CODE);
    } finally {
      delete (navigator as unknown as { clipboard?: unknown }).clipboard;
    }
  });

  it("records accept and reject without touching the input", async () => {
    const server = await openRecord(runRecord());
    typeCode("def untouched():\n    return 0\n");
    server.on("POST", `/api/v1/runs/${RUN_ID}/decision`, (request) =>
      json(200, runRecord({ human_decision: (request.body as { decision: "accepted" | "rejected" }).decision })),
    );
    fireEvent.click(screen.getByRole("button", { name: "Accept proposal" }));
    expect(await screen.findByText("Decision recorded: accepted.")).toBeInTheDocument();
    expect(server.calls("POST", `/api/v1/runs/${RUN_ID}/decision`)[0]!.body).toEqual({ decision: "accepted" });
    expect(screen.getByRole("button", { name: "Accept proposal" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "Reject proposal" }));
    expect(await screen.findByText("Decision recorded: rejected.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject proposal" })).toHaveAttribute("aria-pressed", "true");
    expect(editor().value).toBe("def untouched():\n    return 0\n");
  });

  it("shows a decision error and keeps the previous state", async () => {
    const server = await openRecord(runRecord());
    server.on("POST", `/api/v1/runs/${RUN_ID}/decision`, () =>
      apiError(409, "proposal_unavailable", "No proposal is available: The run has not finished yet."),
    );
    fireEvent.click(screen.getByRole("button", { name: "Accept proposal" }));
    expect(await screen.findByText(/The decision was not recorded: No proposal is available/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Accept proposal" })).toHaveAttribute("aria-pressed", "false");
  });

  it("labels a fake-provider run inside the result even when the service now runs a model", async () => {
    await openRecord(runRecord({ provider_mode: "fake", model: null }));
    expect(screen.getByText("Demo mode: this result is not from the AI model.")).toBeInTheDocument();
    expect(screen.getByText("Demo")).toBeInTheDocument();
  });
});
