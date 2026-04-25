# Collector

The collector owns browser-driven capture, response persistence, and spec enrichment.

## Core flow

- Open a real Goofish search page in an attached browser session
- Listen to search/list responses instead of scraping console output
- Normalize listing fields into `items` and `item_snapshots`
- Deduplicate listings by `item_id` before persistence
- Drop obvious low-price outliers before they reach the cleaned tables
- Skip unchanged snapshots so repeated daily runs do not bloat storage
- Enrich Garmin and Apple listings into structured specs
- Preview high-confidence LLM anomaly suggestions from existing cleaned rows before any write-back design is accepted
- Track whether each `items` row has already been reviewed by the LLM, and only send unchecked active rows by default

## Main CLI commands

```bash
goofish-collector db-upgrade
goofish-collector seed-task
goofish-collector collect-search garmin --task-key garmin-fenix --profile-key chrome-attached
goofish-collector collect-batch --profile-key chrome-attached --parallel-tabs 3
goofish-collector enrich-specs --business-domain garmin --limit 100
goofish-collector review-items-llm --business-domain garmin --batch-size 20 --concurrency 4
goofish-collector apply-item-llm-review reports/item-llm-review-preview-*.json --dry-run
goofish-collector show-spec-summary --business-domain garmin
goofish-collector cleanup-history --max-passes 1
goofish-collector show-health
goofish-collector show-browser-sessions
```

## Browser session state

Login state is tracked in `browser_sessions`:

- `profile_key`
- `auth_state`
- `last_login_required_at`
- `last_authenticated_at`

The actual browser cookies and session files remain under `BROWSER_PROFILE_DIR/<profile_key>`.

Home feed monitoring should reuse an existing Goofish home tab and alternate between the `猜你喜欢` and `个人闲置` tabs, with a 10-second dwell after each switch. It should not close/reopen the tab or reload the page every cycle.

## Crawl pacing

To reduce Goofish risk-control triggers, page-turn actions are intentionally throttled.

- Target interval between pagination actions: about 5 seconds
- Short post-click settle delay: under 1 second
- If you need slower pacing, adjust the wait values in the pagination helper before running large batches

## Spec enrichment

Spec extraction is hybrid:

- Rule parsing first
- LLM fallback only for low-confidence listings
- Final specs stored in `item_spec_enrichments`
- Batch LLM review can re-check existing `items` plus structured specs and emit anomaly-only suggestions without writing to the database
- `apply-item-llm-review` can consume a reviewed JSON file and patch existing `items` / `item_spec_enrichments` by `item_id`
- The LLM review result also decides whether a listing is invalid data such as accessories, ads, recycling posts, or electronic-parts offers

Environment variables:

- `AI_BASE_URL`
- `AI_MODEL`
- `AI_API_KEY` or `BAILIAN_CODING_PLAN_API_KEY`
- `AI_ENABLE_THINKING`
- `PRUNE_RAW_AFTER_INGEST`
- `LOW_PRICE_FILTER_RATIO`
- `LOW_PRICE_FILTER_MIN_SAMPLES`

## Data hygiene

The collector now treats `items` and `item_snapshots` as the cleaned storage layer.

- `item_id` is the primary dedupe key
- items without a valid positive price are rejected
- low-price garbage is filtered when there are enough comparable samples in the batch
- `review-items-llm` batches existing `items` rows, asks the model for anomaly-only corrections, and only writes a preview JSON result
- `apply-item-llm-review --dry-run` shows exactly which fields would be updated before any database mutation
- `review-items-llm` skips rows where `items.llm_reviewed=true` unless `--force` is used
- `apply-item-llm-review` marks reviewed rows as `valid` or `invalid`; invalid rows are deactivated with `items.is_active=false`
- raw requests and raw responses are skipped when `PRUNE_RAW_AFTER_INGEST=true`
- unchanged snapshots are not inserted again
- `cleanup-history` applies the same rules to historical data that was collected before the cleanup pipeline existed
- use `--max-passes N` only when you intentionally want a stricter historical cleanup sweep

## Daily run

Use the scheduler-friendly wrapper from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_daily_job.ps1
```

That wrapper sets the correct working directory and `PYTHONPATH`, then runs the existing discovery pipeline.
