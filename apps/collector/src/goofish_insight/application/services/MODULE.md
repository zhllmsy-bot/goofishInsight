# Application Services

## Purpose

`application/services` contains the service-layer workflows used by CLI commands and web routes.

## Key Service Families

- `dashboard_*`: dashboard sections, panels, filters, and trend cards
- `pricing_explanations.py`: shared human-readable serializers for baseline and opportunity readiness summaries
- `pricing_eligibility.py`: review gate and spec-confidence eligibility for pricing, baselines, and opportunities
- `spec_candidate_queue.py`: bounded candidate loading for first-pass spec enrichment
- `spec_enrichment_policy.py`: category-level complete/partial/retry contracts for first-pass spec extraction
- `spec_worker_state.py`: repeat-result freeze and persistent worker state helpers
- `template_attribute_audit.py`: top-level active category template audit plus minimal canonical supplements, auto-discovered from runtime profiles and prompt profiles
- `review_*`: intake review, second-pass review, apply, calibration, and trace helpers
- `review_v3_*`: dual-stage flat extraction, deterministic mapping, executor abstraction, direct-model execution, CozeLoop prompt sync helpers, and compatibility bridge back into `items.llm_review_*`
- `buy_*`: fair-price baselines, opportunity refresh, alerts, feedback, and dashboard data
- `runtime_*`: resident launchd control and operational health helpers
- `*_config`, `*_catalog_*`, `*_template_*`: category, task, and template configuration
- `seller_classification.py`: heuristic seller-type inference
- `feed_category_resolution.py` and `feed_workflow_runtime.py`: reusable homepage feed target-pool gating, candidate-domain routing, and lightweight decision persistence

## Current Repo Notes

- Trend cards should pull full historical `item_snapshots` for the selected product groups.
- Garbage tombstones should stay minimal and permanent.
- Review prompts should send only used fields and ask models to return only decision fields.
- Seller type is heuristic metadata, not a captured platform merchant flag.
- Resident spec workers should use bounded candidate queues plus freeze/backoff state, not open-ended `partial` retries.
- Pricing records should carry reusable `pricing_eligibility` and `spec_contract` snapshots so buy opportunities and dashboard views do not recompute explanation logic.
- Pricing records should also carry a reusable `spec_source` snapshot so shadow rows, runtime-only rule results, and normal extracted specs stay distinguishable in every downstream surface.
- Buy workbench serializers should expose human-readable explanation summaries derived from those snapshots instead of pushing raw gating logic into templates.
- Pricing availability should expose one shared summary contract so baselines, dashboard pricing panels, and buy workbench cards describe readiness with the same wording.
- The same pricing-availability summary contract should flow through homepage focus cards, trend cards, and CLI pricing commands so operators see one explanation vocabulary across every entrypoint.
- Homepage feed should follow one shared contract: `raw category gate -> candidate internal domains -> final category resolution -> template enrichment -> outreach`; raw xianyu category ids are target-pool gate signals, not final internal category mappings.
- Review V3 should execute directly against the configured model endpoint by default; the resident review runtime should loop on V3 second-pass work and keep writing compatible `items.llm_review_*` fields for downstream readers.
- CozeLoop is reserved for prompt sync/debug and should stay off the latency-sensitive execution path.
- Review V3 CozeLoop sync should remain idempotent: identical prompt detail must resolve to `unchanged` instead of generating fresh prompt commits on every operator run.
