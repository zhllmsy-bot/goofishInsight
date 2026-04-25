# Web Entrypoints

## Purpose

`entrypoints/web` contains the FastAPI routers for the internal dashboard.

## Current Scope

- dashboard and review pages
- configuration pages for categories, templates, and tasks
- buy opportunity inbox and feedback endpoints

## Operating Notes

- Web routes should stay thin and delegate to application services.
- Trend views should reflect migrated historical data from `item_snapshots`, not only the latest capture window.
