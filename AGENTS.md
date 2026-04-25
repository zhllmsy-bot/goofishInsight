# Goofish Insight AGENTS

## Read This First

- Check live runtime state from the exact CLI subcommand, not from screenshots, stale logs, or old report filenames.
- Query OpenViking first when you need project memory or historical context.
- After changing service-layer code, run the relevant tests before reporting success.
- Treat `python -m goofish_insight.cli` as the canonical local entrypoint.
- Treat [docs/23-best-practice-architecture-implementation-spec.md](<repo-root>/docs/23-best-practice-architecture-implementation-spec.md) as the current best-practice architecture baseline when changing data contracts, resident jobs, pricing eligibility, or runtime controls.

## Project Purpose

Goofish Insight is a category-driven second-hand market intelligence and buy-side decision system for Goofish.

Current main business goal:

- continuously capture target categories
- normalize listings into reusable product records
- build fair-price and buy-zone baselines
- surface actionable buying opportunities
- keep historical snapshots for trend analysis and human review

Current focus categories:

- Apple computers
- Garmin watches
- selected camera categories during onboarding or spot analysis

## Current System Shape

The project is still a modular monolith centered in `apps/collector`.

Main layers:

1. `apps/collector`
   Collection, ingestion, review, spec enrichment, dashboard APIs, runtime controls, and buy-side services.
2. `apps/web`
   Templates and static assets for the internal dashboard.
3. `apps/analyzer`
   Future destination for heavier analysis jobs. Some buy-side analysis still lives in `collector` today.
4. `infra`
   Launchd, PostgreSQL bootstrap, and deployment assets.
5. `scripts`
   Operational wrappers for local runtime, review workers, and one-shot smoke runs.

Within `apps/collector/src/goofish_insight`:

- `entrypoints`: CLI and FastAPI registration
- `application`: orchestration and read-model services
- `domain`: reusable rules, policies, and contracts
- `presentation`: display labels and Jinja helpers
- root modules such as `cli.py`, `pricing.py`, and `specs.py` still contain important runtime logic

## Data Contracts That Matter Now

- Historical market memory lives in `items` plus `item_snapshots`.
- Trend charts should use historical `item_snapshots`, not only the current freshness window.
- Permanent garbage filtering uses `item_ingest_rejection` tombstones with minimal fields only. Keep `item_id`, source identity, rejection reason, and counters; do not keep full listing bodies for permanent garbage rows.
- `items.title_tokens` is retired. Do not add `title_tokens` or `titleToken` back into schema, prompts, outputs, traces, or dashboards.
- LLM prompts should receive only fields that the model actually needs. Do not ask the model to echo unchanged input fields.
- `seller_profiles.metadata_json.sellerType` is a heuristic classification only: `commercial_like`, `private_like`, or `unknown`. It is not a platform-truth merchant flag.

## Review And Cleaning Principles

- Use deterministic rules first.
- Use LLM review only for ambiguity, low-confidence cleanup, or structured extraction gaps.
- Hard garbage rules should stay conservative. Generic words like `表盘`, `表带`, or `地图服务` can appear inside valid Garmin listings and must not be treated as automatic garbage by keyword alone.
- Very long spam titles are permanent garbage candidates. Current hard cutoff: title length greater than `500`.
- When a listing is permanently rejected at ingest, keep only the minimal tombstone row needed for future filtering.

## Runtime Principles

- Prefer attached, logged-in Chrome sessions for Goofish collection.
- Use resident local services for dashboard, feed watch, and batch collection when continuous operation is needed.
- Do not conflate feed monitoring with search collection.
- Raw request or response payloads may be pruned after ingest; structured history must remain queryable.
- When using a remote model provider, always inspect the run sidecars before blaming the data. Transport, billing, or auth failures can masquerade as low confidence.
- Resident jobs must be convergent. Every long-running worker should have a bounded candidate set, repeat-result freeze behavior, no-progress backoff, and an operator-visible stop path.
- Report resident progress using deduplicated business output such as unique item count, new `complete` rows, or new pricing-eligible rows. Do not present retry counts as business progress.

## Model Provider Contract

Local default:

- provider: `openai_compatible`
- base URL: `http://127.0.0.1:8000/v1`

Ark compatibility layer is available for one-shot review cleaning:

- OpenAI-compatible base: `https://ark.cn-beijing.volces.com/api/coding/v3`
- Anthropic-compatible base: `https://ark.cn-beijing.volces.com/api/coding`
- wrapper: `scripts/run-ark-review-cleaning.sh`

If a remote Ark run returns `0` tokens and unresolved items, inspect the `.low-confidence.json` sidecar first. That usually means transport, auth, or billing failure rather than model indecision.

## Command Contract

Report live work as `PID <pid> | <subcommand> | <meaning>`.

Job meanings:

- `collect-search` / `collect-batch` / `run-discovery`: search-result collection
- `refresh-home-feed` / `watch-home-feed`: homepage feed monitoring
- `enrich-specs`: spec enrichment and backfill
- `review-v3-second-pass`: one-shot second-pass cleaning
- `serve-web`: dashboard
- `build-buy-baselines`: fair-price baseline rebuild
- `refresh-buy-opportunities`: opportunity refresh
- `emit-buy-alerts`: write alert events
- `record-buy-feedback`: persist human feedback
- `classify-seller-types`: refresh heuristic seller labels

Do not rename a running job based on prose, screenshots, or assumptions.

## Primary Commands

Database:

- `python -m goofish_insight.cli db-upgrade`
- `python -m goofish_insight.cli db-current`

Collection:

- `python -m goofish_insight.cli collect-search ...`
- `python -m goofish_insight.cli collect-batch ...`
- `python -m goofish_insight.cli watch-home-feed ...`

Cleaning and review:

- `python -m goofish_insight.cli review-v3-second-pass ...`
- `python -m goofish_insight.cli sync-review-v3-compat --apply ...`
- `./scripts/run-ark-review-cleaning.sh ...`

Spec and pricing:

- `python -m goofish_insight.cli enrich-specs ...`
- `./scripts/run-ark-spec-enrichment.sh ...`
- `python -m goofish_insight.cli show-price-bands ...`
- `python -m goofish_insight.cli build-buy-baselines ...`
- `python -m goofish_insight.cli refresh-buy-opportunities ...`
- `python -m goofish_insight.cli emit-buy-alerts ...`
- `python -m goofish_insight.cli record-buy-feedback ...`

Maintenance:

- `python -m goofish_insight.cli classify-seller-types`
- `python -m goofish_insight.cli cleanup-history ...`
- `./scripts/control-local-resident-market-runtime.sh status`
- `./scripts/control-local-resident-review-v3.sh status`

## Delivery Baseline

Before reporting any change as complete, run the delivery baseline:

```bash
npm run verify-baseline
```

P0 gates that must pass:

1. `npm run typecheck -w @goofish/dashboard-react`
2. `npm run test -w @goofish/dashboard-react`
3. `npm run typecheck -w @goofish/dashboard-nest`
4. `npm run test:e2e -w @goofish/dashboard-nest -- --runInBand`
5. `python -m compileall apps/collector/src apps/analyzer/src -q`
6. `PYTHONPATH=apps/collector/src:apps/analyzer/src:packages/schema/src python -m unittest <selected modules>`

Full baseline definition: [C15-quality-gates-and-release-baseline.md](docs/task-packs-20260419-system-closeout/C15-quality-gates-and-release-baseline.md)

## Operating Notes

- Keep documentation aligned with the code, especially `AGENTS.md`, `MODULE.md`, and skill docs.
- Generated artifacts in `reports/` can become stale after prompt-schema changes. Remove or rotate old traces when they show fields that no longer exist, such as `title_tokens`.
- First-pass for product understanding is `enrich-specs`: resolve category and template, load template attributes, and extract structured values from source fields into `item_spec_enrichments`.
- `review-items-llm` is legacy only. `review-v3-second-pass` is the canonical review path now, and neither should be used as the primary spec-extraction job.
- When evaluating trends or buy zones, make sure historical migrated data for legacy domains is included under the canonical categories.
