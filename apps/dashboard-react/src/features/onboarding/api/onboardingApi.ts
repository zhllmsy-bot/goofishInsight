import { dashboardApiUrl } from '../../../shared/lib/dashboardApiConfig';
import { fetchJson } from '../../../shared/lib/fetchJson';
import {
  onboardingCoverageSchema,
  onboardingDiscoverySchema,
  onboardingDraftSchema,
  onboardingPersistResultSchema,
  onboardingQueueMutationSchema,
  onboardingQueueSchema,
} from './onboardingSchemas';

export type OnboardingFilters = {
  operatorId: string;
  sourceKeyword: string;
  taskKey: string;
  businessDomain: string;
  profileKey: string;
  discoveryPages: number;
  status: string;
  itemScanLimit: number;
  includeClosed: boolean;
};

export type OnboardingQueueItem = Awaited<ReturnType<typeof fetchOnboardingQueue>>['items'][number];

export async function fetchOnboardingCoverage(filters: OnboardingFilters, signal?: AbortSignal) {
  const url = dashboardApiUrl('/api/onboarding/xianyu/coverage');
  if (filters.sourceKeyword) {
    url.searchParams.set('source_keyword', filters.sourceKeyword);
  }
  if (filters.businessDomain) {
    url.searchParams.set('business_domain', filters.businessDomain);
  }
  url.searchParams.set('item_scan_limit', String(filters.itemScanLimit));
  return onboardingCoverageSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/onboarding/xianyu/coverage',
      signal,
    }),
  );
}

export async function fetchOnboardingQueue(filters: OnboardingFilters, signal?: AbortSignal) {
  const url = dashboardApiUrl('/api/onboarding/xianyu/queue');
  if (filters.status) {
    url.searchParams.set('status', filters.status);
  }
  if (filters.includeClosed) {
    url.searchParams.set('include_closed', 'true');
  }
  url.searchParams.set('limit', '80');
  return onboardingQueueSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/onboarding/xianyu/queue',
      signal,
    }),
  );
}

export async function postOnboardingDiscovery(filters: OnboardingFilters, signal?: AbortSignal) {
  return onboardingDiscoverySchema.parse(
    await fetchJson(dashboardApiUrl('/api/onboarding/xianyu/discovery'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sourceKeyword: filters.sourceKeyword,
        taskKey: filters.taskKey || null,
        businessDomain: filters.businessDomain || null,
        pages: Math.max(1, Number(filters.discoveryPages || 1)),
        profileKey: filters.profileKey || 'default',
        loginWaitSeconds: 180,
      }),
      errorPrefix: '/api/onboarding/xianyu/discovery',
      signal,
    }),
  );
}

export async function postOnboardingQueueSync(filters: OnboardingFilters, signal?: AbortSignal) {
  return onboardingQueueMutationSchema.parse(
    await fetchJson(dashboardApiUrl('/api/onboarding/xianyu/queue/sync'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        operatorId: filters.operatorId,
        sourceKeyword: filters.sourceKeyword || null,
        businessDomain: filters.businessDomain || null,
        itemScanLimit: filters.itemScanLimit,
        apply: true,
      }),
      errorPrefix: '/api/onboarding/xianyu/queue/sync',
      signal,
    }),
  );
}

export async function postOnboardingQueueStatus(
  input: {
    operatorId: string;
    queueId: string | null | undefined;
    status: string;
    statusNote?: string | null;
  },
  signal?: AbortSignal,
) {
  return onboardingQueueMutationSchema.parse(
    await fetchJson(dashboardApiUrl('/api/onboarding/xianyu/queue/status'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        operatorId: input.operatorId,
        status: input.status,
        queueId: input.queueId ?? null,
        statusNote: input.statusNote ?? null,
        apply: true,
      }),
      errorPrefix: '/api/onboarding/xianyu/queue/status',
      signal,
    }),
  );
}

export async function postOnboardingDraft(
  filters: OnboardingFilters,
  item: OnboardingQueueItem,
  signal?: AbortSignal,
) {
  return onboardingDraftSchema.parse(
    await fetchJson(dashboardApiUrl('/api/onboarding/xianyu/draft'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sourceKeyword: filters.sourceKeyword || item.sampleTitles[0] || null,
        businessDomain: filters.businessDomain || item.businessDomains[0] || null,
        xianyuCatId: item.xianyuCatId ?? null,
        xianyuTbCatId: item.xianyuTbCatId ?? null,
        xianyuCCatId: item.xianyuCCatId ?? null,
        sampleLimit: 25,
        preferUnmapped: false,
      }),
      errorPrefix: '/api/onboarding/xianyu/draft',
      signal,
    }),
  );
}

export async function postOnboardingPersist(
  input: {
    operatorId: string;
    payload: Record<string, unknown>;
    apply: boolean;
  },
  signal?: AbortSignal,
) {
  return onboardingPersistResultSchema.parse(
    await fetchJson(dashboardApiUrl('/api/onboarding/xianyu/persist'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        operatorId: input.operatorId,
        payload: input.payload,
        apply: input.apply,
      }),
      errorPrefix: '/api/onboarding/xianyu/persist',
      signal,
    }),
  );
}
