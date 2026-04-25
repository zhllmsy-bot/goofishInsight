# Goofish Insight Package

## Purpose

`apps/collector/src/goofish_insight` is the main Python package for the collector-side runtime.

## Package Layout

- `entrypoints/`: CLI and web registration
- `application/`: orchestration and service-layer read/write logic
- `domain/`: reusable contracts and policies
- `presentation/`: display helpers
- root modules such as `cli.py`, `pricing.py`, `specs.py`, `models.py`, and `webapp.py`

## Current Reality

The package is mid-refactor: the layering exists, but several important workflows still live in root modules. Treat the package as a modular monolith, not a fully separated clean architecture system.
