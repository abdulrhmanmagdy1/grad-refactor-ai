/**
 * Types and client calls of the project review API (/api/v1/projects).
 *
 * The record shapes mirror src/refactor_ai/project/models.py. A project is uploaded as a
 * raw zip body; the review runs in the background and is polled like a run.
 */

import { API_PREFIX, DOWNLOAD_TIMEOUT_MS, filenameFromContentDisposition, readJson, request } from "./client";
import type { Disposition, HumanDecision, ModelReference } from "./contracts";

export type ProjectStatus = "queued" | "indexing" | "scanning" | "reviewing" | "fixing" | "completed" | "failed";
export type Category = "bug" | "architecture" | "security" | "quality" | "refactoring";
export type Severity = "high" | "medium" | "low";

export const CATEGORIES: readonly Category[] = ["bug", "security", "architecture", "quality", "refactoring"];
export const SEVERITIES: readonly Severity[] = ["high", "medium", "low"];
export const PROJECT_TERMINAL: readonly ProjectStatus[] = ["completed", "failed"];

export interface Finding {
  id: string;
  category: Category;
  severity: Severity;
  source: string;
  file: string | null;
  line_start: number | null;
  line_end: number | null;
  symbol: string | null;
  title: string;
  explanation: string;
  evidence: string | null;
  recommendation: string | null;
  confidence: number | null;
  fixable: boolean;
  also_reported_by: string[];
}

export interface FixCheck {
  status: string;
  detail: string | null;
}

export interface Fix {
  id: string;
  finding_ids: string[];
  file: string;
  symbol: string;
  line_start: number;
  line_end: number;
  original: string;
  proposed: string | null;
  imports: string[];
  explanation: string | null;
  diff: string | null;
  produced_by: string;
  syntax: FixCheck;
  static_recheck: FixCheck;
  tests: FixCheck;
  review: FixCheck;
  review_reasons: string[];
  disposition: Disposition;
  disposition_reasons: string[];
  decision: HumanDecision | null;
}

export interface AgentCall {
  role: string;
  target: string;
  status: string;
  elapsed_s: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  finish_reason: string | null;
  error: string | null;
  raw_output: string | null;
}

export interface ProjectRecord {
  schema_version: number;
  project_id: string;
  name: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  status: ProjectStatus;
  progress: string | null;
  run_tests: boolean;
  summary: Record<string, unknown>;
  architecture: Record<string, unknown>;
  findings: Finding[];
  fixes: Fix[];
  baseline_tests: Record<string, unknown> | null;
  model: ModelReference | null;
  calls: AgentCall[];
  stage_times: { stage: string; seconds: number }[];
  warnings: string[];
  skipped_files: { path: string; reason: string }[];
  error: { code: string; message: string } | null;
}

export type ProjectSummary = Pick<
  ProjectRecord,
  "project_id" | "name" | "created_at" | "finished_at" | "status" | "progress" | "run_tests" | "summary" | "error"
>;

export interface ProjectInfo {
  uses_model: boolean;
  model_id?: string | null;
  model_revision?: string | null;
  ready?: boolean;
  detail: string | null;
  max_zip_bytes: number;
  tests_allowed: boolean;
}

export interface ProjectAccepted {
  project_id: string;
  status: ProjectStatus;
  poll_url: string;
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export function isProjectRecord(value: unknown): value is ProjectRecord {
  return (
    isObject(value) &&
    typeof value.project_id === "string" &&
    typeof value.status === "string" &&
    Array.isArray(value.findings) &&
    Array.isArray(value.fixes)
  );
}

function shaped<T>(value: unknown, guard: (value: unknown) => value is T, what: string): T {
  if (!guard(value)) throw new Error(`The service sent ${what} in an unexpected format.`);
  return value;
}

export function projectPath(projectId: string): string {
  return `${API_PREFIX}/projects/${encodeURIComponent(projectId)}`;
}

export function getProjectInfo(signal?: AbortSignal): Promise<ProjectInfo> {
  return request("GET", `${API_PREFIX}/projects/info`, { signal }, async (response) => {
    const value = await readJson(response, "the project review settings");
    return shaped(
      value,
      (v): v is ProjectInfo => isObject(v) && typeof v.uses_model === "boolean",
      "the project review settings",
    );
  });
}

export function uploadProject(
  file: Blob,
  name: string,
  runTests: boolean,
  signal?: AbortSignal,
): Promise<ProjectAccepted> {
  const query = new URLSearchParams({ name, run_tests: String(runTests) });
  return request(
    "POST",
    `${API_PREFIX}/projects?${query.toString()}`,
    { raw: { data: file, type: "application/zip" }, signal, timeoutMs: DOWNLOAD_TIMEOUT_MS },
    async (response) => {
      const value = await readJson(response, "the upload confirmation");
      return shaped(
        value,
        (v): v is ProjectAccepted => isObject(v) && typeof v.project_id === "string",
        "the upload confirmation",
      );
    },
  );
}

export function getProject(projectId: string, signal?: AbortSignal): Promise<ProjectRecord> {
  return request("GET", projectPath(projectId), { signal }, async (response) =>
    shaped(await readJson(response, "a project review"), isProjectRecord, "the project review"),
  );
}

export function listProjects(limit: number, signal?: AbortSignal): Promise<ProjectSummary[]> {
  const query = new URLSearchParams({ limit: String(limit) });
  return request("GET", `${API_PREFIX}/projects?${query.toString()}`, { signal }, async (response) => {
    const value = await readJson(response, "the project reviews");
    if (!isObject(value) || !Array.isArray(value.projects)) {
      throw new Error("The service sent the project reviews in an unexpected format.");
    }
    return value.projects as ProjectSummary[];
  });
}

export function decideFix(
  projectId: string,
  fixId: string,
  decision: HumanDecision,
  signal?: AbortSignal,
): Promise<ProjectRecord> {
  return request(
    "POST",
    `${projectPath(projectId)}/fixes/${encodeURIComponent(fixId)}/decision`,
    { body: { decision }, signal },
    async (response) => shaped(await readJson(response, "a project review"), isProjectRecord, "the project review"),
  );
}

export function deleteProject(projectId: string, signal?: AbortSignal): Promise<void> {
  return request("DELETE", projectPath(projectId), { signal }, async () => undefined);
}

export interface DownloadedFile {
  blob: Blob;
  filename: string;
}

function download(path: string, fallback: string, accept: string): Promise<DownloadedFile> {
  return request("GET", path, { timeoutMs: DOWNLOAD_TIMEOUT_MS, accept }, async (response) => ({
    blob: await response.blob(),
    filename: filenameFromContentDisposition(response.headers.get("Content-Disposition")) ?? fallback,
  }));
}

export function fetchPatch(projectId: string): Promise<DownloadedFile> {
  return download(`${projectPath(projectId)}/patch`, "accepted-fixes.patch", "text/x-diff, */*;q=0.1");
}

export function fetchFixedProject(projectId: string): Promise<DownloadedFile> {
  return download(`${projectPath(projectId)}/download`, "project-reviewed.zip", "application/zip, */*;q=0.1");
}
