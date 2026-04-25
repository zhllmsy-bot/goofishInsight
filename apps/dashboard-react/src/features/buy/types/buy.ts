import type { z } from 'zod';

import {
  buyAlertEventSchema,
  buyBaselineSchema,
  buyDataValueReportSchema,
  buyFeedbackCalibrationApplyResponseSchema,
  buyFeedbackEntrySchema,
  buyFeedbackResponseSchema,
  buyBaselineListSchema,
  buyOpportunityDetailOpportunitySchema,
  buyOpportunityDetailSchema,
  buyOpportunityRiskSchema,
  buyOpportunitySchema,
  buyWatchTargetListSchema,
  buyWatchTargetSchema,
  buyWorkbenchSchema,
} from '../api/buySchemas';

export type BuyWorkbench = z.infer<typeof buyWorkbenchSchema>;
export type BuyDataValueReport = z.infer<typeof buyDataValueReportSchema>;
export type BuyOpportunity = z.infer<typeof buyOpportunitySchema>;
export type BuyOpportunityDetailOpportunity = z.infer<typeof buyOpportunityDetailOpportunitySchema>;
export type BuyOpportunityDetail = z.infer<typeof buyOpportunityDetailSchema>;
export type BuyBaseline = z.infer<typeof buyBaselineSchema>;
export type BuyWatchTarget = z.infer<typeof buyWatchTargetSchema>;
export type BuyWatchTargetList = z.infer<typeof buyWatchTargetListSchema>;
export type BuyBaselineList = z.infer<typeof buyBaselineListSchema>;
export type BuyOpportunityRisk = z.infer<typeof buyOpportunityRiskSchema>;
export type BuyAlertEvent = z.infer<typeof buyAlertEventSchema>;
export type BuyFeedbackEntry = z.infer<typeof buyFeedbackEntrySchema>;
export type BuyFeedbackResponse = z.infer<typeof buyFeedbackResponseSchema>;
export type BuyFeedbackCalibrationApplyResponse = z.infer<typeof buyFeedbackCalibrationApplyResponseSchema>;

export type BuyFeedbackRequest = {
  opportunityId: string;
  feedbackLabel: 'purchased' | 'contacted' | 'not_worth_it' | 'detail_opened' | 'listing_opened';
  feedbackType?: string;
  operatorId?: string;
  feedbackNote?: string;
  purchasePrice?: string;
  expectedResalePrice?: string;
  linkToAlertCandidate?: boolean;
};

export type BuyFeedbackCalibrationApplyRequest = {
  categoryCode: string;
  windowDays?: number;
  operatorId?: string;
  recommendationIds?: string[];
};
