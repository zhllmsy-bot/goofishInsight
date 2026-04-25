import { useQuery } from '@tanstack/react-query';

import {
  fetchProgressAudits,
  fetchProgressHeader,
  fetchProgressOverview,
  fetchProgressUsageWorkers,
  progressAuditsQueryKey,
  progressHeaderQueryKey,
  progressOverviewQueryKey,
  progressUsageWorkersQueryKey,
} from '../api/progressApi';
import { errorMessage } from '../../dashboard/lib/formatters';
import type { QueryState } from '../../dashboard/types/dashboard';

const PROGRESS_STALE_TIME = 5_000;
const USAGE_STALE_TIME = 10_000;

export function useProgressPage(query: QueryState) {
  const headerQuery = useQuery({
    queryKey: progressHeaderQueryKey(query.categoryCode),
    queryFn: ({ signal }) => fetchProgressHeader(query, signal),
    staleTime: PROGRESS_STALE_TIME,
  });
  const overviewQuery = useQuery({
    queryKey: progressOverviewQueryKey(query.categoryCode),
    queryFn: ({ signal }) => fetchProgressOverview(query, signal),
    staleTime: PROGRESS_STALE_TIME,
  });
  const usageWorkersQuery = useQuery({
    queryKey: progressUsageWorkersQueryKey(query.categoryCode),
    queryFn: ({ signal }) => fetchProgressUsageWorkers(query, signal),
    staleTime: USAGE_STALE_TIME,
  });
  const auditsQuery = useQuery({
    queryKey: progressAuditsQueryKey(query.categoryCode),
    queryFn: ({ signal }) => fetchProgressAudits(query, signal),
    staleTime: PROGRESS_STALE_TIME,
  });

  const queries = [headerQuery, overviewQuery, usageWorkersQuery, auditsQuery];
  const firstError = queries.map((queryState) => queryState.error).find(Boolean);

  return {
    header: headerQuery.data ?? null,
    overview: overviewQuery.data ?? null,
    usageWorkers: usageWorkersQuery.data ?? null,
    audits: auditsQuery.data ?? null,
    isLoading: queries.some((queryState) => queryState.isPending),
    isRefreshing: queries.some((queryState) => queryState.isRefetching),
    error: firstError ? errorMessage(firstError) : null,
  };
}
