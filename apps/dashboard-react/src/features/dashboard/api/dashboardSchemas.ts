import { z } from 'zod';

const nullableStringSchema = z.string().nullable().optional();
const nullableNumberSchema = z.number().nullable().optional();
const primitiveValueSchema = z.union([z.string(), z.number(), z.boolean(), z.null()]);

export const filterOptionSchema = z.object({
  value: z.string(),
  label: z.string(),
  summaryLabel: z.string().optional(),
});

export const filterFieldSchema = z.object({
  key: z.string(),
  label: z.string(),
  options: z.array(filterOptionSchema),
  placeholder: z.string().optional(),
  pricingRole: z.string().nullable().optional(),
  pricingSemanticFields: z.array(z.string()).optional(),
});

export const filtersDataSchema = z.object({
  available_categories: z.array(z.string()).optional(),
  selected_category_code: nullableStringSchema,
  selected_filter_values: z.record(z.string(), z.string()).optional(),
  visible_filter_fields: z.array(filterFieldSchema).optional(),
  active_filter_summary: z.array(z.string()).optional(),
  pricing_scope: z.string().optional(),
  pricing_freshness_days: z.number().optional(),
});

const pricingEvidenceSchema = z.object({
  sellerSampleCount: nullableNumberSchema,
  uniqueSellerCount: nullableNumberSchema,
  exactSpecRatio: nullableNumberSchema,
  reliabilityScore: nullableNumberSchema,
  effectiveSampleCount: nullableNumberSchema,
  recencyWeightedSampleCount: nullableNumberSchema,
  mad: nullableNumberSchema,
  confidenceScore: nullableNumberSchema,
  confidenceReasons: z.array(z.string()).optional(),
  qualityTier: nullableStringSchema,
  p15Price: nullableNumberSchema,
  p35Price: nullableNumberSchema,
  p50Price: nullableNumberSchema,
  latestSeenAt: nullableStringSchema,
  freshnessDays: nullableNumberSchema,
  templateComplete: z.boolean().optional(),
});

const pricingAvailabilitySchema = z.object({
  availabilityTier: nullableStringSchema,
  pricingAvailable: z.boolean().optional(),
  pricingBlockReason: nullableStringSchema,
  pricingEvidence: pricingEvidenceSchema.optional(),
});

const pricingContractSchema = z.object({
  categoryCode: nullableStringSchema,
  pricingKeyFields: z.array(z.string()).optional(),
  requiredPricingFields: z.array(z.string()).optional(),
  selectorFieldAliases: z.record(z.string(), z.string()).optional(),
  requiredSelectorFields: z.array(z.string()).optional(),
  optionalSelectorFields: z.array(z.string()).optional(),
  unsupportedPricingFields: z.array(z.string()).optional(),
  selectedPricingValues: z.record(z.string(), primitiveValueSchema).optional(),
  missingPricingFields: z.array(z.string()).optional(),
  templateKeyPreview: nullableStringSchema,
  templateCompleteness: z
    .object({
      status: nullableStringSchema,
      isComplete: z.boolean().optional(),
      missingFields: z.array(z.string()).optional(),
      primarySelectorField: nullableStringSchema,
    })
    .optional(),
});

export const heroDataSchema = z.object({
  overview: z
    .object({
      latest_seen: nullableStringSchema,
      active_items: nullableNumberSchema,
      stale_ratio: nullableNumberSchema,
      latest_run: z
        .object({
          display_name: nullableStringSchema,
          status: nullableStringSchema,
        })
        .nullable()
        .optional(),
      browser_session: z
        .object({
          auth_state: nullableStringSchema,
        })
        .nullable()
        .optional(),
    })
    .optional(),
});

export const pricingRowSchema = z.object({
  label: z.string(),
  product_label: nullableStringSchema,
  spec_label: nullableStringSchema,
  safe_buy_price: z.number(),
  normal_buy_price: z.number(),
  market_mid_price: z.number(),
  estimated_profit_floor: z.number(),
  estimated_profit_ceiling: z.number(),
  normal_margin_pct: nullableNumberSchema,
  safe_margin_pct: nullableNumberSchema,
  reliability_score: nullableNumberSchema,
  unique_seller_count: nullableNumberSchema,
  schema_id: nullableNumberSchema,
  effective_sample_count: nullableNumberSchema,
  recency_weighted_sample_count: nullableNumberSchema,
  confidence_score: nullableNumberSchema,
  confidence_reasons: z.array(z.string()).optional(),
  quality_tier: nullableStringSchema,
  mad: nullableNumberSchema,
  p15_price: nullableNumberSchema,
  p35_price: nullableNumberSchema,
  p50_price: nullableNumberSchema,
  dimensions: z.array(z.string()).optional(),
  opportunity_label: nullableStringSchema,
});

export const pricingDataSchema = z.object({
  pricing_panel: z
    .object({
      rows: z.array(pricingRowSchema).optional(),
      freshness_days: nullableNumberSchema,
      view_label: nullableStringSchema,
      selected_pricing_availability: pricingAvailabilitySchema.optional(),
    })
    .optional(),
  pricing_gate_summary: z
    .object({
      candidate_count: nullableNumberSchema,
      pricing_pool_count: nullableNumberSchema,
      review_gate_filtered_count: nullableNumberSchema,
    })
    .optional(),
  pricing_contract: pricingContractSchema.optional(),
  pricing_availability: pricingAvailabilitySchema.optional(),
});

export const itemSchema = z.object({
  item_id: z.string(),
  title: z.string(),
  display_name: nullableStringSchema,
  domain_label: nullableStringSchema,
  business_domain: nullableStringSchema,
  price: z.number(),
  region: nullableStringSchema,
  last_seen_at: nullableStringSchema,
  seller_name: nullableStringSchema,
  seller_id: nullableStringSchema,
  listing_url: nullableStringSchema,
  image_url: nullableStringSchema,
  heartbeat_label: nullableStringSchema,
  listing_preference: nullableStringSchema,
});

export const itemsDataSchema = z.object({
  items: z.array(itemSchema).optional(),
});

export const focusCardSchema = z.object({
  title: z.string(),
  tone: z.string().optional(),
  empty: z.boolean().optional(),
  empty_text: z.string().optional(),
  label: nullableStringSchema,
  safe_buy_price: nullableNumberSchema,
  normal_buy_price: nullableNumberSchema,
  market_mid_price: nullableNumberSchema,
  estimated_profit_label: nullableStringSchema,
  caption: nullableStringSchema,
  dimensions: z.array(z.string()).optional(),
  focus_state_label: nullableStringSchema,
  focus_state_class: nullableStringSchema,
  required_profit_amount: nullableNumberSchema,
});

export const focusDataSchema = z.object({
  market_focus_cards: z.array(focusCardSchema).optional(),
});

export const trendTickSchema = z.object({
  y: nullableNumberSchema,
  x: nullableNumberSchema,
  label: nullableStringSchema,
});

export const trendPointSchema = z.object({
  center_x: nullableNumberSchema,
  mid_y: nullableNumberSchema,
  tooltip: nullableStringSchema,
});

export const trendCardSchema = z.object({
  label: z.string(),
  domain_label: nullableStringSchema,
  latest_close: nullableNumberSchema,
  change_class: nullableStringSchema,
  change_label: nullableStringSchema,
  volatility_label: nullableStringSchema,
  chart_width: nullableNumberSchema,
  chart_height: nullableNumberSchema,
  aria_label: nullableStringSchema,
  price_ticks: z.array(trendTickSchema).optional(),
  date_ticks: z.array(trendTickSchema).optional(),
  trend_points: z.array(trendPointSchema).optional(),
  trend_upper_path: nullableStringSchema,
  trend_lower_path: nullableStringSchema,
  trend_line_path: nullableStringSchema,
  latest_range_label: nullableStringSchema,
  latest_sample_count: nullableNumberSchema,
  seller_sample_count: nullableNumberSchema,
});

export const domainCardSchema = z.object({
  label: z.string(),
  business_domain: nullableStringSchema,
  signal_class: nullableStringSchema,
  signal_label: nullableStringSchema,
  active_count: nullableNumberSchema,
  stale_count: nullableNumberSchema,
  avg_price: nullableNumberSchema,
  last_seen_at: nullableStringSchema,
});

export const insightsDataSchema = z.object({
  overview: z
    .object({
      scope_label: nullableStringSchema,
      window_days: nullableNumberSchema,
      stale_ratio: nullableNumberSchema,
      latest_seen: nullableStringSchema,
      active_items: nullableNumberSchema,
      total_sellers: nullableNumberSchema,
      latest_run: z
        .object({
          display_name: nullableStringSchema,
          status: nullableStringSchema,
        })
        .nullable()
        .optional(),
    })
    .optional(),
  domain_trend_cards: z.array(trendCardSchema).optional(),
  domain_cards: z.array(domainCardSchema).optional(),
});

export const calibrationRowSchema = z.object({
  model_name: z.string(),
  domain_label: nullableStringSchema,
  calibration_class: nullableStringSchema,
  calibration_label: nullableStringSchema,
  listed_avg_price: nullableNumberSchema,
  sold_anchor_price: nullableNumberSchema,
  visible_record_count: nullableNumberSchema,
  calibration_detail: nullableStringSchema,
});

export const calibrationDataSchema = z.object({
  mobile_market_panel: z
    .object({
      available: z.boolean().optional(),
      captured_model_count: nullableNumberSchema,
      latest_captured_at: nullableStringSchema,
      rows: z.array(calibrationRowSchema).optional(),
    })
    .optional(),
  top_models: z
    .array(
      z.object({
        model_name: z.string(),
        domain_label: nullableStringSchema,
        listing_count: nullableNumberSchema,
        avg_price: nullableNumberSchema,
        last_seen_at: nullableStringSchema,
        mobile_calibration: z
          .object({
            sold_anchor_price: nullableNumberSchema,
          })
          .nullable()
          .optional(),
      }),
    )
    .optional(),
});

export const dashboardSectionSchemas = {
  hero: heroDataSchema,
  filters: filtersDataSchema,
  pricing: pricingDataSchema,
  items: itemsDataSchema,
  focus: focusDataSchema,
  insights: insightsDataSchema,
  calibration: calibrationDataSchema,
} as const;
