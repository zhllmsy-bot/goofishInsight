# Apps Module

## Purpose

`apps/` contains the repository's runtime applications.

## Current Reality

- `collector` is the operational core.
- `web` holds templates and static assets for the dashboard.
- `analyzer` is still a light placeholder; some analysis services still live in `collector`.
- `android-overlay` is an experimental client-side helper and is not the mainline runtime.

## Boundaries

- Browser automation, ingestion, review, pricing, and buy-side workflows belong in `collector` today.
- Pure presentation assets belong in `web`.
- New heavy offline analysis jobs should move toward `analyzer` instead of further bloating `collector`.
