import type { AgentHarnessSnapshot } from '../types/agentHarness';
import { agentHarnessSnapshotSchema } from './agentHarnessSchemas';
import { dashboardApiUrl } from '../../../shared/lib/dashboardApiConfig';
import { fetchJson } from '../../../shared/lib/fetchJson';

export async function fetchAgentHarnessStatus(signal?: AbortSignal): Promise<AgentHarnessSnapshot> {
  return agentHarnessSnapshotSchema.parse(
    await fetchJson(dashboardApiUrl('/api/dashboard/agent-harness/status'), {
      errorPrefix: '/api/dashboard/agent-harness/status',
      signal,
    }),
  );
}

export function agentHarnessStatusQueryKey() {
  return ['agent-harness', 'status'] as const;
}
