# Review V3 Dual-Stage Spec

## Why V3

V3 exists to solve a specific architecture problem: second-hand marketplace data is highly unstructured, noisy, and non-standardized. Letting one large model directly output database-shaped pricing rows is expensive and fragile.

The V3 principle is:

`LLM does semantic extraction; Python code does deterministic mapping; low-confidence items enter a bounded expert-review pass.`

This keeps token cost low, reduces hallucinated model codes, and makes failure diagnosis much clearer.

## Design Goals

- Do not change existing review/spec/pricing pipelines.
- Keep V3 isolated in its own storage and CLI commands.
- First pass returns only flat factual features.
- Deterministic mapping decides whether an item is directly priceable.
- Second pass only resolves among a short local candidate list.

## Pipeline

### Stage 1: Fast & Flat Extraction

Input:
- title
- condition tags
- listing description
- current price
- source keyword

Output:
- flat feature object only
- no template rows
- no spuAttributes / skuAttributes
- no catalog id generation by the model

Decision path:
1. static rule guard rejects obvious garbage / buyback / overlong titles
2. LLM extracts flat factual features
3. Python mapping scores against local catalog
4. item enters one of:
   - `REJECTED_STATIC_GUARD`
   - `REJECTED_ACCESSORY`
   - `VALID_READY_FOR_PRICING`
   - `PENDING_REVIEW`

### Stage 2: Candidate Resolution

Input:
- raw title and description
- first-pass extracted features
- top 3-5 local catalog candidates

Output:
- `resolved_model_code` chosen from candidates only
- `needs_human`
- reasoning text for audit

Decision path:
- resolved candidate -> `VALID_READY_FOR_PRICING`
- unresolved but ambiguous -> `MANUAL_AUDIT_REQUIRED`
- unsupported / still not matched -> `INVALID_OR_NOT_SUPPORTED`

## Storage

V3 persists into a dedicated table: `item_review_v3`.

This avoids overwriting:
- `items.llm_review_*`
- `item_spec_enrichments`
- current pricing eligibility contracts

## Current Scope

Implemented profiles:
- `camera_interchangeable_lens`
- `apple_computer`
- `garmin_watch`
- `camera_body`
- `phone`
- `apple_airpods`

Important boundary:
- current local catalog coverage is strongest for `camera_interchangeable_lens`
- Apple and Garmin can run first-pass extraction immediately
- direct deterministic mapping for Apple/Garmin will stay conservative until category model catalogs are populated

## CLI

- `review-v3-first-pass`
- `review-v3-second-pass`
- `sync-review-v3-cozeloop-prompts`
- wrapper script: `scripts/start-review-v3.sh`
- direct execution wrapper: `scripts/control-review-v3-direct.sh`
- CozeLoop wrapper: `scripts/control-review-v3-cozeloop.sh`

## CozeLoop Executor

V3 now supports two executors:
- `direct`
- `cozeloop`

Recommended runtime boundary:
- `direct` is the default hot-path executor for first-pass and second-pass runs
- `cozeloop` is reserved for prompt sync/debug and should stay off the latency-sensitive execution path

The CozeLoop path is intentionally split:
- prompt sync uses CozeLoop internal manage APIs with `session_key`
- prompt execution uses CozeLoop OpenAPI with PAT

This matches the current local CozeLoop capabilities:
- internal manage routes support prompt CRUD and commit
- PAT-based execute works reliably on `http://127.0.0.1:8888/v1/loop/prompts/execute`

Important compatibility note:
- CozeLoop prompt `model_config.json_mode` must stay `false`
- Ark `coding/v3` rejects `response_format.type=json_object`
- JSON-only output is enforced by prompt contract, not by transport-level json mode

Prompt sync is idempotent:
- if the managed prompt detail has not changed, sync returns `action=unchanged`
- no extra draft save or commit is created
- this prevents version spam when operators run `first-pass` repeatedly during prompt iteration

## Non-Goals

V3 does not yet:
- replace every legacy CLI/operator affordance on day one
- write directly into current pricing/spec tables without the existing compatibility bridge
- require CozeLoop as the only executor

## Next Steps

1. keep expanding category model catalogs so Apple and Garmin manual rates keep dropping
2. treat V3 resident direct execution as the default runtime path and keep legacy V2 only as a rollback lever
3. use CozeLoop for prompt iteration and regression sets, not as the hot execution path
