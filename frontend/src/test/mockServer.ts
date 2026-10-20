/**
 * A fetch-level fake of the service for tests: requests go through the real API client
 * and are answered by registered handlers. No network or backend is used.
 */

import { type Mock, vi } from "vitest";

export interface MockRequest {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
  headers: Record<string, string>;
  signal: AbortSignal | null;
}

export type Handler = (request: MockRequest) => Response | Promise<Response>;

export function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

export function apiError(
  status: number,
  code: string,
  message: string,
  details: Array<Record<string, unknown>> | null = null,
  headers: Record<string, string> = {},
): Response {
  return json(status, { error: { code, message, details } }, headers);
}

interface Route {
  method: string;
  path: string | RegExp;
  handler: Handler;
}

export class MockServer {
  private routes: Route[] = [];
  readonly requests: MockRequest[] = [];
  readonly fetch: Mock<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>;

  constructor() {
    this.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => this.handle(input, init));
  }

  /** Registers a handler; a later registration for the same route wins. */
  on(method: string, path: string | RegExp, handler: Handler | Response | (() => Response)): this {
    const wrapped: Handler =
      handler instanceof Response
        ? () => handler.clone()
        : (handler as Handler);
    this.routes.unshift({ method: method.toUpperCase(), path, handler: wrapped });
    return this;
  }

  /** Answers with JSON 200 (a fresh Response for every call). */
  onJson(method: string, path: string | RegExp, body: unknown | (() => unknown), status = 200): this {
    return this.on(method, path, () => json(status, typeof body === "function" ? (body as () => unknown)() : body));
  }

  install(): this {
    vi.stubGlobal("fetch", this.fetch);
    return this;
  }

  calls(method: string, path: string | RegExp): MockRequest[] {
    return this.requests.filter(
      (request) =>
        request.method === method.toUpperCase() &&
        (typeof path === "string" ? request.path === path : path.test(request.path)),
    );
  }

  private async handle(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
    const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://127.0.0.1:5173");
    const method = (init?.method ?? "GET").toUpperCase();
    const headers: Record<string, string> = {};
    new Headers(init?.headers).forEach((value, key) => {
      headers[key] = value;
    });
    let body: unknown = undefined;
    if (typeof init?.body === "string") {
      try {
        body = JSON.parse(init.body);
      } catch {
        body = init.body;
      }
    }
    const request: MockRequest = {
      method,
      path: url.pathname,
      query: url.searchParams,
      body,
      headers,
      signal: init?.signal ?? null,
    };
    this.requests.push(request);
    if (request.signal?.aborted) throw new DOMException("The operation was aborted.", "AbortError");
    const route = this.routes.find(
      (candidate) =>
        candidate.method === method &&
        (typeof candidate.path === "string" ? candidate.path === url.pathname : candidate.path.test(url.pathname)),
    );
    if (!route) return apiError(404, "not_found", `No mock for ${method} ${url.pathname}`);
    return route.handler(request);
  }
}
