# Bulk Mobile Market History Todo

## Goal

Standardize a high-availability workflow that queries recent成交价格 in Idle Fish mobile market pages for mainstream collected products, persists structured results, and keeps a dynamic task queue with self-checks after every meaningful step.

## Operating Rules

- Update this file after every meaningful step.
- Run a self-check after every completed step.
- If the current path proves unreliable, replan here before continuing.
- Prefer deterministic UI extraction from Android UI hierarchy over OCR.
- Prefer queue-state persistence over in-memory-only execution.
- Do not silently mark a query as done if navigation or extraction quality is uncertain.

## Current Findings

- The connected Android phone is authorized and controllable through `adb`.
- Idle Fish launch, search entry, market-page summary extraction, and AnalysisReport persistence already work for single-query capture.
- Arbitrary text input through `adb input text` is still unreliable inside Idle Fish search input.
- Mainstream product candidates can be sourced from the existing dashboard/top-model aggregation.
- The missing piece is a bulk queue runner that can standardize task state, retries, self-checks, and report persistence.

## Todo List

- [x] Review the existing mobile history pipeline and the source of mainstream product candidates.
- [x] Create a new dynamic todo list for bulk mobile history capture.
- [x] Define the queue model: which products are considered mainstream, which query string to use, and what status lifecycle each task follows.
- [x] Implement queue/state persistence for bulk market-history tasks.
- [x] Implement a bulk runner that executes one task at a time, self-checks each step, and updates task state after every transition.
- [x] Add dynamic replanning hooks so blocked queries can be marked for retry/manual follow-up instead of stalling the whole run.
- [x] Run a real-device dry run on a small mainstream query set and validate report persistence.
- [x] Tune query normalization and fallback strategy based on real-device failures.
- [x] Run the bulk workflow on a larger mainstream set.
- [x] Finalize SOP notes and execution commands for repeated use.

## Self-Check Log

### Checkpoint 1

- Status: passed
- What changed:
  - Confirmed the existing single-query mobile history pipeline is reusable for batch orchestration.
  - Confirmed mainstream product candidates can be derived from current dashboard/top-model data rather than inventing a separate source.
- Replan needed: yes
- Replan decision:
  - Build the batch workflow as a queue/state layer on top of the existing single-query capture service.
  - Treat arbitrary query input as a reliability risk that must be isolated behind explicit task states and retries.

### Checkpoint 2

- Status: passed
- What changed:
  - Added a bulk queue/state service on top of the existing mobile history capture service.
  - Added task lifecycle states: `pending`, `running`, `done`, `blocked_input`, `failed`.
  - Added CLI commands to initialize and run the mainstream bulk queue.
  - Added a stable query-input path using the phone's Latin IME plus `adb shell input text` for ASCII-like product queries.
- Self-check result:
  - `test_mobile_market_history` and `test_mobile_market_history_batch` both passed.
  - Python compile checks passed for the updated services and CLI.
- Replan needed: yes
- Replan decision:
  - Keep the first real-device batch small and inspect failures before scaling.
  - Favor ASCII query candidates first, because they are now the most reliable fully-automated input path.

### Checkpoint 3

- Status: mixed
- What changed:
  - Verified `LatinIME + adb shell input text` can reliably switch from one product query to another for ASCII-like model names.
  - Added resilience for several real-device branches:
    - search suggestion / `查询宝贝成交价` page recognition
    - market-page variant recognition (`成交记录 + 最近成交/在售宝贝`)
    - camera / image-search detour detection and back navigation
    - retry logic for intermittent `uiautomator dump` failures
  - Added an executable wrapper:
    - `scripts/start-mobile-market-history-bulk.sh`
- Self-check result:
  - Single-query capture now works for:
    - `mac mini m4`
    - `forerunner 265`
  - Bulk dry run already shows the right behavior at the queue level:
    - failed tasks do not stall the queue
    - the runner continues to the next mainstream task
  - The small real-device batch is not fully green yet:
    - `mac mini m4` still fails intermittently in the batch runner
    - some market pages need one more scroll to expose enough成交信息
- Replan needed: yes
- Replan decision:
  - Keep `max_scrolls=1` as the default bulk-run posture.
  - Continue tuning the Apple query path and validation rules before declaring the batch runner fully complete.

### Checkpoint 4

- Status: passed
- What changed:
  - Added an explicit `home` baseline state for Idle Fish startup screens.
  - Added `force-stop + relaunch + baseline recovery` before bulk-task query attempts.
  - Stopped treating the home-page search hint as a real query.
- Self-check result:
  - `test_mobile_market_history` and `test_mobile_market_history_batch` both passed.
  - Python compile checks passed for the updated mobile services and CLI.
- Replan needed: yes
- Replan decision:
  - Re-run a small real-device mixed-domain dry run from a fresh queue.
  - If Apple tasks still fail, capture the exact branch and decide whether to add query-family fallbacks or stronger page-reset logic.

### Checkpoint 5

- Status: passed
- What changed:
  - Ran a fresh real-device dry run on a mixed-domain mainstream set (`top_n=4`) from a cold-start Idle Fish baseline.
  - Verified all 4 representative tasks reached `done` and persisted structured reports.
  - Confirmed the most reliable fallback order in practice:
    - Apple: compact family query (for example `macbookairm2`) may succeed after spaced/spec-heavy variants fail.
    - Garmin: brand-prefixed fallback (for example `garmin instinct`) can recover tasks that land on a weak market variant.
- Self-check result:
  - Queue summary reached `done=4`, `blocked_input=0`, `failed=0`.
  - Reports were persisted for:
    - `Mac mini M4`
    - `Instinct`
    - `MacBook Air M2 8G 256G`
    - `Forerunner 265`
- Replan needed: yes
- Replan decision:
  - Promote the workflow from small dry run to a larger mainstream batch.
  - Keep the current Apple compact-query fallbacks and Garmin brand-prefixed fallbacks.
  - Finalize SOP notes after the larger run confirms the same stability profile.

### Checkpoint 6

- Status: passed
- What changed:
  - Ran a larger mainstream batch (`top_n=12`) through the same Android workflow.
  - Persisted structured reports for all 12 tasks.
  - Wrote a repeatable SOP doc with executable commands and operating rules.
- Self-check result:
  - Queue summary reached `done=12`, `blocked_input=0`, `failed=0`.
  - The workflow proved stable across both Apple M-series and Garmin product families.
  - Cold-start baseline recovery plus query-candidate fallback is sufficient for the current mainstream set.
- Replan needed: no
- Replan decision:
  - The current goal is achieved.
  - Future iterations can focus on expanding the mainstream set, improving deeper record capture, or integrating these reports into downstream pricing dashboards.
