import { z } from 'zod';

export const overlayOcrLineSchema = z.object({
  text: z.string(),
  left: z.number().nullable(),
  top: z.number().nullable(),
  right: z.number().nullable(),
  bottom: z.number().nullable(),
});

export const overlayAnalyzeRequestSchema = z.object({
  source_package: z.string().nullable(),
  screen_width: z.number().nullable(),
  screen_height: z.number().nullable(),
  captured_at: z.string().nullable(),
  screenshot_base64: z.string().nullable(),
  ocr_lines: z.array(overlayOcrLineSchema),
});

export const overlayVlmPayloadSchema = z.object({
  title_candidate: z.string().nullable(),
  brand_hint: z.string().nullable(),
  business_domain_hint: z.string().nullable(),
  model_hint: z.string().nullable(),
  spec_hint: z.string().nullable(),
  price_hint: z.string().nullable(),
  confidence: z.number().nullable(),
  reason: z.string().nullable(),
  enabled: z.boolean(),
  used: z.boolean(),
  error: z.string().nullable().optional(),
});

export const overlayOcrSummarySchema = z.object({
  line_count: z.number(),
  title_candidate: z.string().nullable(),
  ocr_title_candidate: z.string().nullable(),
  title_candidate_source: z.string(),
  listing_price: z.number().nullable(),
  price_source_text: z.string().nullable(),
  text_excerpt: z.string(),
  screenshot_supplied: z.boolean(),
});

export const overlayPricingSchema = z.object({
  label: z.string().nullable(),
  product_label: z.string().nullable(),
  spec_label: z.string().nullable(),
  seller_sample_count: z.number().nullable(),
  listing_count: z.number().nullable(),
  reliability_score: z.number().nullable(),
  reliability_tier: z.string().nullable(),
  is_actionable: z.boolean().nullable(),
  sample_confident: z.boolean().nullable(),
  safe_buy_price: z.number().nullable(),
  target_buy_ceiling: z.number().nullable(),
  fair_price: z.number().nullable(),
  market_mid_price: z.number().nullable(),
  estimated_profit_floor: z.number().nullable(),
  estimated_profit_ceiling: z.number().nullable(),
  required_profit_amount: z.number().nullable(),
  normal_margin_pct: z.number().nullable(),
  safe_margin_pct: z.number().nullable(),
  listing_price: z.number().nullable(),
  expected_profit_margin_pct: z.number().nullable(),
  price_position: z.string().nullable(),
});

export const overlayTrendSchema = z.object({
  latest_close: z.number().nullable(),
  latest_range_label: z.string().nullable(),
  change_label: z.string().nullable(),
  volatility_label: z.string().nullable(),
  day_count: z.number().nullable(),
  trend_quality_ok: z.boolean().nullable(),
  latest_sample_count: z.number().nullable(),
  recent_average_sample_count: z.number().nullable(),
});

export const overlayDomainAnalysisSchema = z.object({
  business_domain: z.string(),
  domain_label: z.string(),
  task_key: z.string(),
  task_display_name: z.string(),
  title_candidate: z.string(),
  candidate_record: z.record(z.string(), z.unknown()).nullable(),
  matched_view: z.string(),
  score: z.number(),
  pricing: overlayPricingSchema,
  trend: overlayTrendSchema.nullable(),
});

export const overlayDecisionSchema = z.object({
  status: z.string(),
  quick_flip_ok: z.boolean(),
  summary: z.string(),
  risk_flags: z.array(z.string()),
});

export const overlayAnalyzeResponseSchema = z.object({
  ok: z.boolean(),
  source_package: z.string().nullable(),
  captured_at: z.string().nullable(),
  ocr_summary: overlayOcrSummarySchema,
  vlm_summary: overlayVlmPayloadSchema.nullable(),
  match: overlayDomainAnalysisSchema.nullable(),
  alternatives: z.array(overlayDomainAnalysisSchema),
  decision: overlayDecisionSchema,
});

export const overlayVlmRuntimeStatusSchema = z.object({
  enabled: z.boolean(),
  base_url: z.string().nullable(),
  model: z.string().nullable(),
  thinking_enabled: z.boolean().nullable(),
  queue: z.object({
    worker_alive: z.boolean(),
    pending_jobs: z.number(),
    active_job_id: z.string().nullable(),
    active_seconds: z.number().nullable(),
    completed_jobs: z.number(),
    failed_jobs: z.number(),
  }),
});

export const overlayHealthzResponseSchema = z.object({
  ok: z.boolean(),
  vlm: overlayVlmRuntimeStatusSchema,
});