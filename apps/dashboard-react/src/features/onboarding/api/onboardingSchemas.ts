import { z } from 'zod';

const nullableStringSchema = z.string().nullable().optional();
const unknownRecordSchema = z.record(z.string(), z.unknown());

export const onboardingCoverageSchema = z.object({
  counts: z.record(z.string(), z.union([z.number(), z.string(), z.null()])).default({}),
  coverage: z.record(z.string(), z.union([z.number(), z.string(), z.null()])).default({}),
  filters: z.record(z.string(), z.union([z.string(), z.number(), z.boolean(), z.null()])).default({}),
});

export const onboardingQueueItemSchema = z.object({
  id: nullableStringSchema,
  matchKey: nullableStringSchema,
  status: nullableStringSchema,
  xianyuCatId: nullableStringSchema,
  xianyuTbCatId: nullableStringSchema,
  xianyuCCatId: nullableStringSchema,
  itemCountSnapshot: z.number().nullable().optional(),
  sampleTitles: z.array(z.string()).default([]),
  businessDomains: z.array(z.string()).default([]),
  updatedAt: nullableStringSchema,
  ownerOperatorId: nullableStringSchema,
  metadata: unknownRecordSchema.nullable().optional(),
  resolvedMapping: unknownRecordSchema.nullable().optional(),
});

export const onboardingQueueSchema = z.object({
  total: z.number().optional().default(0),
  items: z.array(onboardingQueueItemSchema).default([]),
});

export const onboardingDiscoverySchema = z.object({
  sourceKeyword: z.string().optional().default(''),
  executionMode: z.string().optional().default(''),
  run: z
    .object({
      runId: nullableStringSchema,
      pagesSucceeded: z.number().nullable().optional(),
      pagesAttempted: z.number().nullable().optional(),
    })
    .nullable()
    .optional(),
});

const onboardingAttributeOptionSchema = z.object({
  optionCode: z.string(),
  optionName: z.string(),
  sortNo: z.number().optional(),
  status: z.string().optional(),
});

const onboardingAttributeObservationSchema = z.object({
  attributeCode: z.string().nullable().optional(),
  attributeName: z.string().nullable().optional(),
  dataType: z.string().nullable().optional(),
  valueScope: z.string().nullable().optional(),
  isMulti: z.boolean().nullable().optional(),
  unit: z.string().nullable().optional(),
  isRequired: z.boolean().nullable().optional(),
  isSale: z.boolean().nullable().optional(),
  isFilter: z.boolean().nullable().optional(),
  isSearch: z.boolean().nullable().optional(),
  isDisplay: z.boolean().nullable().optional(),
  sortNo: z.number().nullable().optional(),
  observedCount: z.number().nullable().optional(),
  sampleValues: z.array(z.unknown()).default([]),
  selected: z.boolean().nullable().optional(),
  profileSuggested: z.boolean().nullable().optional(),
  suggestedCode: z.string().nullable().optional(),
  optionSuggestions: z.array(onboardingAttributeOptionSchema).default([]),
  visible: z.boolean().nullable().optional(),
});

const onboardingCategoryHintSchema = z.object({
  name: z.string().nullable().optional(),
  confidence: z.number().nullable().optional(),
});

const onboardingAnalysisSchema = z.object({
  sampleCount: z.number().nullable().optional(),
  attributeObservations: z.array(onboardingAttributeObservationSchema).default([]),
  selectedAttributeCodes: z.array(z.string()).default([]),
  categoryHints: z.array(onboardingCategoryHintSchema).default([]),
  sampleTitles: z.array(z.string()).default([]),
});

const onboardingCategorySchema = z.object({
  code: z.string().nullable().optional(),
  name: z.string().nullable().optional(),
  path: z.string().nullable().optional(),
  level: z.number().nullable().optional(),
  status: z.string().nullable().optional(),
});

const onboardingTemplateSchema = z.object({
  version: z.number().nullable().optional(),
  status: z.string().nullable().optional(),
  items: z.array(z.record(z.string(), z.unknown())).default([]),
});

const onboardingCatalogSchema = z.object({
  requestId: z.string().nullable().optional(),
  category: onboardingCategorySchema.nullable().optional(),
  attributes: z.array(z.record(z.string(), z.unknown())).default([]),
  template: onboardingTemplateSchema.nullable().optional(),
});

const onboardingReuseCoverageSchema = z.object({
  coveredSuggestedAttributeCodes: z.array(z.string()).default([]),
  missingSuggestedAttributeCodes: z.array(z.string()).default([]),
  extraTemplateAttributeCodes: z.array(z.string()).default([]),
  coverageRatio: z.number().nullable().optional(),
});

const onboardingReuseSuggestionSchema = z.object({
  category: z.record(z.string(), z.unknown()).nullable().optional(),
  template: z.record(z.string(), z.unknown()).nullable().optional(),
  coverage: onboardingReuseCoverageSchema.nullable().optional(),
});

const onboardingPayloadSchema = z.object({
  requestId: z.string().nullable().optional(),
  catalog: onboardingCatalogSchema.nullable().optional(),
  mappings: z.array(z.record(z.string(), z.unknown())).default([]),
  reuseSuggestion: onboardingReuseSuggestionSchema.nullable().optional(),
});

export const onboardingDraftSchema = z.object({
  selection: unknownRecordSchema.nullable().optional(),
  analysis: onboardingAnalysisSchema.nullable().optional(),
  payload: onboardingPayloadSchema.nullable().optional(),
  reuseSuggestion: onboardingReuseSuggestionSchema.nullable().optional(),
});

export const onboardingPersistResultSchema = z.object({
  dryRun: z.boolean().nullable().optional(),
  categoryId: nullableStringSchema,
  templateId: nullableStringSchema,
  mappingCount: z.number().nullable().optional(),
});

export const onboardingQueueMutationSchema = z.object({
  createdCount: z.number().nullable().optional(),
  resolvedCount: z.number().nullable().optional(),
  queue: unknownRecordSchema.nullable().optional(),
});

export type OnboardingAttributeOption = z.infer<typeof onboardingAttributeOptionSchema>;
export type OnboardingAttributeObservation = z.infer<typeof onboardingAttributeObservationSchema>;
export type OnboardingAnalysis = z.infer<typeof onboardingAnalysisSchema>;
export type OnboardingCategory = z.infer<typeof onboardingCategorySchema>;
export type OnboardingTemplate = z.infer<typeof onboardingTemplateSchema>;
export type OnboardingCatalog = z.infer<typeof onboardingCatalogSchema>;
export type OnboardingReuseCoverage = z.infer<typeof onboardingReuseCoverageSchema>;
export type OnboardingReuseSuggestion = z.infer<typeof onboardingReuseSuggestionSchema>;
export type OnboardingPayload = z.infer<typeof onboardingPayloadSchema>;
export type OnboardingDraft = z.infer<typeof onboardingDraftSchema>;
