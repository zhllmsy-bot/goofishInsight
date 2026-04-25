# Collector Module

## Purpose

`apps/collector` is the live operational core of Goofish Insight.

## Responsibilities

- attached-browser collection and feed watch
- ingestion and normalization into PostgreSQL
- permanent garbage tombstones at ingest time
- spec enrichment and review pipelines
- pricing and buy-side baseline generation
- dashboard API assembly and local runtime controls

## Current Data Rules

- Historical market memory lives in `items` and `item_snapshots`.
- Hard garbage rows should use `item_ingest_rejection` and keep only minimal tombstone fields.
- `items.title_tokens` is retired and must not return.
- LLM inputs and outputs should be minimal and schema-driven.
- Seller type stored on `seller_profiles.metadata_json` is heuristic only.

## Key Paths

- `src/goofish_insight/cli.py`
- `src/goofish_insight/specs.py`
- `src/goofish_insight/pricing.py`
- `src/goofish_insight/models.py`
- `src/goofish_insight/webapp.py`
- `alembic/`
- `tests/`
