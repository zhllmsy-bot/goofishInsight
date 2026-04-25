import { z } from 'zod';

import {
  agentHarnessEventSchema,
  agentHarnessLeadRunSchema,
  agentHarnessMetricsSchema,
  agentHarnessMiddlewareSchema,
  agentHarnessSnapshotSchema,
  agentHarnessTaskSchema,
  agentHarnessWorkspaceSchema,
} from '../api/agentHarnessSchemas';

export type AgentHarnessWorkspace = z.infer<typeof agentHarnessWorkspaceSchema>;
export type AgentHarnessLeadRun = z.infer<typeof agentHarnessLeadRunSchema>;
export type AgentHarnessMetrics = z.infer<typeof agentHarnessMetricsSchema>;
export type AgentHarnessMiddleware = z.infer<typeof agentHarnessMiddlewareSchema>;
export type AgentHarnessTask = z.infer<typeof agentHarnessTaskSchema>;
export type AgentHarnessEvent = z.infer<typeof agentHarnessEventSchema>;
export type AgentHarnessSnapshot = z.infer<typeof agentHarnessSnapshotSchema>;
