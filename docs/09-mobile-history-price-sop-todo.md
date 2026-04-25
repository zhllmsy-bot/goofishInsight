# Mobile History Price SOP Todo

## Goal

Standardize the workflow for querying historical成交价格 from the connected Android phone, so the project can repeatedly collect, validate, and persist mobile-side market data with high reliability.

## Operating Rules

- Update this file after every meaningful step.
- Run a self-check after every completed step.
- If a blocker or a better path appears, add/remove/reorder todos here before continuing.
- Prefer deterministic UI extraction over OCR when available.
- Do not trust one extraction path blindly; validate key fields before persisting.

## Current Findings

- Android device is connected through `adb`.
- Idle Fish app UI hierarchy can be dumped successfully with `uiautomator dump`.
- The market page already exposes useful structured text such as:
  - query keyword
  - `近7日成交均价`
  - `成交区间`
  - `成交记录`
  - visible成交价 entries
- The current project does not yet have a dedicated Android automation path.

## Todo List

- [x] Verify Android device connectivity and authorization.
- [x] Verify Idle Fish market page text can be extracted from UI hierarchy.
- [x] Define the SOP steps for one keyword query end-to-end.
- [x] Implement Android device helpers for dump, tap, swipe, and activity checks.
- [x] Implement market-page parser for summary metrics and visible成交记录.
- [x] Implement a standard executor: search keyword -> open 行情 -> extract -> validate -> persist.
- [x] Add dynamic checks and retries for each step.
- [x] Persist structured output to `reports/` and `AnalysisReport`.
- [x] Add a CLI command for repeated execution.
- [x] Run one real keyword end-to-end on the connected phone.
- [ ] Improve arbitrary query input beyond current-query or recent-search reuse.
- [ ] Improve scroll collection so it stays inside the market page after swipe.
- [x] Review extraction quality and revise the SOP if needed.

## Self-Check Log

### Checkpoint 1

- Status: passed
- What changed:
  - Confirmed `adb devices -l` sees the phone.
  - Confirmed `uiautomator dump` works on the current Idle Fish screen.
  - Confirmed the dumped XML contains行情页关键文本.
- Replan needed: yes
- Replan decision:
  - Build on UI hierarchy extraction first.
  - Keep OCR only as a fallback path, not the primary path.

### Checkpoint 2

- Status: passed
- What changed:
  - Added Android market-history service and CLI command.
  - Added structured extraction for:
    - current query
    - 近7日成交均价
    - 成交区间
    - visible 成交记录
  - Added report persistence to `reports/` and `AnalysisReport`.
- Self-check result:
  - `capture-mobile-market-history --query m2ultra192g` succeeded.
  - Captured:
    - `近7日成交均价 = 37995`
    - `成交区间 = 32850-37995`
    - `visible_record_count = 1`
- Replan needed: yes
- Replan decision:
  - Treat "current query / recent-search chip reuse" as the stable V1 path.
  - Do not depend on `adb input text` for Idle Fish search input yet.
  - Add a dedicated follow-up todo for arbitrary query input.

### Checkpoint 3

- Status: mixed
- What changed:
  - Verified optional scroll collection.
- Self-check result:
  - Scroll step can run, but current swipe may leave the market page and drop back to search-result state.
- Replan needed: yes
- Replan decision:
  - Keep summary + first visible成交记录 as stable output for V1.
  - Add a follow-up todo to stabilize in-page scroll collection before depending on multi-screen records.
