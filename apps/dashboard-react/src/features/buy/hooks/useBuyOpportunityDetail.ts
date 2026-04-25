import { useQuery } from '@tanstack/react-query';

import {
  buyOpportunityDetailQueryKey,
  fetchBuyOpportunityDetail,
} from '../api/buyApi';

const BUY_OPPORTUNITY_DETAIL_STALE_TIME = 20_000;

export function useBuyOpportunityDetail(opportunityId: string, categoryCode: string) {
  const queryKey = buyOpportunityDetailQueryKey(opportunityId, categoryCode);

  const detailQuery = useQuery({
    enabled: opportunityId.length > 0,
    queryKey,
    queryFn: ({ signal }) =>
      fetchBuyOpportunityDetail(
        opportunityId,
        {
          categoryCode: categoryCode || undefined,
        },
        signal,
      ),
    staleTime: BUY_OPPORTUNITY_DETAIL_STALE_TIME,
  });

  return {
    detail: detailQuery.data ?? null,
    error: detailQuery.error instanceof Error ? detailQuery.error.message : null,
    isLoading: detailQuery.isPending,
    isRefreshing: detailQuery.isFetching && !detailQuery.isPending,
  };
}
