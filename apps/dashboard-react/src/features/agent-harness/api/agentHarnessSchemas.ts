import { z } from 'zod';

export const agentHarnessWorkspaceSchema = z.object({
  name: z.string(),
  path: z.string(),
  executionMode: z.string(),
  sandboxMode: z.string(),
});

export const agentHarnessLeadRunSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: z.string(),
  goal: z.string(),
  summary: z.string(),
  iteration: z.number(),
  maxIterations: z.number(),
  loopState: z.string(),
  humanGate: z.string(),
  lastDecisionAt: z.string(),
  lastDecisionRelative: z.string(),
  rationale: z.array(z.string()),
});

export const agentHarnessMetricsSchema = z.object({
  taskCount: z.number(),
  runningCount: z.number(),
  queuedCount: z.number(),
  blockedCount: z.number(),
  reviewCount: z.number(),
  completedCount: z.number(),
  parallelismBudget: z.number(),
  activeMiddlewares: z.number(),
});

export const agentHarnessMiddlewareSchema = z.object({
  name: z.string(),
  layer: z.string(),
  purpose: z.string(),
});

export const agentHarnessTaskSchema = z.object({
  key: z.string(),
  title: z.string(),
  owner: z.string(),
  status: z.string(),
  tone: z.string(),
  priority: z.string(),
  scope: z.string(),
  summary: z.string(),
  rationale: z.string(),
  acceptanceCriteria: z.array(z.string()),
  dependencies: z.array(z.string()),
  files: z.array(z.string()),
  middlewareFocus: z.array(z.string()),
  startedAt: z.string(),
  updatedAt: z.string(),
  updatedAtRelative: z.string(),
  progress: z.number(),
  risk: z.string(),
});

export const agentHarnessEventSchema = z.object({
  id: z.string(),
  kind: z.string(),
  tone: z.string(),
  title: z.string(),
  detail: z.string(),
  at: z.string(),
  atRelative: z.string(),
});

export const agentHarnessSnapshotSchema = z.object({
  updatedAt: z.string(),
  workspace: agentHarnessWorkspaceSchema,
  leadRun: agentHarnessLeadRunSchema,
  metrics: agentHarnessMetricsSchema,
  middlewareStack: z.array(agentHarnessMiddlewareSchema),
  tasks: z.array(agentHarnessTaskSchema),
  events: z.array(agentHarnessEventSchema),
  nextActions: z.array(z.string()),
});
