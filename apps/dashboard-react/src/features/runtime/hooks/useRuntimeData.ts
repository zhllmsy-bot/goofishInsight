import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { RuntimeActionRequest } from '../types/runtime';
import {
  fetchRuntimeStatus,
  postRuntimeAction,
  runtimeStatusScopedQueryKey,
} from '../api/runtimeApi';

const RUNTIME_REFRESH_MS = 20_000;

export function useRuntimeControlState(categoryCode?: string | null) {
  const queryClient = useQueryClient();
  const queryKey = runtimeStatusScopedQueryKey(categoryCode);

  const runtimeQuery = useQuery({
    queryKey,
    queryFn: ({ signal }) => fetchRuntimeStatus({ categoryCode }, signal),
    refetchInterval: RUNTIME_REFRESH_MS,
    refetchIntervalInBackground: true,
  });

  const actionMutation = useMutation({
    mutationFn: ({ request }: { request: RuntimeActionRequest }) => postRuntimeAction(request),
    onSuccess: (result) => {
      queryClient.setQueryData(queryKey, result.runtime);
    },
  });

  return {
    runtime: runtimeQuery.data ?? null,
    isLoading: runtimeQuery.isPending,
    error: runtimeQuery.error instanceof Error ? runtimeQuery.error.message : null,
    pendingTarget: actionMutation.variables?.request.target ?? '',
    pendingAction: actionMutation.variables?.request.action ?? '',
    runAction: (request: RuntimeActionRequest) => actionMutation.mutateAsync({ request }),
  };
}
