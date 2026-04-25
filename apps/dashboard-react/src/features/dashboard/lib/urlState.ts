import type { QueryState } from '../types/dashboard';

export type WorkspaceQueryInput = Partial<QueryState>;

export const DEFAULT_QUERY_STATE: QueryState = {
  categoryCode: 'apple_computer',
  productLabel: '',
  specLabel: '',
  display_type: '',
  case_size_mm: '',
  is_solar: '',
  chip_family: '',
  screen_size_in: '',
  memory_gb: '',
  storage_gb: '',
  pricingScope: 'all',
  pricingFreshnessDays: '30',
};

export function readInitialQuery(search = getCurrentSearch()): QueryState {
  const params = new URLSearchParams(search);
  return {
    categoryCode: params.get('category_code') ?? DEFAULT_QUERY_STATE.categoryCode,
    productLabel: params.get('product_label') ?? DEFAULT_QUERY_STATE.productLabel,
    specLabel: params.get('spec_label') ?? DEFAULT_QUERY_STATE.specLabel,
    display_type: params.get('display_type') ?? DEFAULT_QUERY_STATE.display_type,
    case_size_mm: params.get('case_size_mm') ?? DEFAULT_QUERY_STATE.case_size_mm,
    is_solar: params.get('is_solar') ?? DEFAULT_QUERY_STATE.is_solar,
    chip_family: params.get('chip_family') ?? DEFAULT_QUERY_STATE.chip_family,
    screen_size_in: params.get('screen_size_in') ?? DEFAULT_QUERY_STATE.screen_size_in,
    memory_gb: params.get('memory_gb') ?? DEFAULT_QUERY_STATE.memory_gb,
    storage_gb: params.get('storage_gb') ?? DEFAULT_QUERY_STATE.storage_gb,
    pricingScope: params.get('pricing_scope') === 'actionable' ? 'actionable' : DEFAULT_QUERY_STATE.pricingScope,
    pricingFreshnessDays: params.get('pricing_freshness_days') ?? DEFAULT_QUERY_STATE.pricingFreshnessDays,
  };
}

export function buildWorkspaceSearch(query: QueryState): string {
  const params = new URLSearchParams();
  applyWorkspaceQueryToParams(params, query);
  const search = params.toString();
  return search ? `?${search}` : '';
}

export function buildWorkspacePath(pathname: string, query: QueryState): string {
  const search = buildWorkspaceSearch(query);
  return search ? `${pathname}${search}` : pathname;
}

export function buildWorkspaceLocation(pathname: string, query: QueryState): {
  pathname: string;
  search?: string;
} {
  const search = buildWorkspaceSearch(query);
  return search ? { pathname, search } : { pathname };
}

export function syncQueryToUrl(query: QueryState): void {
  if (typeof window === 'undefined') {
    return;
  }

  const url = new URL(window.location.href);
  applyWorkspaceQueryToParams(url.searchParams, query);
  const nextSearch = url.searchParams.toString();
  window.history.replaceState({}, '', nextSearch ? `${url.pathname}?${nextSearch}` : url.pathname);
}

export function setSearchParam(params: URLSearchParams, key: string, value: string): void {
  if (!value) {
    params.delete(key);
    return;
  }

  params.set(key, value);
}

export function applyWorkspaceQueryToParams(params: URLSearchParams, query: WorkspaceQueryInput): void {
  setSearchParam(params, 'category_code', query.categoryCode ?? '');
  setSearchParam(params, 'product_label', query.productLabel ?? '');
  setSearchParam(params, 'spec_label', query.specLabel ?? '');
  setSearchParam(params, 'display_type', query.display_type ?? '');
  setSearchParam(params, 'case_size_mm', query.case_size_mm ?? '');
  setSearchParam(params, 'is_solar', query.is_solar ?? '');
  setSearchParam(params, 'chip_family', query.chip_family ?? '');
  setSearchParam(params, 'screen_size_in', query.screen_size_in ?? '');
  setSearchParam(params, 'memory_gb', query.memory_gb ?? '');
  setSearchParam(params, 'storage_gb', query.storage_gb ?? '');
  setSearchParam(params, 'pricing_scope', query.pricingScope ?? '');
  setSearchParam(params, 'pricing_freshness_days', query.pricingFreshnessDays ?? '');
}

function getCurrentSearch(): string {
  if (typeof window === 'undefined') {
    return '';
  }
  return window.location.search;
}
