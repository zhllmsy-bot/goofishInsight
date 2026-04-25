import { useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';

import { dashboardSectionQueryKey, fetchDashboardSection } from '../api/dashboardApi';
import { DASHBOARD_QUERY_STALE_TIME } from '../lib/constants';
import { errorMessage } from '../lib/formatters';
import { extractProductOptions, extractTemplateFilterFields, getFilterField } from '../lib/selectors';
import { syncQueryToUrl } from '../lib/urlState';
import type {
  DashboardPrimaryState,
  DashboardReferenceState,
  FilterField,
  ListingGroup,
  PricingRow,
  QueryState,
} from '../types/dashboard';
import { buildListingGroups } from '../lib/selectors';

export function useDashboardUrlSync(query: QueryState): void {
  useEffect(() => {
    syncQueryToUrl(query);
  }, [query]);
}

export function useDashboardPrimaryState(query: QueryState): DashboardPrimaryState {
  const hasSelectedCombination = Boolean(query.productLabel);
  const heroQuery = useQuery({
    queryKey: dashboardSectionQueryKey('hero', query),
    queryFn: ({ signal }) => fetchDashboardSection('hero', query, signal),
    placeholderData: keepPreviousData,
    staleTime: DASHBOARD_QUERY_STALE_TIME,
  });

  const filtersQuery = useQuery({
    queryKey: dashboardSectionQueryKey('filters', query),
    queryFn: ({ signal }) => fetchDashboardSection('filters', query, signal),
    placeholderData: keepPreviousData,
    staleTime: DASHBOARD_QUERY_STALE_TIME,
  });

  const pricingQuery = useQuery({
    queryKey: dashboardSectionQueryKey('pricing', query),
    queryFn: ({ signal }) => fetchDashboardSection('pricing', query, signal),
    enabled: hasSelectedCombination,
    placeholderData: keepPreviousData,
    staleTime: DASHBOARD_QUERY_STALE_TIME,
  });

  const itemsQuery = useQuery({
    queryKey: dashboardSectionQueryKey('items', query),
    queryFn: ({ signal }) => fetchDashboardSection('items', query, signal),
    enabled: hasSelectedCombination,
    placeholderData: keepPreviousData,
    staleTime: DASHBOARD_QUERY_STALE_TIME,
  });

  const focusQuery = useQuery({
    queryKey: dashboardSectionQueryKey('focus', query),
    queryFn: ({ signal }) => fetchDashboardSection('focus', query, signal),
    placeholderData: keepPreviousData,
    staleTime: DASHBOARD_QUERY_STALE_TIME,
  });

  const activeQueries = hasSelectedCombination
    ? [heroQuery, filtersQuery, pricingQuery, itemsQuery, focusQuery]
    : [heroQuery, filtersQuery, focusQuery];
  const firstError = activeQueries.map((queryState) => queryState.error).find(Boolean);

  return {
    hero: heroQuery.data ?? null,
    filters: filtersQuery.data ?? null,
    pricing: pricingQuery.data ?? null,
    items: itemsQuery.data ?? null,
    focus: focusQuery.data ?? null,
    loading: activeQueries.some((queryState) => queryState.isPending),
    error: firstError ? errorMessage(firstError) : null,
  };
}

export function useDashboardReferenceState(query: QueryState): DashboardReferenceState {
  const hasSelectedCombination = Boolean(query.productLabel);
  const insightsQuery = useQuery({
    queryKey: dashboardSectionQueryKey('insights', query),
    queryFn: ({ signal }) => fetchDashboardSection('insights', query, signal),
    enabled: hasSelectedCombination,
    placeholderData: keepPreviousData,
    staleTime: DASHBOARD_QUERY_STALE_TIME,
  });

  const calibrationQuery = useQuery({
    queryKey: dashboardSectionQueryKey('calibration', query),
    queryFn: ({ signal }) => fetchDashboardSection('calibration', query, signal),
    enabled: hasSelectedCombination,
    placeholderData: keepPreviousData,
    staleTime: DASHBOARD_QUERY_STALE_TIME,
  });

  return {
    insights: insightsQuery.data ?? null,
    calibration: calibrationQuery.data ?? null,
  };
}

export function useDashboardDerivedState(primaryState: DashboardPrimaryState): {
  productField: ReturnType<typeof getFilterField>;
  specField: ReturnType<typeof getFilterField>;
  productOptions: ReturnType<typeof extractProductOptions>;
  templateFields: FilterField[];
  pricingRow: PricingRow | null;
  listingGroups: ListingGroup[];
} {
  const productField = getFilterField(primaryState.filters?.visible_filter_fields, 'product_label');
  const specField = getFilterField(primaryState.filters?.visible_filter_fields, 'spec_label');
  const productOptions = extractProductOptions(primaryState.filters);
  const templateFields = extractTemplateFilterFields(primaryState.filters?.visible_filter_fields);
  const rawPricingRow = primaryState.pricing?.pricing_panel?.rows?.[0] ?? null;
  const availabilityTier =
    primaryState.pricing?.pricing_availability?.availabilityTier ??
    primaryState.pricing?.pricing_panel?.selected_pricing_availability?.availabilityTier;
  const canUsePricingRow = availabilityTier ? availabilityTier === 'guidance_ready' : Boolean(rawPricingRow);
  const pricingRow = canUsePricingRow ? rawPricingRow : null;
  const listingGroups = useMemo(
    () => buildListingGroups(primaryState.items?.items ?? [], pricingRow),
    [primaryState.items?.items, pricingRow],
  );

  return {
    productField,
    specField,
    productOptions,
    templateFields,
    pricingRow,
    listingGroups,
  };
}

function keepPreviousData<T>(previousData: T | undefined): T | undefined {
  return previousData;
}
