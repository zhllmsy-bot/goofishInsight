import { z } from 'zod';

const nullableStringSchema = z.string().nullable().optional();
const nullableNumberSchema = z.number().nullable().optional();
const nullableBooleanSchema = z.boolean().nullable().optional();

export const llmTraceUsageSchema = z.object({
  input_tokens: z.number().optional(),
  output_tokens: z.number().optional(),
  total_tokens: z.number().optional(),
  cached_tokens: z.number().optional(),
});

export const llmTraceSummarySchema = z.object({
  trace_key: z.string(),
  file_name: z.string(),
  generated_at: nullableStringSchema,
  provider: nullableStringSchema,
  model: nullableStringSchema,
  method: nullableStringSchema,
  url: nullableStringSchema,
  status: nullableStringSchema,
  error: nullableStringSchema,
  latency_ms: z.number().nullable().optional(),
  item_id: nullableStringSchema,
  usage: llmTraceUsageSchema.nullable().optional(),
});

export const llmTraceMessageSchema = z.object({
  index: z.number(),
  role: z.string(),
  content_text: nullableStringSchema,
  content_preview: nullableStringSchema,
});

export const llmTraceDetailSchema = z.object({
  trace_key: z.string(),
  file_name: z.string(),
  generated_at: nullableStringSchema,
  provider: nullableStringSchema,
  model: nullableStringSchema,
  url: nullableStringSchema,
  method: nullableStringSchema,
  status: nullableStringSchema,
  message_count: z.number(),
  messages: z.array(llmTraceMessageSchema),
  request_headers_json: z.string().optional(),
  request_payload_json: z.string().optional(),
  response_payload_json: z.string().optional(),
  raw_json: z.string().optional(),
  error: nullableStringSchema,
  latency_ms: z.number().nullable().optional(),
  item_id: nullableStringSchema,
  usage: llmTraceUsageSchema.nullable().optional(),
  reasoning_content: z.string().optional(),
});

export const llmTraceSectionSchema = z.object({
  trace_enabled: z.boolean().optional(),
  trace_dir: z.string().optional(),
  trace_count: z.number().optional(),
  traces: z.array(llmTraceSummarySchema).optional(),
  latest_trace: llmTraceDetailSchema.nullable().optional(),
});

export const llmTraceDetailResponseSchema = z.object({
  trace: llmTraceDetailSchema.nullable(),
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
  is_recent: nullableBooleanSchema,
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

export const usageWorkersSectionSchema = z.object({
  usage_summary: usageSummarySchema.optional(),
  worker_runs: z.array(workerRunSchema).optional(),
});
