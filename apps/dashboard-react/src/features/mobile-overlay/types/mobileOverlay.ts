import type { z } from 'zod';

import {
  overlayAnalyzeRequestSchema,
  overlayAnalyzeResponseSchema,
  overlayDomainAnalysisSchema,
  overlayHealthzResponseSchema,
  overlayOcrLineSchema,
  overlayOcrSummarySchema,
  overlayPricingSchema,
  overlayTrendSchema,
  overlayVlmPayloadSchema,
  overlayDecisionSchema,
} from '../api/mobileOverlaySchemas';

export type OverlayOcrLine = z.infer<typeof overlayOcrLineSchema>;
export type OverlayAnalyzeRequest = z.infer<typeof overlayAnalyzeRequestSchema>;
export type OverlayVlmPayload = z.infer<typeof overlayVlmPayloadSchema>;
export type OverlayOcrSummary = z.infer<typeof overlayOcrSummarySchema>;
export type OverlayPricing = z.infer<typeof overlayPricingSchema>;
export type OverlayTrend = z.infer<typeof overlayTrendSchema>;
export type OverlayDomainAnalysis = z.infer<typeof overlayDomainAnalysisSchema>;
export type OverlayDecision = z.infer<typeof overlayDecisionSchema>;
export type OverlayAnalyzeResponse = z.infer<typeof overlayAnalyzeResponseSchema>;
export type OverlayHealthzResponse = z.infer<typeof overlayHealthzResponseSchema>;