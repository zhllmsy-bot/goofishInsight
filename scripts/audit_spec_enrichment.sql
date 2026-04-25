-- Spec enrichment quality audit (safe read-only)
--
-- Usage:
--   psql "$DATABASE_URL" -f scripts/audit_spec_enrichment.sql
--
-- Notes:
-- - This file is intentionally read-only.
-- - Thresholds are conservative and designed to highlight obvious garbage.

\echo '## item_spec_enrichments summary'
select
  count(*) as total,
  count(*) filter (where extractor_type = 'llm_review') as llm_review_rows,
  count(*) filter (where extractor_type = 'rule') as rule_rows,
  count(*) filter (where extractor_type = 'hybrid') as hybrid_rows
from item_spec_enrichments;

\echo '## by business_domain'
select business_domain, count(*) as rows
from item_spec_enrichments
group by 1
order by rows desc, business_domain;

\echo '## status distribution'
select status, count(*) as rows
from item_spec_enrichments
group by 1
order by rows desc, status;

\echo '## empty enrichment (all core fields null)'
select count(*) as empty_core_fields
from item_spec_enrichments
where nullif(trim(coalesce(brand,'')),'') is null
  and nullif(trim(coalesce(model_name,'')),'') is null
  and nullif(trim(coalesce(product_line,'')),'') is null
  and nullif(trim(coalesce(model_family,'')),'') is null
  and nullif(trim(coalesce(generation,'')),'') is null
  and case_size_mm is null
  and screen_size_in is null
  and nullif(trim(coalesce(chip_family,'')),'') is null
  and memory_gb is null
  and storage_gb is null;

\echo '## obvious out-of-range numeric values'
select
  count(*) filter (where screen_size_in is not null and (screen_size_in <= 0 or screen_size_in > 30)) as bad_screen_size,
  count(*) filter (where case_size_mm is not null and (case_size_mm <= 0 or case_size_mm > 80)) as bad_case_size,
  count(*) filter (where memory_gb is not null and (memory_gb <= 0 or memory_gb > 256)) as bad_memory,
  count(*) filter (where storage_gb is not null and (storage_gb <= 0 or storage_gb > 8192)) as bad_storage
from item_spec_enrichments;

\echo '## domain mismatch between item and enrichment'
select count(*) as domain_mismatch
from item_spec_enrichments e
join items i on i.id = e.item_id_ref
where i.business_domain <> e.business_domain;

