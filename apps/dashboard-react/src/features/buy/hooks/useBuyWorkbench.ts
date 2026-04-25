import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import {
  applyBuyFeedbackCalibration,
  buyBaselinesQueryKey,
  buyWorkbenchQueryKey,
  buyTargetsQueryKey,
  fetchBuyBaselines,
  fetchBuyTargets,
  fetchBuyWorkbench,
  postBuyFeedback,
} from '../api/buyApi';
import type {
  BuyBaselineList,
  BuyFeedbackCalibrationApplyRequest,
  BuyFeedbackRequest,
  BuyWatchTargetList,
} from '../types/buy';

const BUY_WORKBENCH_STALE_TIME = 20_000;

export function useBuyWorkbench(categoryCode: string, limit = 50) {
  const queryClient = useQueryClient();
  const queryKey = buyWorkbenchQueryKey(categoryCode, limit);

  async function invalidateBuyReadModels() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['buy', 'workbench', categoryCode] }),
      queryClient.invalidateQueries({ queryKey: ['buy', 'targets', categoryCode] }),
      queryClient.invalidateQueries({ queryKey: ['buy', 'baselines', categoryCode] }),
      queryClient.invalidateQueries({ queryKey: ['buy', 'opportunity-detail'] }),
    ]);
  }

  const workbenchQuery = useQuery({
    queryKey,
    queryFn: ({ signal }) =>
      fetchBuyWorkbench(
        {
          categoryCode: categoryCode || undefined,
          limit,
        },
        signal,
      ),
    staleTime: BUY_WORKBENCH_STALE_TIME,
  });

  const feedbackMutation = useMutation({
    mutationFn: (payload: BuyFeedbackRequest) => postBuyFeedback(payload),
    onSuccess: async () => {
      await invalidateBuyReadModels();
    },
  });

  const calibrationMutation = useMutation({
    mutationFn: (payload: BuyFeedbackCalibrationApplyRequest) => applyBuyFeedbackCalibration(payload),
    onSuccess: async () => {
      await invalidateBuyReadModels();
    },
  });

  return {
    workbench: workbenchQuery.data ?? null,
    error: workbenchQuery.error instanceof Error ? workbenchQuery.error.message : null,
    isLoading: workbenchQuery.isPending,
    isRefreshing: workbenchQuery.isFetching && !workbenchQuery.isPending,
    submitFeedback: feedbackMutation.mutateAsync,
    feedbackPendingId: feedbackMutation.isPending ? feedbackMutation.variables?.opportunityId ?? null : null,
    applyCalibration: calibrationMutation.mutateAsync,
    calibrationPending: calibrationMutation.isPending,
  };
}

export function useBuyTargets(categoryCode: string, limit = 200) {
  const query = useBuyTargetsQuery(categoryCode, limit);
  return {
    watchTargets: query.data ?? null,
    error: query.error instanceof Error ? query.error.message : null,
    isLoading: query.isPending,
    isRefreshing: query.isFetching && !query.isPending,
  };
}

export function useBuyBaselines(categoryCode: string, limit = 200, baselineDate?: string) {
  const query = useBuyBaselinesQuery(categoryCode, limit, baselineDate);
  return {
    baselines: query.data ?? null,
    error: query.error instanceof Error ? query.error.message : null,
    isLoading: query.isPending,
    isRefreshing: query.isFetching && !query.isPending,
  };
}

function useBuyTargetsQuery(categoryCode: string, limit = 200) {
  return useQuery<BuyWatchTargetList>({
    queryKey: buyTargetsQueryKey(categoryCode, limit),
    queryFn: ({ signal }) =>
      fetchBuyTargets(
        {
          categoryCode: categoryCode || undefined,
          limit,
        },
        signal,
      ),
  });
}

function useBuyBaselinesQuery(categoryCode: string, limit = 200, baselineDate?: string) {
  return useQuery<BuyBaselineList>({
    queryKey: buyBaselinesQueryKey(categoryCode, baselineDate, limit),
    queryFn: ({ signal }) =>
      fetchBuyBaselines(
        {
          categoryCode: categoryCode || undefined,
          baselineDate,
          limit,
        },
        signal,
      ),
  });
}
