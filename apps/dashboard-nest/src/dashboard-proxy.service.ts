import { HttpException, Injectable } from '@nestjs/common';

const DEFAULT_BACKEND_ORIGIN = 'http://127.0.0.1:8791';
const DEFAULT_BACKEND_TIMEOUT_MS = 30_000;

function normalizeOrigin(value?: string): string | null {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed.replace(/\/+$/, '') : null;
}

function parsePositiveInt(value: string | undefined, fallback: number): number {
  if (!value) {
    return fallback;
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return Math.floor(parsed);
}

@Injectable()
export class DashboardProxyService {
  private readonly backendOrigin =
    normalizeOrigin(process.env.GOOFISH_DASHBOARD_BACKEND_ORIGIN) ?? DEFAULT_BACKEND_ORIGIN;
  private readonly requestTimeoutMs = parsePositiveInt(
    process.env.GOOFISH_DASHBOARD_BACKEND_TIMEOUT_MS,
    DEFAULT_BACKEND_TIMEOUT_MS,
  );

  async forwardSection(
    section: string,
    query: Record<string, string | string[] | undefined>,
  ): Promise<unknown> {
    return this.forwardDashboardPath(`/api/dashboard/sections/${section}`, query);
  }

  async forwardRuntimeStatus(
    query: Record<string, string | string[] | undefined> = {},
  ): Promise<unknown> {
    return this.forwardDashboardPath('/api/dashboard/runtime/status', query);
  }

  async forwardAgentHarnessStatus(): Promise<unknown> {
    return this.forwardDashboardPath('/api/dashboard/agent-harness/status');
  }

  async forwardRuntimeAction(body: unknown): Promise<unknown> {
    return this.forwardDashboardPath('/api/dashboard/runtime/actions', {}, {
      body,
      method: 'POST',
    });
  }

  async forwardListingPreference(body: unknown): Promise<unknown> {
    return this.forwardDashboardPath('/api/dashboard/listing-preferences', {}, {
      body,
      method: 'POST',
    });
  }

  async forwardProgressSection(
    section: string,
    query: Record<string, string | string[] | undefined>,
  ): Promise<unknown> {
    return this.forwardDashboardPath(`/api/progress/sections/${section}`, query);
  }

  async forwardDashboardPath(
    path: string,
    query: Record<string, string | string[] | undefined> = {},
    options: {
      method?: 'GET' | 'POST';
      body?: unknown;
    } = {},
  ): Promise<unknown> {
    const url = new URL(path, this.backendOrigin);

    Object.entries(query).forEach(([key, value]) => {
      if (Array.isArray(value)) {
        value.filter(Boolean).forEach((entry) => url.searchParams.append(key, entry));
        return;
      }
      if (value) {
        url.searchParams.set(key, value);
      }
    });

    const controller = new AbortController();
    let didTimeout = false;
    const timeoutId = setTimeout(() => {
      didTimeout = true;
      controller.abort();
    }, this.requestTimeoutMs);

    let response: Response;

    try {
      response = await fetch(url, {
        method: options.method ?? 'GET',
        headers: {
          Accept: 'application/json',
          ...(options.body ? { 'Content-Type': 'application/json' } : {}),
        },
        ...(options.body ? { body: JSON.stringify(options.body) } : {}),
        signal: controller.signal,
      });
    } catch (error) {
      clearTimeout(timeoutId);
      if (didTimeout) {
        throw new HttpException(
          { message: `${path} upstream timeout after ${this.requestTimeoutMs}ms` },
          504,
        );
      }
      throw new HttpException(
        {
          message: `${path} upstream unavailable`,
          detail: error instanceof Error ? error.message : String(error),
        },
        504,
      );
    }

    clearTimeout(timeoutId);

    const text = await response.text();
    const parsed = text ? parseJsonSafely(text) : null;
    if (!response.ok) {
      throw new HttpException(parsed ?? text ?? `${path} upstream error`, response.status);
    }

    return parsed ?? {};
  }
}

function parseJsonSafely(text: string): unknown | null {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}
