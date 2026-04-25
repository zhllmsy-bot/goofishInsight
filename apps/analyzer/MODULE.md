# Analyzer Module

## Purpose

`apps/analyzer` is the home for analysis-heavy jobs and buy-side decision logic that should not stay mixed into the collector.

## Current Reality

- Three batch jobs form the core: `daily_metrics`, `model_scores`, `analysis_reports`.
- Buy-side baselines, opportunity refresh, and pricing logic have been extracted here.
- All runtime constants, lock paths, source modes, and health status are unified in `goofish_analyzer.contract`.
- CLI entry points are in `goofish_analyzer.cli` with per-job commands plus `health` and `status`.

## Key Modules

- `contract.py` — unified runtime constants: job names, lock paths, source modes, exit codes, health status, `build_source_contract()`, `resolve_lock_path()`
- `cli.py` — Typer CLI with commands: `run-job`, `run-daily-metrics`, `run-model-scores`, `run-analysis-reports`, `run-all`, `health`, `status`
- `jobs/_locking.py` — shared `fcntl` file-lock context manager
- `jobs/daily_metrics.py`, `jobs/model_scores.py`, `jobs/analysis_reports.py` — job entry points
- `logging.py` — structured job logging and `collector_job_run` lifecycle
- `services/` — business logic: metrics builder, score builder, report builder, buy decision hub, buy opportunities, buy feedback, pricing thresholds, pricing explanations, buy alerts

## Boundary

- `collector` continues to own: collection, ingestion, review, spec enrichment, dashboard APIs, runtime controls.
- `analyzer` owns: batch analysis jobs, buy-side decision logic, pricing/alert domain contracts.
- Analyzer jobs import from `collector` for DB access and models only.
