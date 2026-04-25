# Goofish Insight W11 Entrypoint & Legacy Spec Audit

Date: 2026-04-14
Scope: W11 engineering closure after the first collector service extraction pass.
Updated: 2026-04-16 after the home-feed rules service extraction pass.

## Executive Summary

W11 is partially complete, but the CLI entrypoint layer is not yet a pure parameter-parse-and-dispatch layer.

Completed extraction:

- `collector_browser.py`: browser/risk-control/auth-state helpers.
- `collector_runs.py`: crawl-run finalization and progress helpers.
- `collector_ingest.py`: snapshot insert gating and timestamp updates.
- `collector_runtime.py`: job-run and checkpoint writes.
- `collector_batch_runtime.py`: batch cursor, host lock, quality metrics, risk backoff, risk event logging, and risk summaries.
- `review_output_artifacts.py`: review usage summary, sidecar output, calibration output paths, and chunk iteration.
- `review_second_pass.py`: second-pass local AI default fallback helper.
- `pricing_reporting.py`: model discovery report writing, pricing availability annotation, template-mode smoke, and smoke HTTP helpers.
- `pricing_entrypoints.py`: baseline date parsing helper for pricing commands.
- `home_feed_rules.py`: home-feed target matching, seller classification, message formatting, and detail URL helpers.

Current residual risk:

- `cli.py` is down from 5,186 lines to 4,185 lines, but still has 103 top-level functions/classes.
- `entrypoints/cli/collect.py` is down from 1,140 lines to 298 lines after batch runtime helper extraction.
- `entrypoints/cli/review.py` is down from 702 lines to 440 lines after review output and second-pass helper extraction.
- `entrypoints/cli/pricing.py` is down from 703 lines to 261 lines after pricing report/smoke and baseline parsing helper extraction.

Conclusion: the command-registration split has already happened, but the business/helper logic split is not finished. Treat entrypoint purity as not yet passed.

## Entrypoint Purity Check

Line counts:

| File | Lines | Finding |
| --- | ---: | --- |
| `apps/collector/src/goofish_insight/entrypoints/cli/collect.py` | 298 | Improved. Now only exposes `register_collect_commands`; still contains relatively heavy collect-batch orchestration inside the command body. |
| `apps/collector/src/goofish_insight/entrypoints/cli/review.py` | 440 | Improved. Output/sidecar/chunk helpers moved; now only owns command orchestration, with local AI fallback moved to service layer. |
| `apps/collector/src/goofish_insight/entrypoints/cli/pricing.py` | 261 | Improved. Report/smoke/client helpers moved; now mostly command facade plus service-level baseline-date parsing. |
| `apps/collector/src/goofish_insight/entrypoints/cli/admin.py` | 892 | Large, but mostly command facade over catalog services; lower priority than collect/review/pricing. |
| `apps/collector/src/goofish_insight/entrypoints/cli/maintenance.py` | 167 | Acceptable. |
| `apps/collector/src/goofish_insight/entrypoints/cli/feed.py` | 135 | Acceptable for now. |
| `apps/collector/src/goofish_insight/entrypoints/cli/mobile.py` | 91 | Acceptable. |

Top-level helper/function hotspots in entrypoints:

- `collect.py`: helper functions moved out; remaining hotspot is the large `collect_batch` command body itself.
- `review.py`: output and chunk helpers moved out; remaining hotspot is command orchestration only.
- `pricing.py`: report/smoke helpers moved out; remaining helper logic is gone from the entrypoint.

Recommended next extraction batches:

1. Extract the `collect_batch` orchestration body into a service-level use case after W1 checkpoint semantics stabilize.
2. Keep `review.py` unchanged unless a new orchestration hotspot emerges.
3. Keep `pricing.py` unchanged; its remaining logic is now just command wiring.
4. Keep `home_feed_rules.py` as the reusable compatibility boundary for future feed-specific extractions instead of moving more feed logic back into `cli.py`.

## Legacy `item_spec_enrichments` Field Audit

Legacy columns under audit:

| Field | Reference Count | Role |
| --- | ---: | --- |
| `case_size_mm` | 84 | Garmin-specific size identity and pricing selector. |
| `is_solar` | 78 | Garmin-specific edition selector. |
| `display_type` | 85 | Garmin-specific display selector. |
| `screen_size_in` | 86 | Apple/Mac screen selector and generic template attr bridge. |
| `chip_family` | 110 | Apple/Mac chip selector and normalized item fallback. |
| `cpu_model` | 25 | Apple/Mac detail field, lower usage. |
| `cpu_cores` | 49 | Apple/Mac detail field, lower usage. |
| `gpu_cores` | 49 | Apple/Mac detail field, lower usage. |
| `memory_gb` | 124 | Apple/Mac SKU selector and normalized item fallback. |
| `storage_gb` | 135 | Apple/Mac SKU selector and normalized item fallback. |

Main read/write surfaces:

- `models.py`: physical legacy columns on `ItemSpecEnrichment`.
- `specs.py`: extraction candidate fields, rule extraction, LLM merge, catalog bridge fallback, payload parsing.
- `pricing.py`: summary and selector construction for old dashboard pricing paths.
- `presentation/web.py`: legacy UI field labels, filter order, field-specific option mapping.
- `domain/review/contracts.py`: review payload contract still exposes `spec.*` legacy field names.
- `cli.py`: upsert and backfill paths still write legacy columns.
- `normalizers.py`: normalized item memory/storage helpers remain outside catalog attr model.

Conclusion: these fields cannot be removed in this upgrade phase. They are still an active compatibility layer for Garmin and Apple dashboards, review contracts, pricing summaries, and CLI backfills.

## Recommended Legacy Column Strategy

Do not drop columns yet. Instead:

1. Treat the legacy columns as derived compatibility fields.
2. Write new category-specific attributes to catalog tables first where the category template supports them.
3. Continue writing legacy columns from the same extraction payload until W7 catalog read-path coverage and consistency gates are satisfied.
4. Add a follow-up migration only after dashboard/pricing/review readers use template attributes as the primary source.
5. Add a compatibility contract test before deprecating any field: same input item should produce the same dashboard selector labels from old legacy columns and new catalog attributes.

## W11 Completion Status

Passed:

- First collector service extraction exists and selected tests pass.
- `collect.py` batch cursor/risk helper extraction exists and selected integration passes.
- `review.py` output helper and second-pass AI fallback extraction exist and selected integration passes.
- `pricing.py` reporting/smoke helper and baseline parsing extraction exist and selected integration passes.
- `home_feed_rules.py` extraction exists and selected feed/runtime integration passes.
- `specs.py` and `pricing.py` debt are quantified at file level.
- Legacy field usage is audited.
- Windows path residue cleanup is staged.

Not passed yet:

- Entrypoints are not pure dispatchers.
- `cli.py` still holds 103 top-level functions/classes.
- Legacy spec columns remain active compatibility fields.

Next smallest safe step:

Keep entrypoint extraction paused until W1/W8 runtime metrics have a little more soak time; the next W11 move should be a targeted `cli.py` orchestration body, not another broad helper pass.
