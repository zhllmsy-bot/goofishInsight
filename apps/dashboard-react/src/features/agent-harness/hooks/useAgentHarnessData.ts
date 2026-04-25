import { useQuery } from '@tanstack/react-query';

import { agentHarnessStatusQueryKey, fetchAgentHarnessStatus } from '../api/agentHarnessApi';

const AGENT_HARNESS_REFRESH_MS = 15_000;

export function useAgentHarnessState() {
  const query = useQuery({
    queryKey: agentHarnessStatusQueryKey(),
    queryFn: ({ signal }) => fetchAgentHarnessStatus(signal),
    refetchInterval: AGENT_HARNESS_REFRESH_MS,
    refetchIntervalInBackground: true,
  });

  return {
    snapshot: query.data ?? null,
    isLoading: query.isPending,
    error: query.error instanceof Error ? query.error.message : null,
  };
}
