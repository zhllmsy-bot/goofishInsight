import type { QueryState } from '../../dashboard/types/dashboard';
import type { LlmTraceDetail, LlmTraceSection, UsageWorkersSection } from '../types/llmOps';
import {
  llmTraceDetailResponseSchema,
  llmTraceSectionSchema,
} from './llmOpsSchemas';
import { dashboardApiUrl } from '../../../shared/lib/dashboardApiConfig';
import { fetchJson } from '../../../shared/lib/fetchJson';
import {
  fetchProgressUsageWorkers,
  progressUsageWorkersQueryKey,
} from '../../progress/api/progressApi';

export async function fetchLlmTraceSection(signal?: AbortSignal): Promise<LlmTraceSection> {
  return llmTraceSectionSchema.parse(
    await fetchJson(dashboardApiUrl('/api/dashboard/sections/llm-traces'), {
      errorPrefix: '/api/dashboard/sections/llm-traces',
      signal,
    }),
  );
}

export async function fetchLlmTraceDetail(traceKey: string, signal?: AbortSignal): Promise<LlmTraceDetail | null> {
  const data = await fetchJson(
    dashboardApiUrl(`/api/dashboard/llm-traces/${encodeURIComponent(traceKey)}`),
    {
      errorPrefix: `/api/dashboard/llm-traces/${traceKey}`,
      signal,
    },
  );
  return llmTraceDetailResponseSchema.parse(data).trace;
}

export async function fetchUsageWorkersSection(
  query: Pick<QueryState, 'categoryCode'>,
  signal?: AbortSignal,
): Promise<UsageWorkersSection> {
  return fetchProgressUsageWorkers({ categoryCode: query.categoryCode }, signal);
}

export function llmTraceSectionQueryKey() {
  return ['llm-ops', 'trace-section'] as const;
}

export function llmTraceDetailQueryKey(traceKey: string) {
  return ['llm-ops', 'trace-detail', traceKey] as const;
}

export function usageWorkersSectionQueryKey(categoryCode: string) {
  return progressUsageWorkersQueryKey(categoryCode);
}
