// @vitest-environment node
/**
 * Compares the TypeScript contract mirror with the Python sources it copies:
 * src/refactor_ai/contracts.py (models, enums, literals, constants),
 * src/refactor_ai/tasks/guard_clauses.py (task limits, rubric checks, reason codes) and
 * src/refactor_ai/api.py (history limits). A change on the Python side fails here
 * until the frontend is updated.
 */
import { readFileSync } from "node:fs";
import { URL as NodeURL, fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import * as C from "../api/contracts";
import { RUBRIC_CHECK_LABELS, STOP_REASON_LABELS, TASK_REASON_TEXT, runErrorHint } from "../lib/labels";
import { settings } from "./fixtures";
import { CONTRACT_FIELDS, INTERNAL_MODELS } from "./contractFields";

function readRepoFile(relative: string): string {
  const path = fileURLToPath(new NodeURL(`../../../${relative}`, import.meta.url));
  return readFileSync(path, "utf8").replace(/\r\n/g, "\n");
}

const contracts = readRepoFile("src/refactor_ai/contracts.py");
const task = readRepoFile("src/refactor_ai/tasks/guard_clauses.py");
const api = readRepoFile("src/refactor_ai/api.py");
const coordinator = readRepoFile("src/refactor_ai/agents/coordinator.py");
const runErrors = readRepoFile("src/refactor_ai/runs/errors.py");

interface PyClass {
  base: string;
  body: string;
}

function pyClasses(source: string): Map<string, PyClass> {
  const classes = new Map<string, PyClass>();
  for (const match of source.matchAll(/^class (\w+)\((\w+)\):\n((?:(?:[ \t]+.*)?\n)*)/gm)) {
    classes.set(match[1]!, { base: match[2]!, body: match[3]! });
  }
  return classes;
}

const classes = pyClasses(contracts);

function pyFields(name: string): string[] {
  const cls = classes.get(name);
  if (!cls) throw new Error(`contracts.py has no class ${name}`);
  return [...cls.body.matchAll(/^ {4}(\w+): /gm)].map((match) => match[1]!).filter((field) => field !== "model_config");
}

function pyEnumValues(name: string): string[] {
  const cls = classes.get(name);
  if (!cls || cls.base !== "StrEnum") throw new Error(`contracts.py has no StrEnum ${name}`);
  return [...cls.body.matchAll(/^ {4}\w+ = "([^"]+)"$/gm)].map((match) => match[1]!);
}

/** String values of a Literal[...] annotation, which may span several lines. */
function pyLiteral(className: string, field: string): string[] {
  const cls = classes.get(className);
  if (!cls) throw new Error(`contracts.py has no class ${className}`);
  const start = cls.body.search(new RegExp(`^ {4}${field}: .*Literal\\[`, "m"));
  if (start === -1) throw new Error(`${className}.${field} is not a Literal`);
  const open = cls.body.indexOf("Literal[", start) + "Literal[".length;
  const close = cls.body.indexOf("]", open);
  return [...cls.body.slice(open, close).matchAll(/"([^"]+)"/g)].map((match) => match[1]!);
}

function pyConstant(source: string, name: string): string {
  const match = new RegExp(`^${name} = (.+)$`, "m").exec(source);
  if (!match) throw new Error(`No constant ${name}`);
  return match[1]!.trim();
}

const sorted = (values: readonly string[]) => [...values].sort();

describe("contract mirror of contracts.py", () => {
  it.each(Object.keys(CONTRACT_FIELDS))("%s has exactly the Python fields", (name) => {
    expect(sorted(CONTRACT_FIELDS[name as keyof typeof CONTRACT_FIELDS])).toEqual(sorted(pyFields(name)));
  });

  it("classifies every Python contract model as mirrored or internal", () => {
    const models = [...classes.entries()].filter(([, cls]) => cls.base === "Contract").map(([name]) => name);
    const known = new Set<string>([...Object.keys(CONTRACT_FIELDS), ...INTERNAL_MODELS]);
    expect(models.filter((name) => !known.has(name))).toEqual([]);
    expect([...known].filter((name) => !models.includes(name))).toEqual([]);
  });

  it.each([
    ["ProviderMode", C.PROVIDER_MODES],
    ["Role", C.ROLES],
    ["WorkflowMode", C.WORKFLOW_MODES],
    ["RunStatus", C.RUN_STATUSES],
    ["Disposition", C.DISPOSITIONS],
    ["ProviderErrorCode", C.PROVIDER_ERROR_CODES],
    ["ReviewVerdict", C.REVIEW_VERDICTS],
  ] as const)("enum %s matches", (name, values) => {
    expect(sorted(values)).toEqual(sorted(pyEnumValues(name)));
  });

  it.each([
    ["SyntaxCheck", "status", C.SYNTAX_STATUSES],
    ["RubricCheck", "status", C.RUBRIC_STATUSES],
    ["ReferenceTestFailure", "kind", C.REFERENCE_FAILURE_KINDS],
    ["ReferenceTestsResult", "status", C.REFERENCE_TEST_STATUSES],
    ["ModelReviewResult", "status", C.MODEL_REVIEW_STATUSES],
    ["StageTiming", "stage", C.STAGES],
    ["AnalysisReport", "source", C.ANALYSIS_SOURCES],
    ["RunRecord", "human_decision", C.HUMAN_DECISIONS],
    ["RunSummary", "human_decision", C.HUMAN_DECISIONS],
    ["DecisionRequest", "decision", C.HUMAN_DECISIONS],
    ["HealthResponse", "status", ["ok"]],
    ["RunCreateRequest", "task_type", [C.TASK_TYPE]],
  ] as const)("literal %s.%s matches", (className, field, values) => {
    expect(sorted(values)).toEqual(sorted(pyLiteral(className, field)));
  });

  it("uses the same constants", () => {
    expect(Number(pyConstant(contracts, "SCHEMA_VERSION"))).toBe(C.SCHEMA_VERSION);
    expect(Number(pyConstant(contracts, "MAX_CODE_CHARS"))).toBe(C.MAX_CODE_CHARS);
    expect(pyConstant(contracts, "TERMINAL_STATUSES")).toBe("frozenset({RunStatus.COMPLETED, RunStatus.FAILED})");
    expect([...C.TERMINAL_STATUSES]).toEqual(["completed", "failed"]);
  });
});

describe("task and API constants", () => {
  it("matches the task limits and type", () => {
    expect(Number(pyConstant(task, "MAX_INPUT_CHARS"))).toBe(C.TASK_MAX_CHARS);
    expect(Number(pyConstant(task, "MAX_INPUT_LINES"))).toBe(C.TASK_MAX_LINES);
    expect(pyConstant(task, "TASK_TYPE")).toBe(`"${C.TASK_TYPE}"`);
  });

  it("has a label for every rubric check", () => {
    const block = /^RUBRIC_CHECKS = \(\n([\s\S]*?)\n\)/m.exec(task)?.[1] ?? "";
    const checks = [...block.matchAll(/"(\w+)"/g)].map((match) => match[1]!);
    expect(checks.length).toBeGreaterThan(0);
    expect(sorted(Object.keys(RUBRIC_CHECK_LABELS))).toEqual(sorted(checks));
  });

  it("has a text for every task reason code", () => {
    const block = /^REASON_TEXT = \{\n([\s\S]*?)\n\}/m.exec(task)?.[1] ?? "";
    const codes = [...block.matchAll(/^ {4}"(\w+)":/gm)].map((match) => match[1]!);
    expect(codes.length).toBeGreaterThan(0);
    expect(sorted(Object.keys(TASK_REASON_TEXT))).toEqual(sorted(codes));
  });

  it("uses the history limits of the API", () => {
    expect(Number(pyConstant(api, "RUN_LIST_DEFAULT"))).toBe(C.RUN_LIST_DEFAULT_LIMIT);
    expect(Number(pyConstant(api, "RUN_LIST_MAX"))).toBe(C.RUN_LIST_MAX_LIMIT);
  });
});

describe("workflow defaults and run vocabulary", () => {
  it("test fixtures use the default generation limits of WorkflowSettings", () => {
    const body = classes.get("WorkflowSettings")?.body ?? "";
    const parsed: Record<string, Record<string, number>> = {};
    for (const match of body.matchAll(/Role\.(\w+): GenerationConfig\(([^)]*)\)/g)) {
      const values: Record<string, number> = {};
      for (const pair of match[2]!.matchAll(/(\w+)=([\d.]+)/g)) values[pair[1]!] = Number(pair[2]);
      parsed[match[1]!.toLowerCase()] = values;
    }
    expect(Object.keys(parsed).sort()).toEqual(["analysis", "refactor", "review"]);
    const fixture = settings().generation;
    for (const [role, values] of Object.entries(parsed)) {
      expect(fixture[role as C.Role]).toMatchObject(values);
    }
  });

  it("labels every stop reason the coordinator writes", () => {
    const reasons = [...coordinator.matchAll(/^STOP_\w+ = "(\w+)"/gm)].map((match) => match[1]!);
    expect(reasons).toContain("correction_input_too_long");
    expect(reasons.filter((reason) => !(reason in STOP_REASON_LABELS))).toEqual([]);
  });

  it("explains every run error code the service writes", () => {
    const block = /class RunErrorCode\(StrEnum\):\n([\s\S]*?)\n\n\n/.exec(runErrors)?.[1] ?? "";
    const codes = [...block.matchAll(/^ {4}\w+ = "(\w+)"$/gm)].map((match) => match[1]!);
    expect(codes).toContain("adapter_unavailable");
    expect(codes.filter((code) => runErrorHint(code) === null)).toEqual([]);
  });
});
