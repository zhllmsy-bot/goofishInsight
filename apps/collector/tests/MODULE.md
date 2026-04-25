# Collector Tests

## Purpose

`apps/collector/tests` holds regression tests for the collector-side runtime.

## What Belongs Here

- service-layer behavior
- CLI entrypoint wiring
- prompt-shape regressions
- pricing and review policy tests
- schema and migration-adjacent contract checks

## Current Must-Keep Regressions

- `title_tokens` stays removed from runtime payloads
- intake and second-pass prompts remain minimal
- historical trend cards can read older snapshots for selected groups
