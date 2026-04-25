# Application Layer

## Purpose

`application/` holds use-case orchestration and dashboard-facing read models.

## Responsibilities

- assemble dashboard sections and panels
- run review and intake gating services
- coordinate runtime-control logic
- drive buy-side baselines, opportunities, alerts, and feedback
- expose reusable workflows to CLI or web entrypoints

## Boundary

- can combine ORM access, pricing helpers, and business decisions
- should not own CLI registration or FastAPI route wiring
- should not reintroduce broad raw payload storage where a smaller contract is enough
