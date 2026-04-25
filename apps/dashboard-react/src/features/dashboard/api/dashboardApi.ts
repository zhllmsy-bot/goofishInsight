import type { DashboardSectionMap, DashboardSectionName, QueryState } from '../types/dashboard';
import { dashboardSectionSchemas } from './dashboardSchemas';
import { applyWorkspaceQueryToParams } from '../lib/urlState';
import { dashboardApiUrl } from '../../../shared/lib/dashboardApiConfig';
import { fetchJson } from '../../../shared/lib/fetchJson';

export type ListingPreferenceValue = 'interested' | 'not_interested';

const SECTION_PATHS: Record<DashboardSectionName, string> = {
  hero: '/api/dashboard/sections/hero',
  filters: '/api/dashboard/sections/filters',
  pricing: '/api/dashboard/sections/pricing',
  items: '/api/dashboard/sections/items',
  focus: '/api/dashboard/sections/focus',
  insights: '/api/dashboard/sections/insights',
  calibration: '/api/dashboard/sections/calibration',
};

export async function fetchDashboardSection<TSection extends DashboardSectionName>(
  section: TSection,
  query: QueryState,
  signal?: AbortSignal,
): Promise<DashboardSectionMap[TSection]> {
  const data = await fetchJson(buildSectionUrl(SECTION_PATHS[section], query), {
    errorPrefix: SECTION_PATHS[section],
    signal,
  });
  return dashboardSectionSchemas[section].parse(data) as DashboardSectionMap[TSection];
}

export function dashboardSectionQueryKey(section: DashboardSectionName, query: QueryState) {
  return [
    'dashboard',
    'section',
    section,
    query.categoryCode,
    query.productLabel,
    query.specLabel,
    query.display_type,
    query.case_size_mm,
    query.is_solar,
    query.chip_family,
    query.screen_size_in,
    query.memory_gb,
    query.storage_gb,
    query.pricingScope,
    query.pricingFreshnessDays,
  ] as const;
}

export async function postListingPreference(
  payload: {
    itemId: string;
    preference: ListingPreferenceValue;
    reason?: string;
  },
  signal?: AbortSignal,
): Promise<void> {
  await fetchJson(dashboardApiUrl('/api/dashboard/listing-preferences'), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      item_id: payload.itemId,
      preference: payload.preference,
      reason: payload.reason,
    }),
    errorPrefix: '/api/dashboard/listing-preferences',
    signal,
  });
}

function buildSectionUrl(path: string, query: QueryState): URL {
  const url = dashboardApiUrl(path);
  applyWorkspaceQueryToParams(url.searchParams, query);
  return url;
}
