/**
 * HTTP transport for the Refactor AI API.
 *
 * Everything the UI does over the network goes through `requestJson` /
 * `requestText`:
 *
 * - every response is validated against the Zod contract in `contract.ts`;
 * - every request carries a timeout and can be aborted by the caller;
 * - every error keeps the server's `X-Request-ID` so a UI action can be traced
 *   to the exact server log line that produced it (ADR16);
 * - network, timeout, contract and HTTP failures are distinct error kinds so
 *   the UI can react differently instead of showing one generic message.
 */
import type { z } from 'zod';

export type ApiErrorKind = 'http' | 'network' | 'timeout' | 'contract' | 'aborted';

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  readonly detail?: string;
  readonly requestId?: string;

  constructor(
    message: string,
    options: { kind: ApiErrorKind; status?: number; detail?: string; requestId?: string },
  ) {
    super(message);
    this.name = 'ApiError';
    this.kind = options.kind;
    this.status = options.status ?? 0;
    this.detail = options.detail;
    this.requestId = options.requestId;
  }
}

export interface RequestOptions<T> {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
  schema?: z.ZodType<T>;
}

interface TimeoutHandle {
  signal: AbortSignal;
  dispose: () => void;
}

/** Combine a caller signal with a timeout without relying on AbortSignal.any. */
function withTimeout(timeoutMs: number, external?: AbortSignal): TimeoutHandle {
  const controller = new AbortController();
  const timer = window.setTimeout(() => {
    controller.abort(new DOMException('Request timed out', 'TimeoutError'));
  }, timeoutMs);

  const onExternalAbort = () => controller.abort(external?.reason);
  if (external) {
    if (external.aborted) controller.abort(external.reason);
    else external.addEventListener('abort', onExternalAbort, { once: true });
  }

  return {
    signal: controller.signal,
    dispose: () => {
      window.clearTimeout(timer);
      external?.removeEventListener('abort', onExternalAbort);
    },
  };
}

function readRequestId(response: Response): string | undefined {
  return response.headers.get('x-request-id') ?? undefined;
}

/** Extract the human readable part of a FastAPI error body. */
function readDetail(body: unknown): string | undefined {
  if (!body || typeof body !== 'object') return undefined;
  const raw = (body as { detail?: unknown }).detail;
  if (typeof raw === 'string') return raw;
  if (Array.isArray(raw)) {
    const messages = raw
      .map((item) =>
        item && typeof item === 'object' && 'msg' in item
          ? String((item as { msg: unknown }).msg)
          : null,
      )
      .filter((message): message is string => message !== null);
    if (messages.length > 0) return messages.join('; ');
  }
  return undefined;
}

function statusMessage(status: number, detail?: string): string {
  if (detail) return detail;
  if (status === 404) return 'The requested record was not found.';
  if (status === 413) return 'The payload is too large for the API (limit 100 KB).';
  if (status === 422) return 'The request payload was rejected by the API validation.';
  if (status >= 500) return `The API failed while handling the request (HTTP ${status}).`;
  return `Request failed with status ${status}.`;
}

/** Perform a JSON request and validate the response against `schema`. */
export async function requestJson<T>(path: string, options: RequestOptions<T> = {}): Promise<T> {
  const timeout = withTimeout(options.timeoutMs ?? 30_000, options.signal);
  let response: Response;

  try {
    response = await fetch(path, {
      method: options.method ?? 'GET',
      headers: {
        Accept: 'application/json',
        ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: timeout.signal,
      cache: 'no-store',
    });
  } catch (error) {
    timeout.dispose();
    if (options.signal?.aborted) {
      throw new ApiError('The request was cancelled.', { kind: 'aborted' });
    }
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError('The API did not answer in time.', { kind: 'timeout' });
    }
    const offline = typeof navigator !== 'undefined' && navigator.onLine === false;
    throw new ApiError(
      offline
        ? 'The API is unreachable — this machine appears to be offline.'
        : 'The API is unreachable — is the server running?',
      { kind: 'network' },
    );
  }

  const requestId = readRequestId(response);

  if (!response.ok) {
    timeout.dispose();
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    const detail = readDetail(body);
    throw new ApiError(statusMessage(response.status, detail), {
      kind: 'http',
      status: response.status,
      detail,
      requestId,
    });
  }

  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    timeout.dispose();
    throw new ApiError('The API returned a response that is not valid JSON.', {
      kind: 'contract',
      status: response.status,
      requestId,
    });
  }
  timeout.dispose();

  if (!options.schema) return payload as T;

  const parsed = options.schema.safeParse(payload);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    const path = issue?.path?.join('.') || '(root)';
    throw new ApiError(
      `The API response does not match the expected contract at "${path}". ` +
        'The server and the web client are out of sync.',
      { kind: 'contract', status: response.status, detail: issue?.message, requestId },
    );
  }
  return parsed.data;
}

/** Perform a request and return the raw text body (used for the Markdown report). */
export async function requestText(path: string, options: Omit<RequestOptions<never>, 'schema'> = {}) {
  const timeout = withTimeout(options.timeoutMs ?? 30_000, options.signal);
  let response: Response;

  try {
    response = await fetch(path, {
      method: options.method ?? 'GET',
      headers: { Accept: 'text/markdown, text/plain' },
      signal: timeout.signal,
      cache: 'no-store',
    });
  } catch (error) {
    timeout.dispose();
    if (options.signal?.aborted) {
      throw new ApiError('The request was cancelled.', { kind: 'aborted' });
    }
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new ApiError('The API did not answer in time.', { kind: 'timeout' });
    }
    throw new ApiError('The API is unreachable — is the server running?', { kind: 'network' });
  }

  const requestId = readRequestId(response);
  if (!response.ok) {
    timeout.dispose();
    throw new ApiError(statusMessage(response.status), {
      kind: 'http',
      status: response.status,
      requestId,
    });
  }

  const text = await response.text();
  timeout.dispose();
  return text;
}

/** Extract a readable message from any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.kind === 'network') return error.message;
    if (error.kind === 'timeout') return error.message;
    if (error.kind === 'contract') return error.message;
    if (error.kind === 'aborted') return 'The request was cancelled.';
    return error.detail ? `${error.message}` : error.message;
  }
  if (error instanceof Error) return error.message;
  return 'An unexpected error occurred.';
}
