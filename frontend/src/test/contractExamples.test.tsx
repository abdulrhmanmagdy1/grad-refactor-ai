/**
 * Checks the frontend against the backend's published examples in
 * docs/architecture/examples/: every object has exactly the mirrored fields (recursively),
 * passes the client's runtime checks, and every run record renders in the run panel with
 * the right outcome and a diff the parser accepts.
 */
import { render, screen } from "@testing-library/react";
import { readFileSync, readdirSync } from "node:fs";
import { URL as NodeURL, fileURLToPath } from "node:url";
import { createRef } from "react";
import { describe, expect, it } from "vitest";
import {
  ApiError,
  isHealthResponse,
  isRunAccepted,
  isRunList,
  isRunRecord,
  normalizeReferenceCases,
} from "../api/client";
import type { HealthResponse, RunRecord } from "../api/contracts";
import { AppHeader } from "../components/AppHeader";
import { RunPanel } from "../components/RunPanel";
import { describeSubmissionError, syntaxLocation } from "../components/SubmissionError";
import { buildSplitRows, parseUnifiedDiff } from "../lib/diff";
import type { RunEntry } from "../state/runs";
import { CONTRACT_FIELDS, type MirroredModel, NESTED } from "./contractFields";

// Node's URL class: in the jsdom environment the global URL is jsdom's.
const directory = fileURLToPath(new NodeURL("../../../docs/architecture/examples/", import.meta.url));
const files = readdirSync(directory).filter((name) => name.endsWith(".json")).sort();
const load = (name: string): unknown => JSON.parse(readFileSync(`${directory}${name}`, "utf8"));

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** Problems found when checking a value against a mirrored model, recursively. */
function shapeProblems(value: unknown, model: MirroredModel, path: string): string[] {
  if (!isObject(value)) return [`${path}: expected an object for ${model}`];
  const expected = CONTRACT_FIELDS[model];
  const problems: string[] = [];
  for (const key of Object.keys(value)) {
    if (!expected.includes(key)) problems.push(`${path}.${key}: not in ${model}`);
  }
  for (const key of expected) {
    // RunCreateRequest fields with defaults may be omitted by a client.
    if (!(key in value) && !(model === "RunCreateRequest" && key !== "code")) {
      problems.push(`${path}.${key}: missing from ${model}`);
    }
  }
  for (const [key, shape] of Object.entries(NESTED[model] ?? {})) {
    const child = value[key];
    if (child === null || child === undefined) continue;
    if (typeof shape === "string") {
      problems.push(...shapeProblems(child, shape, `${path}.${key}`));
    } else if ("list" in shape) {
      if (!Array.isArray(child)) problems.push(`${path}.${key}: expected a list`);
      else child.forEach((item, index) => problems.push(...shapeProblems(item, shape.list, `${path}.${key}[${index}]`)));
    } else if (isObject(child)) {
      for (const [entry, item] of Object.entries(child)) {
        problems.push(...shapeProblems(item, shape.map, `${path}.${key}.${entry}`));
      }
    } else {
      problems.push(`${path}.${key}: expected a mapping`);
    }
  }
  return problems;
}

function modelFor(file: string): MirroredModel | "ReferenceCaseList" | null {
  if (file.startsWith("run_record_")) return "RunRecord";
  if (file.startsWith("health_")) return "HealthResponse";
  if (file.startsWith("error_")) return "ErrorResponse";
  const direct: Record<string, MirroredModel | "ReferenceCaseList"> = {
    "run_create_request.json": "RunCreateRequest",
    "run_accepted.json": "RunAccepted",
    "run_list.json": "RunList",
    "decision_request.json": "DecisionRequest",
    "reference_cases.json": "ReferenceCaseList",
    "analysis_report.json": "AnalysisReport",
    "review_result.json": "ReviewResult",
  };
  return direct[file] ?? null;
}

// analyze_response.json belongs to the static /api/v1/analyze endpoint, which the UI does not call.
const IGNORED = new Set(["analyze_response.json"]);

describe("backend contract examples", () => {
  it("are present", () => {
    expect(files.length).toBeGreaterThan(10);
  });

  it.each(files.filter((file) => !IGNORED.has(file)))("%s matches the frontend contract", (file) => {
    const model = modelFor(file);
    expect(model, `no model mapping for ${file}`).not.toBeNull();
    const value = load(file);
    if (model === "ReferenceCaseList") {
      const cases = normalizeReferenceCases(value);
      expect(cases.length).toBeGreaterThan(0);
      cases.forEach((item, index) => expect(shapeProblems(item, "ReferenceCaseSummary", `[${index}]`)).toEqual([]));
      return;
    }
    expect(shapeProblems(value, model!, file)).toEqual([]);
    if (model === "RunRecord") expect(isRunRecord(value)).toBe(true);
    if (model === "HealthResponse") expect(isHealthResponse(value)).toBe(true);
    if (model === "RunList") expect(isRunList(value)).toBe(true);
    if (model === "RunAccepted") expect(isRunAccepted(value)).toBe(true);
  });

  it.each(files.filter((file) => file.startsWith("error_")))("%s is explained to the person", (file) => {
    const body = load(file) as { error: { code: string; message: string; details: Array<Record<string, unknown>> | null } };
    const error = new ApiError({
      kind: "http",
      status: 422,
      code: body.error.code,
      message: body.error.message,
      details: body.error.details ?? [],
    });
    const copy = describeSubmissionError(error);
    expect(copy.title.length).toBeGreaterThan(0);
    if (["invalid_syntax", "validation_error", "reference_case_mismatch", "unknown_reference_case", "busy"].includes(error.code)) {
      expect(copy.title).not.toBe("The run could not be started");
    }
    if (error.code === "invalid_syntax") expect(syntaxLocation(error)).toEqual({ line: 1, column: 26 });
  });
});

function entryFor(record: RunRecord): RunEntry {
  return {
    runId: record.run_id,
    record,
    request: null,
    knownStatus: record.status,
    trackedSince: Date.now(),
    poll: record.status === "completed" || record.status === "failed" ? "done" : "polling",
    pollGeneration: 1,
    retry: null,
    error: null,
    timedOutAfterMs: null,
    loading: false,
    statusTrail: [record.status],
  };
}

const EXPECTED_TEXT: Record<string, RegExp> = {
  "run_record_queued.json": /Waiting to start/,
  "run_record_analyzing.json": /Finding nested if statements/,
  "run_record_proposal_ready.json": /Ready to use/,
  "run_record_uncertain.json": /^Not sure$/,
  "run_record_no_change.json": /Nothing to change/,
  "run_record_rejected.json": /Not safe to use/,
  "run_record_failed.json": /Something went wrong/,
  "run_record_interrupted.json": /Something went wrong/,
  "run_record_adapter_unavailable.json": /The fine-tuned model is missing/,
};

describe("run record examples render", () => {
  it.each(files.filter((file) => file.startsWith("run_record_")))("%s", (file) => {
    const record = load(file) as RunRecord;
    render(
      <RunPanel
        entry={entryFor(record)}
        headingRef={createRef()}
        fakeBannerShown={false}
        editorHoldsInput={false}
        submitBlocked={false}
        decision={{ pending: null, error: null }}
        retry={{ runId: null, pending: false, failure: null }}
        onDecide={() => undefined}
        onResume={() => undefined}
        onReload={() => undefined}
        onTryAgain={() => undefined}
        onLoadInput={() => undefined}
      />,
    );
    const expected = EXPECTED_TEXT[file];
    expect(expected, `add the expected text for ${file}`).toBeDefined();
    expect(screen.getAllByText(expected!).length).toBeGreaterThan(0);
    if (record.provider_mode === "fake") {
      expect(screen.getByText("Demo mode: this result is not from the AI model.")).toBeInTheDocument();
    }
    if (record.diff) {
      const parsed = parseUnifiedDiff(record.diff);
      expect(parsed.hunks.length).toBeGreaterThan(0);
      expect(buildSplitRows(record.original_code, record.proposed_code ?? "", parsed)).not.toBeNull();
    }
    if (record.status === "failed") {
      expect(screen.getAllByText(record.error!.code).length).toBeGreaterThan(0);
      expect(screen.queryByRole("button", { name: "Download proposal" })).toBeNull();
    }
  });
});

const HEALTH_EXPECTED: Record<string, { weights: string; state: string; notice: RegExp | null }> = {
  "health_fake.json": { weights: "Fixed rules (fake provider)", state: "Ready", notice: null },
  "health_local.json": { weights: "Fine-tuned LoRA adapter", state: "Ready", notice: null },
  "health_local_loading.json": {
    weights: "Fine-tuned LoRA adapter",
    state: "Loading",
    notice: /^The model is loading\. The model is loading in the background/,
  },
  "health_local_adapter_missing.json": {
    weights: "Adapter requested, none configured",
    state: "Adapter missing",
    notice: /^The fine-tuned adapter is missing\. REFACTOR_AI_REFACTOR_USE_ADAPTER=true/,
  },
};

describe("health examples render in the header", () => {
  it("has an expectation for every health example", () => {
    expect(files.filter((file) => file.startsWith("health_")).sort()).toEqual(Object.keys(HEALTH_EXPECTED).sort());
  });

  it.each(Object.keys(HEALTH_EXPECTED))("%s", (file) => {
    const health = load(file) as HealthResponse;
    const expected = HEALTH_EXPECTED[file]!;
    render(<AppHeader health={health} error={null} loading={false} onRetry={() => undefined} />);
    const status = screen.getByRole("region", { name: "Service status" });
    expect(status).toHaveTextContent(expected.weights);
    expect(status).toHaveTextContent(expected.state);
    const notice = status.querySelector(".service__notice");
    if (expected.notice) expect(notice?.textContent).toMatch(expected.notice);
    else expect(notice).toBeNull();
  });
});
