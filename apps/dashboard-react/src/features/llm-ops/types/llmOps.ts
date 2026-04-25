import type { z } from 'zod';

import {
  llmTraceDetailResponseSchema,
  llmTraceDetailSchema,
  llmTraceSectionSchema,
  usageWorkersSectionSchema,
} from '../api/llmOpsSchemas';

export type LlmTraceSection = z.infer<typeof llmTraceSectionSchema>;
export type LlmTraceDetail = z.infer<typeof llmTraceDetailSchema>;
export type LlmTraceDetailResponse = z.infer<typeof llmTraceDetailResponseSchema>;
export type UsageWorkersSection = z.infer<typeof usageWorkersSectionSchema>;
