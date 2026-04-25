-- 商品属性系统 PostgreSQL DDL 草案
-- 说明：
-- 1. 本文件用于详细设计和评审，不直接等同于最终生产迁移脚本
-- 2. 当前仓库为 Python/FastAPI/SQLAlchemy 项目，后续应以 Alembic 迁移形式正式落库

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'attribute_data_type') THEN
    CREATE TYPE attribute_data_type AS ENUM ('TEXT', 'NUMBER', 'BOOLEAN', 'ENUM', 'JSON');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'attribute_scope_type') THEN
    CREATE TYPE attribute_scope_type AS ENUM ('PLATFORM', 'MERCHANT', 'CHANNEL');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'attribute_status') THEN
    CREATE TYPE attribute_status AS ENUM ('DRAFT', 'ACTIVE', 'DEPRECATED', 'DISABLED');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'template_status') THEN
    CREATE TYPE template_status AS ENUM ('DRAFT', 'PUBLISHED', 'RETIRED');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'product_status') THEN
    CREATE TYPE product_status AS ENUM ('DRAFT', 'ACTIVE', 'INACTIVE', 'ARCHIVED');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'outbox_status') THEN
    CREATE TYPE outbox_status AS ENUM ('PENDING', 'PROCESSING', 'DONE', 'FAILED', 'DEAD');
  END IF;
END
$$;

CREATE TABLE IF NOT EXISTS category (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  parent_id UUID REFERENCES category(id),
  code VARCHAR(64) NOT NULL UNIQUE,
  name VARCHAR(128) NOT NULL,
  path VARCHAR(512) NOT NULL,
  level SMALLINT NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS attribute_definition (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_type attribute_scope_type NOT NULL DEFAULT 'PLATFORM',
  scope_id VARCHAR(64) NOT NULL DEFAULT 'platform',
  code VARCHAR(64) NOT NULL,
  name VARCHAR(128) NOT NULL,
  data_type attribute_data_type NOT NULL,
  value_scope VARCHAR(16) NOT NULL CHECK (value_scope IN ('SPU', 'SKU')),
  is_multi BOOLEAN NOT NULL DEFAULT FALSE,
  unit VARCHAR(32),
  validation_schema JSONB,
  status attribute_status NOT NULL DEFAULT 'DRAFT',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (scope_type, scope_id, code)
);

CREATE TABLE IF NOT EXISTS attribute_option (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  attribute_id UUID NOT NULL REFERENCES attribute_definition(id),
  option_code VARCHAR(64) NOT NULL,
  option_name VARCHAR(128) NOT NULL,
  sort_no INT NOT NULL DEFAULT 0,
  status attribute_status NOT NULL DEFAULT 'ACTIVE',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (attribute_id, option_code)
);

CREATE TABLE IF NOT EXISTS category_attr_template (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id UUID NOT NULL REFERENCES category(id),
  version INT NOT NULL,
  status template_status NOT NULL DEFAULT 'DRAFT',
  effective_at TIMESTAMPTZ,
  published_by VARCHAR(64),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (category_id, version)
);

CREATE TABLE IF NOT EXISTS category_attr_template_item (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  template_id UUID NOT NULL REFERENCES category_attr_template(id),
  attribute_id UUID NOT NULL REFERENCES attribute_definition(id),
  is_required BOOLEAN NOT NULL DEFAULT FALSE,
  is_sale BOOLEAN NOT NULL DEFAULT FALSE,
  is_filter BOOLEAN NOT NULL DEFAULT FALSE,
  is_search BOOLEAN NOT NULL DEFAULT FALSE,
  is_display BOOLEAN NOT NULL DEFAULT TRUE,
  sort_no INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (template_id, attribute_id)
);

CREATE TABLE IF NOT EXISTS product_spu (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  category_id UUID NOT NULL REFERENCES category(id),
  template_id UUID NOT NULL REFERENCES category_attr_template(id),
  merchant_id VARCHAR(64),
  brand_id VARCHAR(64),
  title VARCHAR(256) NOT NULL,
  status product_status NOT NULL DEFAULT 'DRAFT',
  attr_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_sku (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  spu_id UUID NOT NULL REFERENCES product_spu(id),
  sku_code VARCHAR(64) NOT NULL,
  sales_signature_raw TEXT NOT NULL,
  sales_signature_hash VARCHAR(128) NOT NULL,
  price NUMERIC(18, 2) NOT NULL DEFAULT 0,
  stock INT NOT NULL DEFAULT 0,
  barcode VARCHAR(64),
  status product_status NOT NULL DEFAULT 'DRAFT',
  attr_snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (sku_code),
  UNIQUE (spu_id, sales_signature_hash)
);

CREATE TABLE IF NOT EXISTS product_spu_attr_value (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  spu_id UUID NOT NULL REFERENCES product_spu(id),
  attribute_id UUID NOT NULL REFERENCES attribute_definition(id),
  value_seq INT NOT NULL DEFAULT 0,
  text_value TEXT,
  number_value NUMERIC(18, 6),
  normalized_number_value NUMERIC(18, 6),
  bool_value BOOLEAN,
  option_id UUID REFERENCES attribute_option(id),
  json_value JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (spu_id, attribute_id, value_seq),
  CHECK (
    ((text_value IS NOT NULL)::INT +
     (number_value IS NOT NULL)::INT +
     (bool_value IS NOT NULL)::INT +
     (option_id IS NOT NULL)::INT +
     (json_value IS NOT NULL)::INT) = 1
  )
);

CREATE TABLE IF NOT EXISTS product_sku_attr_value (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sku_id UUID NOT NULL REFERENCES product_sku(id),
  attribute_id UUID NOT NULL REFERENCES attribute_definition(id),
  value_seq INT NOT NULL DEFAULT 0,
  text_value TEXT,
  number_value NUMERIC(18, 6),
  normalized_number_value NUMERIC(18, 6),
  bool_value BOOLEAN,
  option_id UUID REFERENCES attribute_option(id),
  json_value JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (sku_id, attribute_id, value_seq),
  CHECK (
    ((text_value IS NOT NULL)::INT +
     (number_value IS NOT NULL)::INT +
     (bool_value IS NOT NULL)::INT +
     (option_id IS NOT NULL)::INT +
     (json_value IS NOT NULL)::INT) = 1
  )
);

CREATE TABLE IF NOT EXISTS outbox_event (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type VARCHAR(64) NOT NULL,
  aggregate_type VARCHAR(64) NOT NULL,
  aggregate_id UUID NOT NULL,
  event_version INT NOT NULL DEFAULT 1,
  payload JSONB NOT NULL,
  status outbox_status NOT NULL DEFAULT 'PENDING',
  retry_count INT NOT NULL DEFAULT 0,
  last_error TEXT,
  next_retry_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS product_attr_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operator_id VARCHAR(64) NOT NULL,
  resource_type VARCHAR(64) NOT NULL,
  resource_id VARCHAR(64) NOT NULL,
  action VARCHAR(64) NOT NULL,
  before_json JSONB,
  after_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
