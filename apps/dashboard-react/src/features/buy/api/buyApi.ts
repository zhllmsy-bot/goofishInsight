import type {
  BuyFeedbackCalibrationApplyRequest,
  BuyFeedbackCalibrationApplyResponse,
  BuyFeedbackRequest,
  BuyFeedbackResponse,
  BuyDataValueReport,
  BuyOpportunityDetail,
  BuyBaselineList,
  BuyWatchTargetList,
  BuyWorkbench,
} from '../types/buy';
import { dashboardApiUrl } from '../../../shared/lib/dashboardApiConfig';
import { fetchJson } from '../../../shared/lib/fetchJson';
import {
  buyBaselineListSchema,
  buyDataValueReportSchema,
  buyFeedbackCalibrationApplyResponseSchema,
  buyFeedbackResponseSchema,
  buyOpportunityDetailSchema,
  buyWatchTargetListSchema,
  buyWorkbenchSchema,
} from './buySchemas';

export async function fetchBuyWorkbench(
  params: {
    categoryCode?: string;
    limit?: number;
  },
  signal?: AbortSignal,
): Promise<BuyWorkbench> {
  const url = buildApiUrl('/api/buy/opportunities');
  if (params.categoryCode) {
    url.searchParams.set('category_code', params.categoryCode);
  }
  if (params.limit) {
    url.searchParams.set('limit', String(params.limit));
  }

  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(`/api/buy/opportunities 返回 ${response.status}`);
  }

  return buyWorkbenchSchema.parse(await response.json());
}

export async function fetchBuyDataValue(
  params: {
    categoryCode?: string;
  },
  signal?: AbortSignal,
): Promise<BuyDataValueReport> {
  const url = buildApiUrl('/api/buy/data-value');
  if (params.categoryCode) {
    url.searchParams.set('category_code', params.categoryCode);
  }

  return buyDataValueReportSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/buy/data-value',
      signal,
    }),
  );
}

export async function fetchBuyTargets(
  params: {
    categoryCode?: string;
    status?: string;
    limit?: number;
  },
  signal?: AbortSignal,
): Promise<BuyWatchTargetList> {
  const url = buildApiUrl('/api/buy/targets');
  if (params.categoryCode) {
    url.searchParams.set('category_code', params.categoryCode);
  }
  if (params.status) {
    url.searchParams.set('status', params.status);
  }
  if (params.limit) {
    url.searchParams.set('limit', String(params.limit));
  }

  return buyWatchTargetListSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/buy/targets',
      signal,
    }),
  );
}

export async function fetchBuyBaselines(
  params: {
    categoryCode?: string;
    baselineDate?: string;
    limit?: number;
  },
  signal?: AbortSignal,
): Promise<BuyBaselineList> {
  const url = buildApiUrl('/api/buy/baselines');
  if (params.categoryCode) {
    url.searchParams.set('category_code', params.categoryCode);
  }
  if (params.baselineDate) {
    url.searchParams.set('baseline_date', params.baselineDate);
  }
  if (params.limit) {
    url.searchParams.set('limit', String(params.limit));
  }

  return buyBaselineListSchema.parse(
    await fetchJson(url, {
      errorPrefix: '/api/buy/baselines',
      signal,
    }),
  );
}

export async function postBuyFeedback(
  payload: BuyFeedbackRequest,
  signal?: AbortSignal,
): Promise<BuyFeedbackResponse> {
  const response = await fetch(buildApiUrl('/api/buy/feedback'), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      opportunityId: payload.opportunityId,
      feedbackLabel: payload.feedbackLabel,
      feedbackType: payload.feedbackType ?? 'decision',
      operatorId: payload.operatorId,
      feedbackNote: payload.feedbackNote,
      purchasePrice: payload.purchasePrice,
      expectedResalePrice: payload.expectedResalePrice,
      linkToAlertCandidate: payload.linkToAlertCandidate ?? false,
    }),
    signal,
  });

  const text = await response.text();
  const json = parseJsonSafely(text);
  if (!response.ok) {
    const detail = json && typeof json === 'object'
      ? 'detail' in json
        ? String(json.detail)
        : 'message' in json
          ? String(json.message)
          : `HTTP ${response.status}`
      : `HTTP ${response.status}`;
    throw new Error(detail);
  }

  return buyFeedbackResponseSchema.parse(json);
}

export async function applyBuyFeedbackCalibration(
  payload: BuyFeedbackCalibrationApplyRequest,
  signal?: AbortSignal,
): Promise<BuyFeedbackCalibrationApplyResponse> {
  const response = await fetch(buildApiUrl('/api/buy/feedback-calibration/apply'), {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      categoryCode: payload.categoryCode,
      windowDays: payload.windowDays ?? 30,
      operatorId: payload.operatorId,
      recommendationIds: payload.recommendationIds,
    }),
    signal,
  });

  const text = await response.text();
  const json = parseJsonSafely(text);
  if (!response.ok) {
    const detail = json && typeof json === 'object'
      ? 'detail' in json
        ? String(json.detail)
        : 'message' in json
          ? String(json.message)
          : `HTTP ${response.status}`
      : `HTTP ${response.status}`;
    throw new Error(detail);
  }

  return buyFeedbackCalibrationApplyResponseSchema.parse(json);
}

export async function fetchBuyOpportunityDetail(
  opportunityId: string,
  params: {
    categoryCode?: string;
  },
  signal?: AbortSignal,
): Promise<BuyOpportunityDetail> {
  const url = buildApiUrl(`/api/buy/opportunities/${encodeURIComponent(opportunityId)}`);
  if (params.categoryCode) {
    url.searchParams.set('category_code', params.categoryCode);
  }

  return buyOpportunityDetailSchema.parse(
    await fetchJson(url, {
      errorPrefix: `/api/buy/opportunities/${opportunityId}`,
      signal,
    }),
  );
}

export function buyWorkbenchQueryKey(categoryCode: string, limit: number) {
  return ['buy', 'workbench', categoryCode, limit] as const;
}

export function buyDataValueQueryKey(categoryCode: string) {
  return ['buy', 'data-value', categoryCode] as const;
}

export function buyOpportunityDetailQueryKey(opportunityId: string, categoryCode: string) {
  return ['buy', 'opportunity-detail', opportunityId, categoryCode] as const;
}

export function buyTargetsQueryKey(categoryCode: string, limit: number, status?: string) {
  return ['buy', 'targets', categoryCode, limit, status ?? null] as const;
}

export function buyBaselinesQueryKey(categoryCode: string, baselineDate: string | undefined, limit: number) {
  return ['buy', 'baselines', categoryCode, baselineDate ?? null, limit] as const;
}

function parseJsonSafely(text: string): unknown {
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

function buildApiUrl(path: string): URL {
  return dashboardApiUrl(path);
}
