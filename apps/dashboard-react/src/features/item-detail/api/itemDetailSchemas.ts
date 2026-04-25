import { z } from 'zod';

const nullableStringSchema = z.string().nullable().optional();
const nullableNumberSchema = z.number().nullable().optional();
const nullableBooleanSchema = z.boolean().nullable().optional();

export const itemDetailRecordSchema = z.object({
  item_id: z.string(),
  title: z.string(),
  business_domain: nullableStringSchema,
  categoryCode: nullableStringSchema,
  categoryName: nullableStringSchema,
  domain_label: nullableStringSchema,
  price: nullableNumberSchema,
  region: nullableStringSchema,
  publish_time: nullableStringSchema,
  first_seen_at: nullableStringSchema,
  last_seen_at: nullableStringSchema,
  listing_url: nullableStringSchema,
  image_urls: z.array(z.string()).optional(),
  condition_tags: z.array(z.string()).optional(),
  normalized_brand: nullableStringSchema,
  normalized_model_family: nullableStringSchema,
  normalized_model: nullableStringSchema,
  normalized_chip: nullableStringSchema,
  normalized_memory_gb: nullableNumberSchema,
  normalized_storage_gb: nullableNumberSchema,
  source_keyword: nullableStringSchema,
  task_display_name: nullableStringSchema,
  raw_response_id: nullableStringSchema,
  has_video: nullableBooleanSchema,
  is_ad: nullableBooleanSchema,
});

export const itemDetailSpecSchema = z.object({
  status: nullableStringSchema,
  confidence: nullableNumberSchema,
  extractor_type: nullableStringSchema,
  product_line: nullableStringSchema,
  model_name: nullableStringSchema,
  generation: nullableStringSchema,
  case_size_mm: nullableNumberSchema,
  is_solar: nullableBooleanSchema,
  display_type: nullableStringSchema,
  screen_size_in: nullableNumberSchema,
  chip_family: nullableStringSchema,
  cpu_cores: nullableNumberSchema,
  gpu_cores: nullableNumberSchema,
  memory_gb: nullableNumberSchema,
  storage_gb: nullableNumberSchema,
  edition_tags: z.array(z.string()).optional(),
  needs_review: nullableBooleanSchema,
});

export const itemDetailSellerSchema = z.object({
  seller_name: nullableStringSchema,
  seller_id: nullableStringSchema,
  region: nullableStringSchema,
});

export const itemDetailSnapshotSchema = z.object({
  snapshot_at: nullableStringSchema,
  price: nullableNumberSchema,
  region: nullableStringSchema,
  publish_time: nullableStringSchema,
  condition_tags: z.array(z.string()).optional(),
  extra_json: z.record(z.string(), z.unknown()).optional(),
});

export const itemDetailSchema = z.object({
  item: itemDetailRecordSchema,
  spec: itemDetailSpecSchema.nullable().optional(),
  seller: itemDetailSellerSchema.optional(),
  snapshots: z.array(itemDetailSnapshotSchema).optional(),
  raw_response_body: nullableStringSchema,
});
