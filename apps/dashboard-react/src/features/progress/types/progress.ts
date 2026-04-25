import type { z } from 'zod';

import {
  progressAuditsSectionSchema,
  progressHeaderSchema,
  progressOverviewSchema,
  progressOverviewSectionSchema,
  progressUsageWorkersSectionSchema,
} from '../api/progressSchemas';

export type ProgressHeader = z.infer<typeof progressHeaderSchema>;
export type ProgressOverview = z.infer<typeof progressOverviewSchema>;
export type ProgressOverviewSection = z.infer<typeof progressOverviewSectionSchema>;
export type ProgressUsageWorkersSection = z.infer<typeof progressUsageWorkersSectionSchema>;
export type ProgressAuditsSection = z.infer<typeof progressAuditsSectionSchema>;
