# Scripts Module

## Purpose

`scripts/` contains operational wrappers and helper entrypoints.

## Current Responsibilities

- attached-browser setup and inspection
- resident runtime control for market collection and review-v3
- resident runtime control for spec enrichment
- one-shot review smoke commands
- review-v3 validation sampling and cutover checks
- cohort-scoped review-v3 second-pass continuation
- full active-items review-v3 backfill launcher
- helper wrappers for recurring jobs
- Ark-compatible remote cleaning smoke path
- Ark-compatible remote spec-enrichment path
- review-v3 direct execution wrapper and CozeLoop prompt sync wrapper

## Key Scripts

- `control-local-resident-market-runtime.sh`
- `control-local-resident-review-v3.sh`
- `control-local-resident-spec-enrichment.sh`
- `open_attached_browser.py`
- `list_attached_tabs.py`
- `run-ark-review-cleaning.sh`
- `run-ark-spec-enrichment.sh`
- `control-review-v3-direct.sh`
- `control-review-v3-cozeloop.sh`
- `run_review_v3_validation_samples.py`
- `run_review_v3_cohort_second_pass.sh`
- `start_review_v3_full_backfill.sh`
- `show-review-v3-progress.sh`
- `run_spec_enrichment_worker.py`
- `start-spec-enrichment-resident.sh`
- `start-review-v3-resident.sh`
- `start-review-v3-full-active-resident.sh`
- `start-review-v3.sh`
- `finalize_review_v3_run.py`
- `benchmark_ark_tpm.py`
- `benchmark_ark_tpm_isolated.py`
- `run-ark-tpm-benchmark.sh`

## Boundary

If a workflow becomes part of the stable operator contract, prefer exposing it through the main CLI as well.

## Current Repo Notes

- `control-review-v3-direct.sh` drives review-v3 directly against the configured model endpoint with `EXECUTOR=direct`.
- `control-local-resident-review-v3.sh` installs and manages launchd-backed V3 services from the terminal; default install/start enables only the full-active worker and disables the legacy second-pass resident unless `ENABLE_SECOND_PASS_RESIDENT=1` is set.
- `control-local-resident-review-v2.sh` is now a legacy forwarder that immediately redirects to the V3 resident control script.
- `start-review-v3-resident.sh` is the default resident second-pass worker and loops over `PENDING_REVIEW` V3 rows.
- `start-review-v3-full-active-resident.sh` is the launchd-safe wrapper for the full-active backfill; it resumes the latest incomplete first-pass run, finalizes second-pass and summary on the same prefix, or starts a new full-active run when no unfinished prefix exists.
- `control-review-v3-cozeloop.sh` is now for CozeLoop bootstrap and prompt sync/debug only; it is no longer the hot-path execution wrapper.
- `run_review_v3_validation_samples.py` selects representative `items` samples per category, can execute first/second pass, and can regenerate a status-only cutover report without burning more tokens.
- `run_review_v3_cohort_second_pass.sh` waits for an upstream first-pass cohort run if needed, then runs only the residual `PENDING_REVIEW` items through second-pass and writes a compact cohort summary.
- `start_review_v3_full_backfill.sh` counts all active `items`, optionally waits for in-flight validation jobs to clear, then launches the resilient V3 orchestrator over the full active cohort; resume mode now defaults to `auto`, so the latest incomplete run prefix is resumed before opening a new run.
- `finalize_review_v3_run.py` resumes the post-first-pass half of an existing orchestrated run and writes `pending-second-pass`, `second-pass.*`, and `final-summary` back onto the original run prefix.
- `run_review_v3_top_items_orchestrator.py` is now the canonical execution state machine for first-pass, second-pass, and summary writing, including retry/backoff plus a per-run state file at `reports/<run_prefix>.run-state.json`.
- `show-review-v3-progress.sh` now reads both watch logs and `*.run-state.json` to report canonical status (`running` / `retry_backoff` / `waiting` / `stalled` / `completed` / `failed`) and reduce false "running" signals when workers are actually gone.
- `benchmark_ark_tpm.py` replays the latest Ark prompt trace (or a synthetic prompt), runs concurrency ladders, and outputs measured RPM/TPM/latency/error and a recommended safe concurrency.
- `benchmark_ark_tpm_isolated.py` executes the same benchmark as truly isolated worker processes (one process per concurrent worker) to avoid single-process thread contention artifacts.
- `run-ark-tpm-benchmark.sh` is the operator wrapper around `benchmark_ark_tpm_isolated.py` with env-driven defaults (`DURATION_SEC`, `CONCURRENCY_LEVELS`, `MAX_TOKENS`).
- CozeLoop prompt sync uses internal manage routes with `session_key`; execution uses PAT-backed OpenAPI routes.
- V3 prompt sync should be idempotent: if prompt detail is unchanged, the script should not create a new CozeLoop commit version.
