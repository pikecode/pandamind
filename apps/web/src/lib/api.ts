/**
 * Thin fetch wrapper.
 *
 * - Reads X-Trace-Id / X-Stream-Id response headers for debugging.
 * - Throws ApiError on non-2xx; envelope shape is { code, message, details, traceId }.
 */
export interface ApiErrorPayload {
  code: string;
  message: string;
  details?: unknown;
  traceId: string;
}

export class ApiError extends Error {
  constructor(public readonly payload: ApiErrorPayload, public readonly status: number) {
    super(payload.message);
    this.name = 'ApiError';
  }
}

const BASE = '/api';

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('pm_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'GET',
    headers: authHeaders(),
  });
  return handle<T>(res);
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handle<T>(res);
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  return handle<T>(res);
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(BASE + path, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  return handle<T>(res);
}

async function handle<T>(res: Response): Promise<T> {
  const traceId = res.headers.get('X-Trace-Id') ?? '-';
  // For now we only log traceId; in real UI wire it to error display.
  // eslint-disable-next-line no-console
  if (!res.ok) console.debug(`[pandamind] ${res.status} trace=${traceId}`);
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  const json = text ? (JSON.parse(text) as unknown) : undefined;
  if (!res.ok) {
    const env = json as ApiErrorPayload | undefined;
    if (env && typeof env === 'object' && 'code' in env) {
      throw new ApiError(env, res.status);
    }
    throw new ApiError(
      { code: 'HTTP_ERROR', message: res.statusText, traceId },
      res.status,
    );
  }
  return json as T;
}
