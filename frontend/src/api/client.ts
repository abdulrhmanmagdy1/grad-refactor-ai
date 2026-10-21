/**
 * Typed client for the local refactoring service.
 *
 * All URLs are relative to the page origin, so the same build works behind the Vite
 * development proxy and when FastAPI serves frontend/dist at "/". Every failure is
 * reported as an ApiError: HTTP errors keep the ErrorResponse code, message and details;
 * network problems, timeouts and malformed responses get their own kinds.
 */

import {
  type ErrorResponse,
  type HealthResponse,
  type HumanDecision,
  type ReferenceCaseSummary,
  type RunAccepted,
  type RunCreateRequest,
  type RunList,
  type RunRecord,
  type RunSummary,
  isProviderMode,
  isRunStatus,
  isWorkflowMode,
} from "./contracts";

export type ApiErrorKind = "http" | "network" | "timeout" | "aborted" | "invalid_response";

/** HTTP statuses after which the same request may succeed later (busy, proxy or server hiccup). */
const TRANSIENT_HTTP_STATUSES: ReadonlySet<number> = new Set([429, 500, 502, 503, 504]);

export interface ApiErrorInit {
  kind: ApiErrorKind;
  code: string;
  message: string;
  status?: number | null;
  details?: ReadonlyArray<Record<string, unknown>>;
  retryAfterSeconds?: number | null;
}

export class ApiError extends Error {
  override readonly name = "ApiError";
  readonly kind: ApiErrorKind;
  readonly code: string;
  readonly status: number | null;
  readonly details: ReadonlyArray<Record<string, unknown>>;
  readonly retryAfterSeconds: number | null;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.kind = init.kind;
    this.code = init.code;
    this.status = init.status ?? null;
    this.details = init.details ?? [];
    this.retryAfterSeconds = init.retryAfterSeconds ?? null;
  }

  /** True when repeating the same request later may succeed. */
  get transient(): boolean {
    if (this.kind === "network" || this.kind === "timeout") return true;
    if (this.kind === "http" && this.status !== null) return TRANSIENT_HTTP_STATUSES.has(this.status);
    return false;
  }
}

/** Converts anything thrown by the client or a caller into an ApiError. */
export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  const message = error instanceof Error && error.message ? error.message : String(error);
  return new ApiError({ kind: "invalid_response", code: "client_error", message });
}

export const DEFAULT_TIMEOUT_MS = 15_000;
export const DOWNLOAD_TIMEOUT_MS = 30_000;

export interface RequestOptions {
  body?: unknown;
  /** A body sent as-is (for example an uploaded zip), with its media type. */
  raw?: { data: Blob; type: string };
  signal?: AbortSignal | undefined;
  timeoutMs?: number;
  accept?: string;
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const DEFAULT_HTTP_CODES: Record<number, string> = {
  400: "bad_request",
  404: "not_found",
  405: "method_not_allowed",
  409: "conflict",
  413: "payload_too_large",
  422: "validation_error",
  429: "too_many_requests",
  500: "internal_error",
  502: "bad_gateway",
  503: "service_unavailable",
  504: "gateway_timeout",
};

function defaultHttpCode(status: number): string {
  return DEFAULT_HTTP_CODES[status] ?? `http_${status}`;
}

function defaultHttpMessage(status: number): string {
  if (status === 502 || status === 504) {
    return `The service did not answer through the proxy (HTTP ${status}). Check that the backend is running.`;
  }
  return `The service answered with HTTP ${status}.`;
}

/** Retry-After as whole seconds (delay-seconds or HTTP-date form), or null. */
export function parseRetryAfter(value: string | null, now: number = Date.now()): number | null {
  if (value === null) return null;
  const trimmed = value.trim();
  if (/^\d+$/.test(trimmed)) return Number(trimmed);
  const date = Date.parse(trimmed);
  if (Number.isNaN(date)) return null;
  return Math.max(0, Math.ceil((date - now) / 1000));
}

function retryAfterFromDetails(details: ReadonlyArray<Record<string, unknown>>): number | null {
  for (const item of details) {
    const value = item["retry_after_s"];
    if (typeof value === "number" && Number.isFinite(value) && value >= 0) return Math.ceil(value);
  }
  return null;
}

function isErrorResponse(value: unknown): value is ErrorResponse {
  return (
    isObject(value) &&
    isObject(value.error) &&
    typeof value.error.code === "string" &&
    typeof value.error.message === "string"
  );
}

function describeValidationItem(item: Record<string, unknown>): string {
  const text = typeof item.message === "string" ? item.message : typeof item.msg === "string" ? item.msg : "";
  const loc = Array.isArray(item.loc) ? item.loc.filter((part) => part !== "body").join(".") : "";
  const clean = text.replace(/^Value error, /, "");
  return loc ? `${loc}: ${clean}` : clean;
}

async function readText(response: Response): Promise<string> {
  try {
    return await response.text();
  } catch {
    return "";
  }
}

async function errorFromResponse(response: Response): Promise<ApiError> {
  const status = response.status;
  const text = await readText(response);
  let payload: unknown;
  try {
    payload = text ? JSON.parse(text) : undefined;
  } catch {
    payload = undefined;
  }
  const headerRetry = parseRetryAfter(response.headers.get("Retry-After"));

  if (isErrorResponse(payload)) {
    const details = Array.isArray(payload.error.details) ? payload.error.details.filter(isObject) : [];
    return new ApiError({
      kind: "http",
      status,
      code: payload.error.code,
      message: payload.error.message,
      details,
      retryAfterSeconds: headerRetry ?? retryAfterFromDetails(details),
    });
  }
  // FastAPI's default bodies, in case a route bypasses the service's error handlers.
  if (isObject(payload) && "detail" in payload) {
    const detail = payload.detail;
    if (Array.isArray(detail)) {
      const details = detail.filter(isObject);
      const message = details.map(describeValidationItem).filter(Boolean).join("; ");
      return new ApiError({
        kind: "http",
        status,
        code: status === 422 ? "validation_error" : defaultHttpCode(status),
        message: message || "The request was not valid.",
        details,
        retryAfterSeconds: headerRetry,
      });
    }
    if (typeof detail === "string" && detail) {
      return new ApiError({
        kind: "http",
        status,
        code: defaultHttpCode(status),
        message: detail,
        retryAfterSeconds: headerRetry,
      });
    }
  }
  return new ApiError({
    kind: "http",
    status,
    code: defaultHttpCode(status),
    message: defaultHttpMessage(status),
    retryAfterSeconds: headerRetry,
  });
}

/**
 * Sends one request and reads the response with `read`, under one timeout that covers
 * both the headers and the body. The caller's signal cancels the request.
 */
export async function request<T>(
  method: string,
  path: string,
  options: RequestOptions,
  read: (response: Response) => Promise<T>,
): Promise<T> {
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  const external = options.signal;
  const forwardAbort = () => controller.abort();
  if (external) {
    if (external.aborted) controller.abort();
    else external.addEventListener("abort", forwardAbort, { once: true });
  }

  const failure = (): ApiError => {
    if (external?.aborted) {
      return new ApiError({ kind: "aborted", code: "aborted", message: "The request was cancelled." });
    }
    if (timedOut) {
      return new ApiError({
        kind: "timeout",
        code: "timeout",
        message: `The service did not answer within ${Math.round(timeoutMs / 1000)} s.`,
      });
    }
    return new ApiError({
      kind: "network",
      code: "network_error",
      message: "Cannot reach the refactoring service. Check that the backend is running.",
    });
  };

  const headers: Record<string, string> = { Accept: options.accept ?? "application/json" };
  const init: RequestInit = {
    method,
    headers,
    signal: controller.signal,
    cache: "no-store",
    credentials: "same-origin",
  };
  if (options.raw !== undefined) {
    headers["Content-Type"] = options.raw.type;
    init.body = options.raw.data;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }

  try {
    let response: Response;
    try {
      response = await fetch(path, init);
    } catch {
      throw failure();
    }
    if (!response.ok) throw await errorFromResponse(response);
    try {
      return await read(response);
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw failure();
    }
  } finally {
    clearTimeout(timer);
    external?.removeEventListener("abort", forwardAbort);
  }
}

function invalidResponse(message: string): ApiError {
  return new ApiError({ kind: "invalid_response", code: "invalid_response", message });
}

export async function readJson(response: Response, what: string): Promise<unknown> {
  const text = await response.text();
  try {
    return JSON.parse(text) as unknown;
  } catch {
    throw invalidResponse(`The service sent ${what} that is not valid JSON.`);
  }
}

export function expectShape<T>(value: unknown, guard: (value: unknown) => value is T, what: string): T {
  if (!guard(value)) throw invalidResponse(`The service sent ${what} in an unexpected format.`);
  return value;
}

// --- Light runtime shape checks. They catch a wrong endpoint or proxy answer early, ---
// --- not every field: the TypeScript types document the full contract.            ---

export function isHealthResponse(value: unknown): value is HealthResponse {
  return (
    isObject(value) &&
    typeof value.version === "string" &&
    isProviderMode(value.mode) &&
    isObject(value.provider) &&
    isProviderMode(value.provider.provider_mode) &&
    isObject(value.runner) &&
    typeof value.runner.enabled === "boolean" &&
    isObject(value.queue)
  );
}

export function isRunAccepted(value: unknown): value is RunAccepted {
  return isObject(value) && typeof value.run_id === "string" && value.run_id !== "" && isRunStatus(value.status);
}

export function isRunRecord(value: unknown): value is RunRecord {
  return (
    isObject(value) &&
    typeof value.run_id === "string" &&
    isRunStatus(value.status) &&
    typeof value.original_code === "string" &&
    isWorkflowMode(value.workflow_mode) &&
    isProviderMode(value.provider_mode) &&
    typeof value.created_at === "string"
  );
}

export function isRunSummary(value: unknown): value is RunSummary {
  return (
    isObject(value) &&
    typeof value.run_id === "string" &&
    isRunStatus(value.status) &&
    typeof value.created_at === "string"
  );
}

export function isRunList(value: unknown): value is RunList {
  return isObject(value) && Array.isArray(value.runs) && value.runs.every(isRunSummary);
}

export function isReferenceCaseSummary(value: unknown): value is ReferenceCaseSummary {
  return (
    isObject(value) &&
    typeof value.case_id === "string" &&
    typeof value.code === "string" &&
    typeof value.function_name === "string"
  );
}

/** The endpoint returns a bare list; a {"cases": [...]} wrapper is also accepted. */
export function normalizeReferenceCases(value: unknown): ReferenceCaseSummary[] {
  const list = Array.isArray(value)
    ? value
    : isObject(value) && Array.isArray(value.cases)
      ? value.cases
      : null;
  if (list === null || !list.every(isReferenceCaseSummary)) {
    throw invalidResponse("The service sent the demonstration cases in an unexpected format.");
  }
  return list;
}

// --- Endpoints ---------------------------------------------------------------------------

export const API_PREFIX = "/api/v1";

export function runPath(runId: string): string {
  return `${API_PREFIX}/runs/${encodeURIComponent(runId)}`;
}

export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request("GET", "/health", { signal }, async (response) =>
    expectShape(await readJson(response, "a health report"), isHealthResponse, "the health report"),
  );
}

export function listReferenceCases(signal?: AbortSignal): Promise<ReferenceCaseSummary[]> {
  return request("GET", `${API_PREFIX}/reference-cases`, { signal }, async (response) =>
    normalizeReferenceCases(await readJson(response, "demonstration cases")),
  );
}

export function createRun(body: RunCreateRequest, signal?: AbortSignal): Promise<RunAccepted> {
  return request("POST", `${API_PREFIX}/runs`, { body, signal }, async (response) =>
    expectShape(await readJson(response, "a run confirmation"), isRunAccepted, "the run confirmation"),
  );
}

export function getRun(runId: string, signal?: AbortSignal): Promise<RunRecord> {
  return request("GET", runPath(runId), { signal }, async (response) =>
    expectShape(await readJson(response, "a run record"), isRunRecord, "the run record"),
  );
}

export function listRuns(limit: number, signal?: AbortSignal): Promise<RunList> {
  const query = new URLSearchParams({ limit: String(limit) });
  return request("GET", `${API_PREFIX}/runs?${query.toString()}`, { signal }, async (response) =>
    expectShape(await readJson(response, "the run history"), isRunList, "the run history"),
  );
}

export function deleteRun(runId: string, signal?: AbortSignal): Promise<void> {
  return request("DELETE", runPath(runId), { signal }, async () => undefined);
}

/**
 * Records the human decision. Returns the updated run when the service answers with a
 * RunRecord, otherwise null (the caller then reloads the run).
 */
export function recordDecision(
  runId: string,
  decision: HumanDecision,
  signal?: AbortSignal,
): Promise<RunRecord | null> {
  return request("POST", `${runPath(runId)}/decision`, { body: { decision }, signal }, async (response) => {
    const text = await response.text();
    if (!text.trim()) return null;
    try {
      const value: unknown = JSON.parse(text);
      return isRunRecord(value) ? value : null;
    } catch {
      return null;
    }
  });
}

export interface ProposalFile {
  blob: Blob;
  filename: string;
}

export function fetchProposal(runId: string, signal?: AbortSignal): Promise<ProposalFile> {
  return request(
    "GET",
    `${runPath(runId)}/proposal`,
    { signal, timeoutMs: DOWNLOAD_TIMEOUT_MS, accept: "text/x-python, text/plain;q=0.9, */*;q=0.1" },
    async (response) => ({
      blob: await response.blob(),
      filename:
        filenameFromContentDisposition(response.headers.get("Content-Disposition")) ??
        defaultProposalFilename(runId),
    }),
  );
}

export function defaultProposalFilename(runId: string): string {
  const safe = runId.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 32);
  return safe ? `proposal-${safe}.py` : "proposal.py";
}

/** Removes path parts and characters that are unsafe in file names. */
export function sanitizeFilename(name: string): string | null {
  const base = name.split(/[\\/]/).pop() ?? "";
  // eslint-disable-next-line no-control-regex
  const cleaned = base.replace(/[\u0000-\u001f\u007f<>:"|?*]/g, "").trim();
  if (!cleaned || cleaned === "." || cleaned === "..") return null;
  return cleaned.slice(0, 120);
}

/** Reads filename* (RFC 5987) or filename from a Content-Disposition header. */
export function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  const extended = /filename\*\s*=\s*([^']*)'[^']*'([^;]+)/i.exec(header);
  if (extended?.[2]) {
    try {
      const decoded = decodeURIComponent(extended[2].trim().replace(/^"|"$/g, ""));
      const safe = sanitizeFilename(decoded);
      if (safe) return safe;
    } catch {
      // Fall through to the plain parameter.
    }
  }
  const quoted = /filename\s*=\s*"((?:[^"\\]|\\.)*)"/i.exec(header);
  if (quoted?.[1] !== undefined) return sanitizeFilename(quoted[1].replace(/\\(.)/g, "$1"));
  const plain = /filename\s*=\s*([^;\s]+)/i.exec(header);
  if (plain?.[1]) return sanitizeFilename(plain[1]);
  return null;
}
