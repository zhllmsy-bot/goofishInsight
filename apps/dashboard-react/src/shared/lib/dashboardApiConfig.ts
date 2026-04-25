export type DashboardApiMode = 'fastapi' | 'bff';

export interface DashboardApiConfig {
  apiMode: DashboardApiMode;
  apiOrigin: string;
  legacyOrigin: string;
  requestTimeoutMs: number;
}

const DEFAULT_FASTAPI_ORIGIN = 'http://127.0.0.1:8791';
const DEFAULT_BFF_ORIGIN = 'http://127.0.0.1:8787';
const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

export const DASHBOARD_API_CONFIG_HELP =
  'VITE_DASHBOARD_API_MODE=fastapi 使用 VITE_FASTAPI_ORIGIN；VITE_DASHBOARD_API_MODE=bff 使用 VITE_BFF_ORIGIN 或当前页面 origin；VITE_LEGACY_ORIGIN 可单独覆盖旧版页面链接。';

function normalizeOrigin(value: string | undefined): string | null {
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

function resolveApiMode(value: string | undefined): DashboardApiMode {
  return value?.trim().toLowerCase() === 'bff' ? 'bff' : 'fastapi';
}

function resolveBrowserOrigin(): string {
  if (typeof window === 'undefined') {
    return DEFAULT_BFF_ORIGIN;
  }
  return window.location.origin;
}

export function resolveDashboardApiConfig(): DashboardApiConfig {
  const apiMode = resolveApiMode(import.meta.env.VITE_DASHBOARD_API_MODE);
  const fastapiOrigin = normalizeOrigin(import.meta.env.VITE_FASTAPI_ORIGIN) ?? DEFAULT_FASTAPI_ORIGIN;
  const apiOrigin =
    apiMode === 'bff'
      ? normalizeOrigin(import.meta.env.VITE_BFF_ORIGIN) ?? resolveBrowserOrigin()
      : fastapiOrigin;

  return {
    apiMode,
    apiOrigin,
    legacyOrigin: normalizeOrigin(import.meta.env.VITE_LEGACY_ORIGIN) ?? fastapiOrigin,
    requestTimeoutMs: parsePositiveInt(
      import.meta.env.VITE_DASHBOARD_API_TIMEOUT_MS,
      DEFAULT_REQUEST_TIMEOUT_MS,
    ),
  };
}

export function dashboardApiUrl(path: string): URL {
  return new URL(path, resolveDashboardApiConfig().apiOrigin);
}

export function legacyDashboardLink(path: string): string {
  return new URL(path, resolveDashboardApiConfig().legacyOrigin).toString();
}
