import { resolveDashboardApiConfig } from './dashboardApiConfig';

export class DashboardApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(
    message: string,
    status: number,
    payload: unknown,
  ) {
    super(message);
    this.name = 'DashboardApiError';
    this.status = status;
    this.payload = payload;
  }
}

export interface FetchJsonInit extends RequestInit {
  errorPrefix?: string;
  timeoutMs?: number;
}

function parseJsonSafely(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function extractErrorMessage(label: string, status: number, payload: unknown): string {
  if (payload && typeof payload === 'object' && !Array.isArray(payload)) {
    const data = payload as Record<string, unknown>;
    if (typeof data.detail === 'string' && data.detail.trim()) {
      return data.detail;
    }
    if (typeof data.message === 'string' && data.message.trim()) {
      return data.message;
    }
  }
  if (typeof payload === 'string' && payload.trim()) {
    return payload;
  }
  return `${label} 返回 ${status}`;
}

function extractNetworkMessage(label: string, error: unknown): string {
  if (error instanceof Error && error.message.trim()) {
    return `${label} 请求失败：${error.message}`;
  }
  return `${label} 请求失败`;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export async function fetchJson<T>(input: RequestInfo | URL, init: FetchJsonInit = {}): Promise<T> {
  const {
    errorPrefix = typeof input === 'string' ? input : 'dashboard api',
    timeoutMs = resolveDashboardApiConfig().requestTimeoutMs,
    signal,
    headers: rawHeaders,
    ...requestInit
  } = init;

  const controller = new AbortController();
  const headers = new Headers(rawHeaders);
  let didTimeout = false;

  if (!headers.has('Accept')) {
    headers.set('Accept', 'application/json');
  }

  const abortFromCaller = () => controller.abort(signal?.reason);
  if (signal?.aborted) {
    abortFromCaller();
  } else {
    signal?.addEventListener('abort', abortFromCaller, { once: true });
  }

  const timeoutId = globalThis.setTimeout(() => {
    didTimeout = true;
    controller.abort();
  }, timeoutMs);

  try {
    const response = await fetch(input, {
      ...requestInit,
      headers,
      signal: controller.signal,
    });
    const text = await response.text();
    const payload = text ? parseJsonSafely(text) : null;

    if (!response.ok) {
      throw new DashboardApiError(
        extractErrorMessage(errorPrefix, response.status, payload),
        response.status,
        payload,
      );
    }

    return payload as T;
  } catch (error) {
    if (didTimeout) {
      throw new Error(`${errorPrefix} 请求超时（${timeoutMs}ms）`);
    }
    if (isAbortError(error)) {
      throw error;
    }
    if (error instanceof DashboardApiError) {
      throw error;
    }
    throw new Error(extractNetworkMessage(errorPrefix, error));
  } finally {
    globalThis.clearTimeout(timeoutId);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}
