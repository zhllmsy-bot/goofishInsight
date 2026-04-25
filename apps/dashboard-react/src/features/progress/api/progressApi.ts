import { dashboardApiUrl } from '../../../shared/lib/dashboardApiConfig';
import { applyWorkspaceQueryToParams, type WorkspaceQueryInput } from '../../dashboard/lib/urlState';
import { fetchJson } from '../../../shared/lib/fetchJson';
import {
  progressAuditsSectionSchema,
  progressHeaderSchema,
  progressOverviewSectionSchema,
  progressUsageWorkersSectionSchema,
} from './progressSchemas';

export async function fetchProgressHeader(query: WorkspaceQueryInput, signal?: AbortSignal) {
  const url = dashboardApiUrl('/api/progress/sections/header');
  applyWorkspaceQueryToParams(url.searchParams, query);
  return progressHeaderSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/progress/sections/header',
      signal,
    }),
  );
}

export async function fetchProgressOverview(query: WorkspaceQueryInput, signal?: AbortSignal) {
  const url = dashboardApiUrl('/api/progress/sections/overview');
  applyWorkspaceQueryToParams(url.searchParams, query);
  return progressOverviewSectionSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/progress/sections/overview',
      signal,
    }),
  );
}

export async function fetchProgressUsageWorkers(query: WorkspaceQueryInput, signal?: AbortSignal) {
  const url = dashboardApiUrl('/api/progress/sections/usage-workers');
  applyWorkspaceQueryToParams(url.searchParams, query);
  return progressUsageWorkersSectionSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/progress/sections/usage-workers',
      signal,
    }),
  );
}

export async function fetchProgressAudits(query: WorkspaceQueryInput, signal?: AbortSignal) {
  const url = dashboardApiUrl('/api/progress/sections/audits');
  applyWorkspaceQueryToParams(url.searchParams, query);
  return progressAuditsSectionSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/progress/sections/audits',
      signal,
    }),
  );
}

export function progressHeaderQueryKey(categoryCode: string) {
  return ['progress', 'header', categoryCode] as const;
}

export function progressOverviewQueryKey(categoryCode: string) {
  return ['progress', 'overview', categoryCode] as const;
}

export function progressUsageWorkersQueryKey(categoryCode: string) {
  return ['progress', 'usage-workers', categoryCode] as const;
}

export function progressAuditsQueryKey(categoryCode: string) {
  return ['progress', 'audits', categoryCode] as const;
}
