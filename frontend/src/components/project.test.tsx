import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import type { Finding, Fix, ProjectRecord } from "../api/projects";
import { DIFF_TEXT, ORIGINAL_CODE, PROPOSED_CODE, health } from "../test/fixtures";
import { MockServer, apiError, json } from "../test/mockServer";
import { checkMeta, sourceLabel } from "./ProjectView";

const PROJECT_ID = "c".repeat(32);

function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    id: "F001",
    category: "bug",
    severity: "high",
    source: "static:ruff:B006",
    file: "app/calc.py",
    line_start: 1,
    line_end: 1,
    symbol: "average",
    title: "Do not use mutable data structures for argument defaults",
    explanation: "Do not use mutable data structures for argument defaults",
    evidence: "ruff B006",
    recommendation: "Use None as the default.",
    confidence: null,
    fixable: true,
    also_reported_by: [],
    ...overrides,
  };
}

function fix(overrides: Partial<Fix> = {}): Fix {
  return {
    id: "X001",
    finding_ids: ["F001"],
    file: "app/calc.py",
    symbol: "average",
    line_start: 1,
    line_end: 5,
    original: ORIGINAL_CODE,
    proposed: PROPOSED_CODE,
    imports: [],
    explanation: "Default None.",
    diff: DIFF_TEXT,
    produced_by: "agent:fixer",
    syntax: { status: "pass", detail: "The patched file parses." },
    static_recheck: { status: "pass", detail: "B006: gone." },
    tests: { status: "pass", detail: "2 passed, none broken." },
    review: { status: "accept", detail: null },
    review_reasons: [],
    disposition: "proposal_ready",
    disposition_reasons: ["ready: everything passed"],
    decision: null,
    ...overrides,
  };
}

function project(overrides: Partial<ProjectRecord> = {}): ProjectRecord {
  return {
    schema_version: 1,
    project_id: PROJECT_ID,
    name: "calc",
    created_at: "2026-10-21T10:00:00Z",
    started_at: "2026-10-21T10:00:01Z",
    finished_at: "2026-10-21T10:01:31Z",
    status: "completed",
    progress: null,
    run_tests: true,
    summary: {
      python_files: 3,
      code_lines: 40,
      findings: 3,
      by_severity: { high: 1, medium: 1, low: 1 },
      fix_dispositions: { proposal_ready: 1, uncertain: 1 },
    },
    architecture: {
      cycles: [["app", "app.calc"]],
      most_imported: [["app", 1]],
      most_dependent: [["app.calc", 1]],
      agent_summary: "Small and simple.",
    },
    findings: [
      finding(),
      finding({
        id: "F002",
        category: "architecture",
        severity: "medium",
        source: "static:index:import-cycle",
        line_start: null,
        line_end: null,
        symbol: "app",
        title: "Import cycle between modules",
        explanation: "app -> app.calc -> app",
        fixable: false,
      }),
      finding({
        id: "F003",
        category: "security",
        severity: "low",
        source: "agent:quality_security",
        line_start: 9,
        title: "Shell command built from input",
        explanation: "The command can be injected.",
        also_reported_by: ["agent:finding_checker"],
      }),
    ],
    fixes: [
      fix(),
      fix({
        id: "X002",
        finding_ids: ["F003"],
        symbol: "run",
        tests: { status: "not_available", detail: "No test refers to run()." },
        review: { status: "uncertain", detail: null },
        disposition: "uncertain",
        disposition_reasons: ["tests_not_available: No test refers to run()."],
      }),
    ],
    baseline_tests: { status: "ran", passed: 2 },
    model: null,
    calls: [],
    stage_times: [],
    warnings: ["The model-call budget was reached."],
    skipped_files: [],
    error: null,
    ...overrides,
  };
}

function setup(info: Record<string, unknown> = {}): MockServer {
  const server = new MockServer().install();
  server.onJson("GET", "/health", health("local_model"));
  server.onJson("GET", "/api/v1/reference-cases", []);
  server.onJson("GET", "/api/v1/runs", { runs: [], limit: 20 });
  server.onJson("GET", "/api/v1/projects/info", {
    uses_model: true,
    model_id: "Qwen/Qwen2.5-Coder-3B-Instruct-GGUF",
    ready: true,
    detail: null,
    max_zip_bytes: 5_000_000,
    tests_allowed: true,
    ...info,
  });
  server.onJson("GET", "/api/v1/projects", { projects: [], limit: 20 });
  return server;
}

async function openProjectTab() {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Whole project" }));
  await screen.findByRole("heading", { name: "Review a project" });
}

function chooseZip(name = "calc.zip", size = 10) {
  const input = document.querySelector<HTMLInputElement>(".dropzone input[type=file]");
  if (!input) throw new Error("no file input");
  const file = new File([new Uint8Array(size)], name, { type: "application/zip" });
  fireEvent.change(input, { target: { files: [file] } });
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("project review tab", () => {
  it("is not loaded until the tab is opened", async () => {
    const server = setup();
    render(<App />);
    await screen.findByRole("button", { name: "Whole project" });
    expect(server.calls("GET", "/api/v1/projects/info")).toHaveLength(0);
  });

  it("uploads a zip, follows the review and shows the results", async () => {
    const server = setup();
    const running = project({ status: "reviewing", progress: "Agents are looking for bugs", findings: [], fixes: [] });
    const records = [running, project()];
    server.on("POST", "/api/v1/projects", () =>
      json(202, { project_id: PROJECT_ID, status: "queued", poll_url: `/api/v1/projects/${PROJECT_ID}` }),
    );
    server.on("GET", `/api/v1/projects/${PROJECT_ID}`, () => json(200, records.length > 1 ? records.shift() : records[0]));
    await openProjectTab();
    expect(screen.getByText("AI model: Qwen/Qwen2.5-Coder-3B-Instruct-GGUF")).toBeInTheDocument();
    chooseZip();
    fireEvent.click(screen.getByLabelText(/Run my project's tests/));
    fireEvent.click(screen.getByRole("button", { name: "Review project" }));

    expect(await screen.findByText("Agents are looking for bugs")).toBeInTheDocument();
    const [upload] = server.calls("POST", "/api/v1/projects");
    expect(upload?.headers["content-type"]).toBe("application/zip");
    expect(upload?.query.get("name")).toBe("calc");
    expect(upload?.query.get("run_tests")).toBe("true");

    await waitFor(() => expect(screen.getByRole("tab", { name: "Problems (3)" })).toBeInTheDocument(), {
      timeout: 4000,
    });
    const cards = document.querySelector(".summary-cards") as HTMLElement;
    expect(within(cards).getByText("Problems found")).toBeInTheDocument();
    expect(screen.getByText("The model-call budget was reached.")).toBeInTheDocument();
    expect(screen.getByText("ruff B006", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("AI agent, double-checked", { exact: false })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Security 1" }));
    expect(screen.queryByText("Import cycle between modules")).not.toBeInTheDocument();
    expect(screen.getByText("Shell command built from input")).toBeInTheDocument();
  });

  it("accepts a fix and downloads the fixed project", async () => {
    const server = setup();
    let decided = project();
    server.on("GET", `/api/v1/projects/${PROJECT_ID}`, () => json(200, decided));
    server.on("POST", `/api/v1/projects/${PROJECT_ID}/fixes/X001/decision`, (request) => {
      decided = project({ fixes: [fix({ decision: (request.body as { decision: "accepted" }).decision }), project().fixes[1] as Fix] });
      return json(200, decided);
    });
    server.on(
      "GET",
      `/api/v1/projects/${PROJECT_ID}/download`,
      () =>
        new Response(new Blob(["zip"]), {
          status: 200,
          headers: { "Content-Type": "application/zip", "Content-Disposition": 'attachment; filename="calc-reviewed.zip"' },
        }),
    );
    server.onJson("GET", "/api/v1/projects", {
      projects: [{ project_id: PROJECT_ID, name: "calc", created_at: "2026-10-21T10:00:00Z", status: "completed", summary: { findings: 3 } }],
      limit: 20,
    });
    const created: string[] = [];
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => undefined }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      created.push(this.download);
    });

    await openProjectTab();
    fireEvent.click(await screen.findByRole("button", { name: "Open" }));
    fireEvent.click(await screen.findByRole("tab", { name: "Fixes (2)" }));
    const zipButton = screen.getByRole("button", { name: /Fixed project/ });
    expect(zipButton).toBeDisabled();

    const card = screen.getByRole("article", { name: "Fix for average" });
    expect(within(card).getByText("Ready to use")).toBeInTheDocument();
    expect(within(card).getAllByText("Passed")).toHaveLength(4);
    const uncertain = screen.getByRole("article", { name: "Fix for run" });
    expect(within(uncertain).getByText("No related test")).toBeInTheDocument();
    expect(within(uncertain).getByText("Why not ready")).toBeInTheDocument();

    fireEvent.click(within(card).getByRole("button", { name: /Accept/ }));
    await waitFor(() => expect(zipButton).toBeEnabled());
    expect(within(card).getByText("Accepted")).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(zipButton);
    });
    await waitFor(() => expect(created).toEqual(["calc-reviewed.zip"]));
    click.mockRestore();
  });

  it("shows the architecture and links a problem to its fix", async () => {
    const server = setup();
    server.on("GET", `/api/v1/projects/${PROJECT_ID}`, () => json(200, project()));
    server.onJson("GET", "/api/v1/projects", {
      projects: [{ project_id: PROJECT_ID, name: "calc", created_at: "2026-10-21T10:00:00Z", status: "completed", summary: {} }],
      limit: 20,
    });
    await openProjectTab();
    fireEvent.click(await screen.findByRole("button", { name: "Open" }));
    fireEvent.click(await screen.findByRole("tab", { name: "Architecture" }));
    expect(screen.getByText("app → app.calc → app")).toBeInTheDocument();
    expect(screen.getByText("Small and simple.", { exact: false })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Problems (3)" }));
    Element.prototype.scrollIntoView = vi.fn();
    fireEvent.click(screen.getAllByRole("button", { name: /See the proposed fix/ })[0] as HTMLElement);
    expect(screen.getByRole("tab", { name: "Fixes (2)" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("article", { name: "Fix for average" })).toHaveAttribute("data-highlighted", "true");
  });

  it("explains a disabled test option, a failed review and a refused upload", async () => {
    const server = setup({ tests_allowed: false, uses_model: false });
    server.on("POST", "/api/v1/projects", () =>
      apiError(422, "invalid_project", "The zip contains no Python files to review.", [{ reason: "no_python_files" }]),
    );
    await openProjectTab();
    expect(screen.getByText("Static checks only (no AI model)")).toBeInTheDocument();
    expect(screen.getByLabelText(/Run my project's tests/)).toBeDisabled();
    expect(screen.getByText(/Turned off on this server/)).toBeInTheDocument();
    chooseZip();
    fireEvent.click(screen.getByRole("button", { name: "Review project" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("no Python files");

    server.on("GET", `/api/v1/projects/${PROJECT_ID}`, () =>
      json(200, project({ status: "failed", error: { code: "interrupted", message: "The service stopped." } })),
    );
    server.onJson("GET", "/api/v1/projects", {
      projects: [{ project_id: PROJECT_ID, name: "calc", created_at: "2026-10-21T10:00:00Z", status: "failed", summary: {} }],
      limit: 20,
    });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    fireEvent.click(await screen.findByRole("button", { name: "Open" }));
    expect(await screen.findByText("The service stopped.")).toBeInTheDocument();
  });

  it("blocks files larger than the limit", async () => {
    setup({ max_zip_bytes: 5 });
    await openProjectTab();
    chooseZip("big.zip", 10);
    expect(screen.getByText("The file is larger than 5 MB.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review project" })).toBeDisabled();
  });
});

describe("project review labels", () => {
  it("names sources plainly", () => {
    expect(sourceLabel(finding())).toBe("ruff B006");
    expect(sourceLabel(finding({ source: "static:task:guard_clauses" }))).toBe("guard-clause check");
    expect(sourceLabel(finding({ source: "static:rule:value-never-used" }))).toBe("static check");
    expect(sourceLabel(finding({ source: "agent:bug_finder" }))).toBe("AI agent");
    expect(sourceLabel(finding({ source: "agent:bug_finder", also_reported_by: ["agent:finding_checker"] }))).toBe(
      "AI agent, double-checked",
    );
  });

  it("never draws missing evidence like a pass", () => {
    expect(checkMeta("tests", { status: "pass", detail: null }).tone).toBe("pass");
    expect(checkMeta("review", { status: "accept", detail: null }).tone).toBe("pass");
    for (const status of ["not_run", "not_available", "error"]) {
      const meta = checkMeta("tests", { status, detail: null });
      expect(meta.tone).not.toBe("pass");
      expect(meta.absent).toBe(true);
    }
    expect(checkMeta("static", { status: "partial", detail: null }).label).toBe("Partly");
    expect(checkMeta("review", { status: "reject", detail: null }).label).toBe("Rejected");
    expect(checkMeta("tests", { status: "not_run", detail: null }).label).toBe("Off");
  });
});

describe("paused function model", () => {
  it("is shown as paused without a warning", async () => {
    const server = new MockServer().install();
    const base = health("local_model");
    server.onJson(
      "GET",
      "/health",
      health("local_model", {
        provider: {
          ...base.provider,
          ready: false,
          detail: "Paused: the other model is using the GPU; this model loads again on its next call.",
        },
      }),
    );
    server.onJson("GET", "/api/v1/reference-cases", []);
    server.onJson("GET", "/api/v1/runs", { runs: [], limit: 20 });
    render(<App />);
    expect(await screen.findByText("Paused", { selector: ".service__pill" })).toBeInTheDocument();
    expect(screen.queryByText("The model is not ready.")).not.toBeInTheDocument();
  });
});
