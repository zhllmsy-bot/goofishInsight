import { z } from 'zod';
import { itemDetailSchema } from '../../item-detail/api/itemDetailSchemas';

const nullableStringSchema = z.string().nullable().optional();
const nullableNumberSchema = z.number().nullable().optional();
const nullableBooleanSchema = z.boolean().nullable().optional();

const recommendationSchema = z.object({
  id: nullableStringSchema,
  priority: nullableStringSchema,
  title: z.string(),
  summary: z.string(),
  recommendedAction: z.string(),
  evidence: z.record(z.string(), z.unknown()).optional(),
});

const explanationSchema = z.object({
  readinessSummary: nullableStringSchema,
  reviewGateSummary: nullableStringSchema,
  specGateSummary: nullableStringSchema,
  missingRequiredFields: z.array(z.string()).optional(),
  confidenceSummary: nullableStringSchema,
  reliabilityScore: nullableNumberSchema,
});

const tierStatsSchema = z.object({
  opportunityCount: nullableNumberSchema,
  feedbackCount: nullableNumberSchema,
  acceptanceRate: nullableNumberSchema,
});

const feedbackQualitySchema = z.object({
  feedbackCount: nullableNumberSchema,
  opportunityCount: nullableNumberSchema,
  tierStats: z.record(z.string(), tierStatsSchema).optional(),
  rejectReasonCounts: z.record(z.string(), z.number()).optional(),
});

const calibrationRecommendationsSchema = z.object({
  totalRecommendationCount: nullableNumberSchema,
  autoApplicableRecommendationCount: nullableNumberSchema,
  templateFieldRecommendations: z.array(recommendationSchema).optional(),
  thresholdRecommendations: z.array(recommendationSchema).optional(),
  rankingRecommendations: z.array(recommendationSchema).optional(),
});

const calibrationThresholdBlockSchema = z.object({
  seller_sample_count: nullableNumberSchema,
  unique_seller_count: nullableNumberSchema,
  exact_spec_ratio: nullableNumberSchema,
  reliability_score: nullableNumberSchema,
  freshness_days: nullableNumberSchema,
});

const calibrationScoringSchema = z.object({
  buyCeilingTightenPct: nullableNumberSchema,
  discountRateWeight: nullableNumberSchema,
  ceilingGapWeight: nullableNumberSchema,
  confidenceWeight: nullableNumberSchema,
  riskPenaltyWeight: nullableNumberSchema,
  discountRateSaturation: nullableNumberSchema,
  ceilingGapSaturation: nullableNumberSchema,
  defaultConfidence: nullableNumberSchema,
});

const effectiveCalibrationConfigSchema = z.object({
  pricingThresholds: z.object({
    referenceOnly: calibrationThresholdBlockSchema.optional(),
    guidanceReady: calibrationThresholdBlockSchema.optional(),
  }).optional(),
  opportunityScoring: calibrationScoringSchema.optional(),
  lastAppliedAt: nullableStringSchema,
  lastAppliedBy: nullableStringSchema,
  lastApplySource: nullableStringSchema,
  lastCalibrationWindowDays: nullableNumberSchema,
  lastAppliedRecommendationIds: z.array(z.string()).optional(),
}).passthrough();

const feedbackCalibrationSchema = z.object({
  windowDays: nullableNumberSchema,
  effectiveCalibrationConfig: effectiveCalibrationConfigSchema.optional(),
  recommendations: calibrationRecommendationsSchema.optional(),
});

const outcomeFunnelSchema = z.object({
  alertedOpportunityCount: nullableNumberSchema,
  openedOpportunityCount: nullableNumberSchema,
  contactedOpportunityCount: nullableNumberSchema,
  purchasedOpportunityCount: nullableNumberSchema,
  purchaseWithoutContactCount: nullableNumberSchema,
  roiEvidenceCount: nullableNumberSchema,
  alertToOpenRate: nullableNumberSchema,
  alertToContactRate: nullableNumberSchema,
  alertToPurchaseRate: nullableNumberSchema,
  openToContactRate: nullableNumberSchema,
  contactToPurchaseRate: nullableNumberSchema,
  roiEvidenceCoverageRate: nullableNumberSchema,
  averageExpectedProfit: nullableNumberSchema,
  averageExpectedRoiRate: nullableNumberSchema,
});

const outcomeProofSchema = z.object({
  alertEventCount: nullableNumberSchema,
  openFeedbackCount: nullableNumberSchema,
  contactFeedbackCount: nullableNumberSchema,
  purchaseFeedbackCount: nullableNumberSchema,
  hasAlertEvidence: nullableBooleanSchema,
  hasOpenEvidence: nullableBooleanSchema,
  hasContactEvidence: nullableBooleanSchema,
  hasPurchaseEvidence: nullableBooleanSchema,
  hasRoiEvidence: nullableBooleanSchema,
  latestFeedbackLabel: nullableStringSchema,
  purchasePrice: nullableNumberSchema,
  expectedResalePrice: nullableNumberSchema,
  estimatedProfit: nullableNumberSchema,
  estimatedRoiRate: nullableNumberSchema,
});

const dataValueStageSchema = z.object({
  key: z.string(),
  label: z.string(),
  count: nullableNumberSchema,
  denominator: nullableNumberSchema,
  conversionRate: nullableNumberSchema,
  leakageCount: nullableNumberSchema,
});

const dataValueDiagnosisSchema = z.object({
  stage: nullableStringSchema,
  severity: nullableStringSchema,
  statusLabel: nullableStringSchema,
  summary: nullableStringSchema,
  nextBestAction: nullableStringSchema,
});

const dataValueRecommendationSchema = z.object({
  priority: nullableStringSchema,
  title: z.string(),
  reason: nullableStringSchema,
  action: nullableStringSchema,
});

const dataValueSummarySchema = z
  .object({
    itemCount: nullableNumberSchema,
    activeItemCount: nullableNumberSchema,
    pricedItemCount: nullableNumberSchema,
    snapshotCount: nullableNumberSchema,
    rejectionCount: nullableNumberSchema,
    specItemCount: nullableNumberSchema,
    completeSpecItemCount: nullableNumberSchema,
    baselineCount: nullableNumberSchema,
    latestBaselineCount: nullableNumberSchema,
    latestBaselineDate: nullableStringSchema,
    opportunityCount: nullableNumberSchema,
    openOpportunityCount: nullableNumberSchema,
    guidanceReadyOpportunityCount: nullableNumberSchema,
    referenceLimitedOpportunityCount: nullableNumberSchema,
    alertEventCount: nullableNumberSchema,
    alertedOpportunityCount: nullableNumberSchema,
    feedbackCount: nullableNumberSchema,
    openedOpportunityCount: nullableNumberSchema,
    contactedOpportunityCount: nullableNumberSchema,
    purchasedOpportunityCount: nullableNumberSchema,
    roiEvidenceCount: nullableNumberSchema,
    specCoverageRate: nullableNumberSchema,
    completeSpecCoverageRate: nullableNumberSchema,
    opportunityYieldRate: nullableNumberSchema,
    openOpportunityRate: nullableNumberSchema,
    guidanceReadyRate: nullableNumberSchema,
    alertCoverageRate: nullableNumberSchema,
    feedbackCoverageRate: nullableNumberSchema,
    purchaseProofRate: nullableNumberSchema,
    roiProofRate: nullableNumberSchema,
    dataValueScore: nullableNumberSchema,
    latestItemSeenAt: nullableStringSchema,
    latestSnapshotAt: nullableStringSchema,
    latestOpportunityDetectedAt: nullableStringSchema,
    latestFeedbackAt: nullableStringSchema,
  })
  .passthrough();

const dataValueCategorySchema = z
  .object({
    categoryCode: z.string(),
    itemCount: nullableNumberSchema,
    activeItemCount: nullableNumberSchema,
    specItemCount: nullableNumberSchema,
    completeSpecItemCount: nullableNumberSchema,
    baselineCount: nullableNumberSchema,
    latestBaselineDate: nullableStringSchema,
    opportunityCount: nullableNumberSchema,
    openOpportunityCount: nullableNumberSchema,
    guidanceReadyOpportunityCount: nullableNumberSchema,
    alertEventCount: nullableNumberSchema,
    alertedOpportunityCount: nullableNumberSchema,
    feedbackCount: nullableNumberSchema,
    purchasedOpportunityCount: nullableNumberSchema,
    roiEvidenceCount: nullableNumberSchema,
    specCoverageRate: nullableNumberSchema,
    completeSpecCoverageRate: nullableNumberSchema,
    opportunityYieldRate: nullableNumberSchema,
    feedbackCoverageRate: nullableNumberSchema,
    purchaseProofRate: nullableNumberSchema,
    roiProofRate: nullableNumberSchema,
    utilizationScore: nullableNumberSchema,
  })
  .passthrough();

export const buyDataValueReportSchema = z.object({
  categoryCode: nullableStringSchema,
  generatedAt: nullableStringSchema,
  summary: dataValueSummarySchema,
  diagnosis: dataValueDiagnosisSchema,
  stages: z.array(dataValueStageSchema),
  categoryBreakdown: z.array(dataValueCategorySchema),
  recommendations: z.array(dataValueRecommendationSchema),
});

export const buyFeedbackCalibrationApplyResponseSchema = z.object({
  categoryCode: nullableStringSchema,
  windowDays: nullableNumberSchema,
  appliedRecommendationCount: nullableNumberSchema,
  skippedRecommendationCount: nullableNumberSchema,
  appliedRecommendations: z.array(recommendationSchema).optional(),
  skippedRecommendations: z
    .array(
      z
        .object({
          id: nullableStringSchema,
          title: nullableStringSchema,
          reason: nullableStringSchema,
        })
        .passthrough(),
    )
    .optional(),
  effectiveCalibrationConfig: effectiveCalibrationConfigSchema.optional(),
  baselineRebuild: z.record(z.string(), z.unknown()).nullable().optional(),
  opportunityRefresh: z.record(z.string(), z.unknown()).nullable().optional(),
}).passthrough();

export const buyOpportunitySchema = z.object({
  id: z.string(),
  itemIdRef: nullableStringSchema,
  title: nullableStringSchema,
  itemId: nullableStringSchema,
  listingUrl: nullableStringSchema,
  region: nullableStringSchema,
  status: nullableStringSchema,
  decision: nullableStringSchema,
  currentPrice: nullableNumberSchema,
  fairPrice: nullableNumberSchema,
  buyCeiling: nullableNumberSchema,
  discountRate: nullableNumberSchema,
  opportunityScore: nullableNumberSchema,
  riskScore: nullableNumberSchema,
  exactSpecReady: nullableBooleanSchema,
  specConfidence: nullableNumberSchema,
  baselineMatchLevel: nullableStringSchema,
  baselineMatchKey: nullableStringSchema,
  templateAvailabilityTier: nullableStringSchema,
  lastDetectedAt: nullableStringSchema,
  explanation: explanationSchema.optional(),
  specContract: z
    .object({
      status: nullableStringSchema,
    })
    .passthrough()
    .optional(),
});

const dailyOpportunityTaskSchema = z.object({
  rank: nullableNumberSchema,
  groupKey: z.string(),
  groupLabel: z.string(),
  recommendedAction: z.string(),
  reason: nullableStringSchema,
  slaLabel: nullableStringSchema,
  riskFlags: z.array(z.string()).optional(),
  valueSignals: z.array(z.string()).optional(),
  opportunity: buyOpportunitySchema,
});

const dailyOpportunityGroupSchema = z.object({
  key: z.string(),
  label: z.string(),
  recommendedAction: z.string(),
  count: nullableNumberSchema,
  tasks: z.array(dailyOpportunityTaskSchema),
});

const dailyMarketIntelSchema = z.object({
  baselineKey: nullableStringSchema,
  sampleSize: nullableNumberSchema,
  fairPrice: nullableNumberSchema,
  buyCeiling: nullableNumberSchema,
  confidence: nullableNumberSchema,
  reason: nullableStringSchema,
});

const dailyOpportunityPackSchema = z.object({
  generatedAt: nullableStringSchema,
  summary: z.object({
    targetProcessingCount: nullableNumberSchema,
    packOpportunityCount: nullableNumberSchema,
    openBacklogCount: nullableNumberSchema,
    ungroupedOpenCount: nullableNumberSchema,
    feedbackCount: nullableNumberSchema,
    contactedOpportunityCount: nullableNumberSchema,
    purchasedOpportunityCount: nullableNumberSchema,
    roiEvidenceCount: nullableNumberSchema,
    feedbackCoverageRate: nullableNumberSchema,
    operatingMode: nullableStringSchema,
    northStar: nullableStringSchema,
  }),
  groups: z.array(dailyOpportunityGroupSchema),
  marketIntel: z.array(dailyMarketIntelSchema),
});

export const buyOpportunityDetailOpportunitySchema = buyOpportunitySchema.extend({
  firstDetectedAt: nullableStringSchema,
  decisionNote: nullableStringSchema,
  feedbackSummary: z
    .object({
      feedbackAction: nullableStringSchema,
      feedbackCategory: nullableStringSchema,
      feedbackLabel: nullableStringSchema,
      operatorId: nullableStringSchema,
      feedbackNote: nullableStringSchema,
      recordedAt: nullableStringSchema,
      alertCandidateLinkage: z.record(z.string(), z.unknown()).optional(),
    })
    .optional(),
  matchedTemplateKey: nullableStringSchema,
  matchedTemplateLabel: nullableStringSchema,
  matchedFieldValues: z.record(z.string(), z.unknown()).optional(),
  templateAvailabilityTier: nullableStringSchema,
  metrics: z.record(z.string(), z.unknown()).optional(),
});

export const buyBaselineSchema = z.object({
  id: z.string(),
  baselineKey: z.string(),
  sampleSize: nullableNumberSchema,
  fairPrice: nullableNumberSchema,
  buyCeiling: nullableNumberSchema,
  confidence: nullableNumberSchema,
  baselineDate: nullableStringSchema,
  explanation: explanationSchema.optional(),
});

export const buyWatchTargetSchema = z.object({
  id: z.string(),
  targetName: z.string(),
  profileKey: nullableStringSchema,
  status: nullableStringSchema,
  budgetCeiling: nullableNumberSchema,
  desiredMemoryGb: nullableNumberSchema,
  desiredStorageGb: nullableNumberSchema,
  desiredRegion: nullableStringSchema,
  riskTolerance: nullableStringSchema,
  notifyCooldownMinutes: nullableNumberSchema,
});

export const buyWorkbenchSchema = z.object({
  categoryCode: nullableStringSchema,
  summary: z
    .object({
      opportunityCount: nullableNumberSchema,
      baselineCount: nullableNumberSchema,
      watchTargetCount: nullableNumberSchema,
      todayOpportunityCount: nullableNumberSchema,
      alertHitRate: nullableNumberSchema,
      alertCount: nullableNumberSchema,
      alertHitCount: nullableNumberSchema,
      feedbackCount: nullableNumberSchema,
      acceptCount: nullableNumberSchema,
      rejectCount: nullableNumberSchema,
      calibrationRecommendationCount: nullableNumberSchema,
    })
    .optional(),
  dataValue: buyDataValueReportSchema.optional(),
  dailyOpportunityPack: dailyOpportunityPackSchema.optional(),
  outcomeFunnel: outcomeFunnelSchema.optional(),
  feedbackQuality: feedbackQualitySchema.optional(),
  feedbackCalibration: feedbackCalibrationSchema.optional(),
  opportunities: z.array(buyOpportunitySchema).optional(),
  baselines: z.array(buyBaselineSchema).optional(),
  watchTargets: z.array(buyWatchTargetSchema).optional(),
});

export const buyWatchTargetListSchema = z.object({
  categoryCode: nullableStringSchema,
  summary: z
    .object({
      watchTargetCount: nullableNumberSchema,
      activeWatchTargetCount: nullableNumberSchema,
    })
    .optional(),
  watchTargets: z.array(buyWatchTargetSchema),
});

export const buyBaselineListSchema = z.object({
  categoryCode: nullableStringSchema,
  summary: z
    .object({
      baselineCount: nullableNumberSchema,
      baselineDateFrom: nullableStringSchema,
      baselineDateTo: nullableStringSchema,
    })
    .optional(),
  baselines: z.array(buyBaselineSchema),
});

export const buyFeedbackResponseSchema = z.object({
  opportunityId: nullableStringSchema,
  feedbackLabel: nullableStringSchema,
  feedbackType: nullableStringSchema,
  linkedAlertCandidate: nullableBooleanSchema,
  status: nullableStringSchema,
  decision: nullableStringSchema,
}).passthrough();

export const buyOpportunityRiskSchema = z.object({
  id: z.string(),
  riskCode: z.string(),
  riskLevel: nullableStringSchema,
  detail: nullableStringSchema,
  evidence: z.record(z.string(), z.unknown()).optional(),
});

export const buyAlertEventSchema = z.object({
  id: z.string(),
  opportunityId: nullableStringSchema,
  watchTargetId: nullableStringSchema,
  alertChannel: nullableStringSchema,
  alertReason: nullableStringSchema,
  status: nullableStringSchema,
  sentAt: nullableStringSchema,
  payload: z.record(z.string(), z.unknown()).optional(),
});

export const buyFeedbackEntrySchema = z.object({
  id: z.string(),
  opportunityId: nullableStringSchema,
  feedbackType: nullableStringSchema,
  feedbackLabel: nullableStringSchema,
  operatorId: nullableStringSchema,
  feedbackNote: nullableStringSchema,
  purchasePrice: nullableNumberSchema,
  expectedResalePrice: nullableNumberSchema,
  payload: z.record(z.string(), z.unknown()).optional(),
});

export const buyOpportunityDetailSchema = z.object({
  categoryCode: nullableStringSchema,
  opportunity: buyOpportunityDetailOpportunitySchema,
  baseline: buyBaselineSchema.nullable().optional(),
  watchTarget: buyWatchTargetSchema.nullable().optional(),
  outcomeProof: outcomeProofSchema.optional(),
  risks: z.array(buyOpportunityRiskSchema).optional(),
  alertEvents: z.array(buyAlertEventSchema).optional(),
  feedbackEntries: z.array(buyFeedbackEntrySchema).optional(),
  itemDetail: itemDetailSchema.nullable().optional(),
});
