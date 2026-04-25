import { z } from 'zod';

const nullableStringSchema = z.string().nullable().optional();
const unknownRecordSchema = z.record(z.string(), z.unknown());

export const categoryConfigItemSchema = z.object({
  id: nullableStringSchema,
  code: nullableStringSchema,
  name: nullableStringSchema,
  path: nullableStringSchema,
  level: z.number().nullable().optional(),
  status: nullableStringSchema,
  promptProfile: nullableStringSchema,
  activeTemplateId: nullableStringSchema,
  extractorProfile: nullableStringSchema,
  validatorProfile: nullableStringSchema,
  llmProviderOverride: nullableStringSchema,
  llmModelOverride: nullableStringSchema,
  runtimeStatus: nullableStringSchema,
  runtimeMetadata: unknownRecordSchema.nullable().optional(),
  createdAt: nullableStringSchema,
  updatedAt: nullableStringSchema,
});

export const categoryConfigListSchema = z.array(categoryConfigItemSchema);

export const categoryConfigUpsertResultSchema = z.object({
  dryRun: z.boolean().nullable().optional(),
  category: categoryConfigItemSchema.nullable().optional(),
  changes: z.array(z.record(z.string(), z.unknown())).default([]),
});

export const templateConfigItemSchema = z.object({
  id: nullableStringSchema,
  categoryCode: nullableStringSchema,
  categoryId: nullableStringSchema,
  version: z.number().nullable().optional(),
  status: nullableStringSchema,
  promptProfile: nullableStringSchema,
  items: z.array(z.record(z.string(), z.unknown())).default([]),
  effectiveAt: nullableStringSchema,
  publishedBy: nullableStringSchema,
  createdAt: nullableStringSchema,
  updatedAt: nullableStringSchema,
});

export const templateConfigListSchema = z.array(templateConfigItemSchema);

export const templateConfigDetailSchema = z.object({
  template: templateConfigItemSchema.nullable().optional(),
  diff: z.record(z.string(), z.unknown()).nullable().optional(),
});

export const templateConfigUpsertResultSchema = z.object({
  dryRun: z.boolean().nullable().optional(),
  template: templateConfigItemSchema.nullable().optional(),
  changes: z.array(z.record(z.string(), z.unknown())).default([]),
});

export const templateConfigDiffPreviewResultSchema = z.object({
  diff: z.record(z.string(), z.unknown()).nullable().optional(),
  summary: nullableStringSchema,
});

export const taskConfigItemSchema = z.object({
  id: nullableStringSchema,
  taskKey: nullableStringSchema,
  displayName: nullableStringSchema,
  taskType: nullableStringSchema,
  profileKey: nullableStringSchema,
  parallelTabs: z.number().nullable().optional(),
  pagingLimit: z.number().nullable().optional(),
  status: nullableStringSchema,
  categoryCode: nullableStringSchema,
  categoryId: nullableStringSchema,
  businessDomain: nullableStringSchema,
  queries: z.array(z.record(z.string(), z.unknown())).default([]),
  brandLexicon: z.array(z.string()).default([]),
  modelLexicon: z.array(z.string()).default([]),
  configLexicon: z.array(z.string()).default([]),
  createdAt: nullableStringSchema,
  updatedAt: nullableStringSchema,
});

export const taskConfigListSchema = z.array(taskConfigItemSchema);

export const taskConfigUpsertResultSchema = z.object({
  dryRun: z.boolean().nullable().optional(),
  task: taskConfigItemSchema.nullable().optional(),
  changes: z.array(z.record(z.string(), z.unknown())).default([]),
});

export type CategoryConfigItem = z.infer<typeof categoryConfigItemSchema>;
export type CategoryConfigUpsertResult = z.infer<typeof categoryConfigUpsertResultSchema>;
export type TemplateConfigItem = z.infer<typeof templateConfigItemSchema>;
export type TemplateConfigDetail = z.infer<typeof templateConfigDetailSchema>;
export type TemplateConfigUpsertResult = z.infer<typeof templateConfigUpsertResultSchema>;
export type TemplateConfigDiffPreviewResult = z.infer<typeof templateConfigDiffPreviewResultSchema>;
export type TaskConfigItem = z.infer<typeof taskConfigItemSchema>;
export type TaskConfigUpsertResult = z.infer<typeof taskConfigUpsertResultSchema>;
