import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import type { QueryState } from '../../dashboard/types/dashboard';
import {
  fetchLlmTraceDetail,
  fetchLlmTraceSection,
  fetchUsageWorkersSection,
  llmTraceDetailQueryKey,
  llmTraceSectionQueryKey,
  usageWorkersSectionQueryKey,
} from '../api/llmOpsApi';

export function useLlmOpsState(query: Pick<QueryState, 'categoryCode'>) {
  const traceSectionQuery = useQuery({
    queryKey: llmTraceSectionQueryKey(),
    queryFn: ({ signal }) => fetchLlmTraceSection(signal),
    staleTime: 3_000,
  });

  const [selectedTraceKey, setSelectedTraceKey] = useState<string>('');

  const effectiveTraceKey = useMemo(() => {
    if (selectedTraceKey) {
      return selectedTraceKey;
    }
    return (
      traceSectionQuery.data?.latest_trace?.trace_key
      || traceSectionQuery.data?.traces?.[0]?.trace_key
      || ''
    );
  }, [selectedTraceKey, traceSectionQuery.data?.latest_trace?.trace_key, traceSectionQuery.data?.traces]);

  const traceDetailQuery = useQuery({
    enabled: Boolean(effectiveTraceKey),
    queryKey: llmTraceDetailQueryKey(effectiveTraceKey),
    queryFn: ({ signal }) => fetchLlmTraceDetail(effectiveTraceKey, signal),
    staleTime: 3_000,
  });

  const usageWorkersQuery = useQuery({
    queryKey: usageWorkersSectionQueryKey(query.categoryCode),
    queryFn: ({ signal }) => fetchUsageWorkersSection(query, signal),
    staleTime: 10_000,
  });

  return {
    selectedTraceKey: effectiveTraceKey,
    setSelectedTraceKey,
    traceSection: traceSectionQuery.data ?? null,
    traceSectionError: traceSectionQuery.error,
    traceDetail: traceDetailQuery.data ?? traceSectionQuery.data?.latest_trace ?? null,
    traceDetailError: traceDetailQuery.error,
    usageWorkers: usageWorkersQuery.data ?? null,
    usageWorkersError: usageWorkersQuery.error,
  };
}
