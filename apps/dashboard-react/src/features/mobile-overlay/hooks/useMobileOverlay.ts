import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { OverlayAnalyzeRequest } from '../types/mobileOverlay';
import { fetchOverlayHealthz, postOverlayAnalyze, overlayHealthzQueryKey } from '../api/mobileOverlayApi';

export function useOverlayHealthz() {
  const healthzQuery = useQuery({
    queryKey: overlayHealthzQueryKey(),
    queryFn: ({ signal }) => fetchOverlayHealthz(signal),
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });

  return {
    healthz: healthzQuery.data ?? null,
    isLoading: healthzQuery.isPending,
    error: healthzQuery.error instanceof Error ? healthzQuery.error.message : null,
  };
}

export function useOverlayAnalysis() {
  const queryClient = useQueryClient();

  const analysisMutation = useMutation({
    mutationFn: ({ request }: { request: OverlayAnalyzeRequest }) => postOverlayAnalyze(request),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: overlayHealthzQueryKey() });
    },
  });

  return {
    analysis: analysisMutation.data ?? null,
    isAnalyzing: analysisMutation.isPending,
    error: analysisMutation.error instanceof Error ? analysisMutation.error.message : null,
    submitAnalysis: (request: OverlayAnalyzeRequest) => analysisMutation.mutateAsync({ request }),
  };
}