# Entrypoints Layer

## Purpose

`entrypoints/` exposes the application's operator-facing interfaces.

## Modules

- `cli/`: Typer command registration split by topic
- `web/`: FastAPI router registration and request parsing

## Boundary

Keep entrypoints thin. They should parse inputs, call services, and format responses, not own the core business rules.
