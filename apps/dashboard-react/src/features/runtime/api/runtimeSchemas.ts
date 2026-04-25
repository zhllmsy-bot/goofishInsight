import { z } from 'zod';

export const runtimeCheckSchema = z.object({
  label: z.string(),
  ok: z.boolean(),
  detail: z.string(),
});

export const runtimeStatSchema = z.object({
  label: z.string(),
  value: z.string(),
});

export const runtimeActionSchema = z.object({
  action: z.string(),
  label: z.string(),
  tone: z.string().optional(),
});

export const runtimeGroupSchema = z.object({
  key: z.string(),
  title: z.string(),
  description: z.string(),
  status: z.string(),
  checks: z.array(runtimeCheckSchema),
  stats: z.array(runtimeStatSchema),
  actions: z.array(runtimeActionSchema),
});

export const runtimeStatusSchema = z.object({
  updatedAt: z.string(),
  groups: z.array(runtimeGroupSchema),
});

export const runtimeActionRequestSchema = z.object({
  target: z.string(),
  action: z.string(),
  categoryCode: z.string().optional(),
});

export const runtimeActionResultSchema = z.object({
  ok: z.boolean(),
  target: z.string(),
  action: z.string(),
  runtime: runtimeStatusSchema,
});
