# Mobile Market History SOP

## Goal

Standardize a repeatable Android + Idle Fish workflow that queries recent成交价格 for mainstream collected products and persists structured snapshots for later use in the project.

## Preconditions

- Android phone is connected through `adb`.
- Phone is unlocked and Idle Fish can be launched.
- Project root:
  - `<repo-root>`

## Core Command

Run the mainstream batch workflow:

```bash
cd <repo-root>
QUEUE_STATE_PATH=<repo-root>/reports/mobile-market-bulk/queue-state-mainstream-v1.json \
TOP_N=12 \
MAX_TASKS=12 \
MAX_SCROLLS=1 \
RESET_QUEUE=1 \
./scripts/start-mobile-market-history-bulk.sh
```

For a repeated run on an existing queue:

```bash
cd <repo-root>
QUEUE_STATE_PATH=<repo-root>/reports/mobile-market-bulk/queue-state-mainstream-v1.json \
MAX_TASKS=12 \
MAX_SCROLLS=1 \
./scripts/start-mobile-market-history-bulk.sh
```

## What The Workflow Does

For each mainstream product task:

1. Force-stop and relaunch Idle Fish.
2. Restore the app to a reusable home/search-entry baseline.
3. Try normalized query candidates in order.
4. Open the market page.
5. Extract:
   - recent 7-day average price when available
   - sold price range when available
   - visible sale records
6. Persist a JSON report and an `AnalysisReport` row.
7. Update queue state after every transition.

## Query Strategy

- Apple tasks prefer family/model fallbacks and compact no-space queries.
  - Example:
    - `macbook air m2 8g 256g`
    - `macbookairm28g256g`
    - `macbook air m2`
    - `macbookairm2`
- Garmin tasks prefer brand-prefixed fallbacks.
  - Example:
    - `instinct`
    - `garmin instinct`
    - `佳明 instinct`

## Output Locations

- Queue state:
  - `<repo-root>/reports/mobile-market-bulk/*.json`
- Device snapshots:
  - `<repo-root>/reports/device/`
- Per-task market-history reports:
  - `<repo-root>/reports/mobile-market-bulk/<task-id>-<timestamp>.json`

## Queue Status Meanings

- `pending`: waiting to run
- `running`: currently executing
- `done`: successfully captured and persisted
- `blocked_input`: could not reliably reach a reusable query/input state
- `failed`: capture finished unsuccessfully for a non-input reason

## Dynamic Self-Check Rules

After each meaningful run:

1. Check queue summary:
   - `done`
   - `blocked_input`
   - `failed`
2. Inspect failed or blocked tasks and compare which query candidate succeeded or failed.
3. If Apple long spaced queries fail but compact family queries succeed, keep compact fallbacks early.
4. If a Garmin generic query lands on weak metrics, keep the `garmin <model>` fallback.
5. Do not mark a task as complete unless the market page is real and at least one of these exists:
   - 7-day average price
   - sold range
   - visible sale records

## Current Proven Batch

Verified successfully on a real-device `top_n=12` run:

- `done = 12`
- `blocked_input = 0`
- `failed = 0`

Representative successful tasks:

- `Mac mini M4`
- `MacBook Air M2 8G 256G`
- `MacBook Air M1`
- `MacBook Pro 14`
- `Instinct`
- `Forerunner 265`
- `Fenix 8`

## Repeatability Notes

- Keep `MAX_SCROLLS=1` as the default posture.
- Prefer cold-start baseline recovery for batch mode.
- Reuse the same queue file when you want resumable execution.
- Use `RESET_QUEUE=1` only when you explicitly want a fresh mainstream snapshot.
