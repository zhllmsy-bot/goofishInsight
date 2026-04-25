import type { RuntimeActionRequest, RuntimeActionResult, RuntimeStatus } from '../types/runtime';
import {
  runtimeActionRequestSchema,
  runtimeActionResultSchema,
  runtimeStatusSchema,
} from './runtimeSchemas';
import { dashboardApiUrl } from '../../../shared/lib/dashboardApiConfig';
import { fetchJson } from '../../../shared/lib/fetchJson';

export async function fetchRuntimeStatus(
  params: { categoryCode?: string | null } = {},
  signal?: AbortSignal,
): Promise<RuntimeStatus> {
  const url = new URL(dashboardApiUrl('/api/dashboard/runtime/status'), window.location.origin);
  if (params.categoryCode) {
    url.searchParams.set('category_code', params.categoryCode);
  }
  return runtimeStatusSchema.parse(
    await fetchJson(url.toString(), {
      errorPrefix: '/api/dashboard/runtime/status',
      signal,
    }),
  );
}

export async function postRuntimeAction(
  request: RuntimeActionRequest,
  signal?: AbortSignal,
): Promise<RuntimeActionResult> {
  const payload = runtimeActionRequestSchema.parse(request);
  return runtimeActionResultSchema.parse(
    await fetchJson(dashboardApiUrl('/api/dashboard/runtime/actions'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      errorPrefix: `/api/dashboard/runtime/actions:${payload.action}`,
      signal,
    }),
  );
}

export function runtimeStatusQueryKey() {
  return ['runtime', 'status'] as const;
}

export function runtimeStatusScopedQueryKey(categoryCode?: string | null) {
  return [...runtimeStatusQueryKey(), categoryCode ?? 'all'] as const;
}
