# W6 business_domain -> category Migration Plan

Date: 2026-04-14
Status: implementation planning / do not batch-edit all files at once

## Goal

Make `category_id` the primary business scope for new read/write paths, while keeping `business_domain` as a compatibility shell until dashboard, review, and pricing paths are migrated and verified.

## Current Hotspot Count

Measured with a direct source scan under `apps/collector/src/goofish_insight` on 2026-04-14.

| rank | file | business_domain refs | category_id refs | migration note |
|---:|---|---:|---:|---|
| 1 | `application/services/review_progress_page.py` | 119 | 0 | progress page is still fully domain scoped; migrate section options to category_code/category_id first |
| 2 | `application/services/review_v3_pipeline.py` | 112 | 32 | keep compatibility until review-v3 run contracts are stable |
| 3 | `cli.py` | 111 | 94 | do not edit directly except mechanical extraction; use service moves first |
| 4 | `application/services/dashboard_queries.py` | 78 | 0 | dashboard read path; high value but needs contract tests |
| 5 | `application/services/catalog_backfill.py` | 77 | 92 | already category-aware; migrate local scope variables gradually |
| 6 | `application/services/xianyu_category_mapping.py` | 65 | 15 | category onboarding path; migrate after dashboard/pricing are stable |
| 7 | `pricing.py` | 65 | 6 | pricing read model; start here for W6 because blast radius is bounded |
| 8 | `entrypoints/cli/admin.py` | 45 | 26 | CLI compatibility wrapper; migrate after services expose category-first contracts |
| 9 | `application/services/review_calibration.py` | 34 | 0 | review analytics; can follow review_progress_page |
| 10 | `application/services/dashboard_sections.py` | 34 | 0 | section facade; migrate with dashboard_queries |

## Recommended PR Order

1. `pricing.py` category-first wrapper

- Add a `category_code/category_id` input path next to existing `business_domain`.
- Internally resolve scope with `category_compat.resolve_category_code` only at the boundary.
- Keep output payload unchanged.
- Contract tests: price bands for existing Apple/Garmin examples must match old domain path.

2. `dashboard_queries.py` read-path migration

- Add category-first filtering to the query builders.
- Keep `business_domain` request parameter as an alias in entrypoints.
- Contract tests: hero/filters/pricing/items sections should match for `business_domain=apple_computer` and `category_code=apple_computer`.

3. `dashboard_sections.py` facade cleanup

- Rename internal variables from domain to scope/category where the value already holds `category_code or business_domain`.
- Do not change API response keys in this step.

4. `catalog_backfill.py` local variable cleanup

- It already has many `category_id` references; focus on replacing remaining local branch decisions that still use `business_domain`.
- Avoid touching persistence semantics in the same PR.

5. Review paths after dashboard/pricing are stable

- `review_progress_page.py`, `review_v3_pipeline.py`, and `review_calibration.py` should be migrated behind a compatibility adapter because they are operationally sensitive.

## Guardrails

- No broad search/replace.
- One core file per PR.
- Every migrated file gets at least one compatibility test: old `business_domain` input and new `category_code/category_id` input return equivalent business payloads.
- Do not remove `category_compat.py` until Phase 3 has at least one full week of dashboard/pricing parity.

## Next Concrete Step

Start W6 with `pricing.py` only:

- identify public functions that accept `business_domain`
- add category-first input parameters without removing the old parameter
- add parity tests around existing price band builders

## T5 Category/Admin Scope Closeout (2026-04-15)

### What was closed

- Admin/backfill entrypoints now prefer canonical `category_code` as the primary scope argument.
- Legacy `--business-domain` remains as a compatibility alias at CLI boundaries.
- Scope normalization at admin boundary is now explicit:
  canonicalize known aliases via `resolve_category_code`
  reject conflicting dual inputs (`category_code` vs `--business-domain`)
  reject empty scope input early

### Compatibility and retirement path

- `category_compat.py` keeps alias mapping for runtime compatibility in Phase 2/3.
- New admin entrypoints must not add business-domain-only parameters.
- Existing compatibility alias can be removed only after:
  one full week of category-first parity for dashboard/pricing with no P1 regressions
  admin/backfill automation no longer using business-domain-only arguments
  catalog dual-read contract and rollback checks staying green after cutover

### Follow-up

- Continue migrating remaining service-level APIs from `business_domain` naming to explicit `category_code/category_id`.
- Once all call sites are category-first, delete compatibility alias flags from admin CLI in a dedicated cleanup PR.
