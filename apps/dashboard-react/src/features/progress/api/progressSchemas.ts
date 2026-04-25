import { z } from 'zod';

const nullableStringSchema = z.string().nullable().optional();
const nullableNumberSchema = z.number().nullable().optional();

export const progressOverviewSchema = z.object({
  domain_count: z.number().optional(),
  pending_review_count: z.number().optional(),
  in_progress_count: z.number().optional(),
  pending_audit_count: z.number().optional(),
  reviewed_valid_count: z.number().optional(),
  reviewed_invalid_count: z.number().optional(),
  reviewed_total: z.number().optional(),
  review_target_total: z.number().optional(),
  completion_percent: z.number().optional(),
  last_reviewed_at: nullableStringSchema,
});

export const progressHeaderSchema = z.object({
  selected_domain: nullableStringSchema,
  selected_category_code: nullableStringSchema,
  available_domains: z.array(z.string()).optional(),
  available_categories: z.array(z.string()).optional(),
  review_overview: progressOverviewSchema.optional(),
  current_ai_provider: nullableStringSchema,
  current_ai_model: nullableStringSchema,
});

export const progressRowSchema = z.object({
  business_domain: z.string(),
  label: z.string(),
  total_items: z.number().optional(),
  active_items: z.number().optional(),
  pending_review_count: z.number().optional(),
  in_progress_count: z.number().optional(),
  pending_audit_count: z.number().optional(),
  reviewed_valid_count: z.number().optional(),
  reviewed_invalid_count: z.number().optional(),
  reviewed_total: z.number().optional(),
  inactive_invalid_count: z.number().optional(),
  review_target_total: z.number().optional(),
  completion_percent: z.number().optional(),
  last_reviewed_at: nullableStringSchema,
});

export const progressOverviewSectionSchema = z.object({
  review_overview: progressOverviewSchema.optional(),
  review_progress_rows: z.array(progressRowSchema).optional(),
});

export const usageRunSchema = z.object({
  file_name: z.string(),
  pipeline: z.string(),
  business_domain: nullableStringSchema,
  domain_label: nullableStringSchema,
  generated_at: nullableStringSchema,
  request_count: z.number().optional(),
  batch_count: z.number().optional(),
  requested_item_count: z.number().optional(),
  input_tokens: z.number().optional(),
  output_tokens: z.number().optional(),
  total_tokens: z.number().optional(),
  cached_tokens: z.number().optional(),
  garbage_hit_count: z.number().optional(),
  low_confidence_filtered_count: z.number().optional(),
  high_confidence_kept_count: z.number().optional(),
  second_pass_requested_count: z.number().optional(),
  second_pass_rescued_count: z.number().optional(),
  second_pass_unresolved_count: z.number().optional(),
});

export const workerEventSchema = z.object({
  event: z.string().optional(),
  title: z.string().optional(),
  summary: z.string().optional(),
  status_class: z.string().optional(),
});

export const workerRunSchema = z.object({
  run_type: z.string().optional(),
  pipeline: z.string().optional(),
  business_domain: nullableStringSchema,
  domain_label: nullableStringSchema,
  log_name: z.string().optional(),
  updated_at: nullableStringSchema,
  is_recent: z.boolean().nullable().optional(),
  worker_label: nullableStringSchema,
  ai_provider: nullableStringSchema,
  ai_model: nullableStringSchema,
  worker_count: nullableNumberSchema,
  batch_size: nullableNumberSchema,
  pending_reviews: nullableNumberSchema,
  requested_item_count: nullableNumberSchema,
  recent_events: z.array(workerEventSchema).optional(),
});

export const usageSummarySchema = z.object({
  file_count: z.number().optional(),
  request_count: z.number().optional(),
  input_tokens: z.number().optional(),
  output_tokens: z.number().optional(),
  total_tokens: z.number().optional(),
  cached_tokens: z.number().optional(),
  garbage_hit_count: z.number().optional(),
  low_confidence_filtered_count: z.number().optional(),
  high_confidence_kept_count: z.number().optional(),
  second_pass_requested_count: z.number().optional(),
  second_pass_rescued_count: z.number().optional(),
  second_pass_unresolved_count: z.number().optional(),
  last_generated_at: nullableStringSchema,
  recent_usage_runs: z.array(usageRunSchema).optional(),
});

export const progressUsageWorkersSectionSchema = z.object({
  usage_summary: usageSummarySchema.optional(),
  worker_runs: z.array(workerRunSchema).optional(),
});

export const progressAuditQueueRowSchema = z.object({
  item_id: z.string().optional(),
  business_domain: z.string().optional(),
  domain_label: z.string().optional(),
  title: z.string().optional(),
  audit_reason: nullableStringSchema,
  confidence: nullableNumberSchema,
  decision_status: nullableStringSchema,
  invalid_reason: nullableStringSchema,
  field_change_count: z.number().optional(),
  reviewed_at: nullableStringSchema,
});

export const progressInvalidReasonRowSchema = z.object({
  business_domain: z.string().optional(),
  domain_label: z.string().optional(),
  reason: z.string().optional(),
  item_count: z.number().optional(),
  last_reviewed_at: nullableStringSchema,
});

export const progressAuditsSectionSchema = z.object({
  audit_queue_rows: z.array(progressAuditQueueRowSchema).optional(),
  invalid_reason_rows: z.array(progressInvalidReasonRowSchema).optional(),
});
