import { useQuery } from '@tanstack/react-query';

import { fetchItemDetail, itemDetailQueryKey } from '../api/itemDetailApi';
import { errorMessage } from '../../dashboard/lib/formatters';

export function useItemDetail(itemId: string) {
  const itemDetailQuery = useQuery({
    enabled: Boolean(itemId),
    queryKey: itemDetailQueryKey(itemId),
    queryFn: ({ signal }) => fetchItemDetail(itemId, signal),
    staleTime: 10_000,
  });

  return {
    detail: itemDetailQuery.data ?? null,
    isLoading: itemDetailQuery.isPending,
    error: itemDetailQuery.error ? errorMessage(itemDetailQuery.error) : null,
  };
}
