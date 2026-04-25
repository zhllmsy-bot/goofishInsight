# Architecture Refactor Spec

Status: Draft v2  
Date: 2026-03-22  
Workspace: `C:\Users\13754\Documents\Playground\goofish-insight`

## 1. Purpose

This document is the controlling spec for architecture refactors in this repository.

It is not just a design note. It exists to make later changes traceable and reviewable.

Every structural refactor should follow:

1. update this spec first
2. assign or reuse a `Trace ID`
3. make the code change
4. run the matching verification
5. sync `AGENTS.md`, relevant `MODULE.md`, and relevant `skills/*/SKILL.md`
6. update the trace item status here

If a refactor has no trace item in this spec, it is considered out of process.

## 2. Current Assessment

The project already has real business capabilities:

- Goofish search collection
- attached-browser collection and homepage feed monitoring
- spec enrichment
- LLM second-pass review and write-back
- pricing bands and dashboard pages

But the codebase still shows common PoC-to-production problems:

- oversized files that mix entrypoints, query logic, business rules, and presentation shaping
- inconsistent boundaries between CLI, web, and worker flows
- some refactors have started, but the target layering is not fully landed yet
- regression coverage exists, but integration coverage is still thin relative to the size of the refactor

Current confirmed state:

- `apps/collector/src/goofish_insight/webapp.py` is now a thin app factory
- CLI command registration is split under `entrypoints/cli/*.py`
- LLM review field contracts and type validation live in `domain/review/contracts.py`
- dashboard page responsibilities are now split across `application/services/dashboard_filters.py`, `dashboard_queries.py`, `dashboard_panels.py`, and a thin `dashboard_page.py` orchestrator
- LLM review lifecycle responsibilities are now split across `application/services/review_queries.py`, `review_batches.py`, `review_ingest.py`, and `review_apply.py`, with `item_llm_review.py` kept as a compatibility facade

## 3. Goals

This refactor targets a modular monolith, not microservices.

Required outcomes:

- clear `entrypoints / application / domain / infra / presentation` layering
- explicit runtime units for `web / collector / review worker / scheduler`
- fewer god modules, with code moving toward stable ownership boundaries
- refactors that can be traced from plan to code to verification
- docs and operator instructions that match the actual code layout

Non-goals for this round:

- no direct microservice split
- no mandatory async rewrite of ORM, browser, or all services
- no new queue infrastructure such as Redis, Celery, or Kafka unless Postgres-based coordination becomes a proven bottleneck

## 4. Best-Practice Constraints

These are the rules this repo should follow while refactoring.

### 4.1 Thin Web Entrypoints

- the FastAPI app factory should only build the app, mount routers, and register template or middleware hooks
- routers should only parse inputs and return responses
- page-data composition belongs in `application/services`
- template labels and Jinja filters belong in `presentation`

### 4.2 Session Scope Must Be Local

- `SessionLocal` can remain as the session factory
- concrete `Session` objects must stay request-local or task-local
- sessions must not be shared across threads or workers

### 4.3 Stable CLI Surface, Thin CLI Logic

- `python -m goofish_insight.cli` remains the operator-facing entrypoint
- command registration can be split by domain
- long-lived business logic should not stay embedded in CLI registration modules

### 4.4 Config Must Not Depend on Working Directory

- `.env` loading must resolve from the repository root or from explicit configuration
- production secrets should come from environment or secret mounts

### 4.5 Browser Access Must Go Through Adapters

- CDP attach
- context and tab lifecycle
- search capture
- homepage feed workflows

These should converge behind browser adapters instead of being duplicated across CLI commands.

### 4.6 LLM Write-Back Must Be Schema-First

- model output fields must be limited to an explicit whitelist
- write-back must re-validate types before persistence
- invalid or unexpected types must be dropped at field level, not coerced blindly into the database

### 4.7 Refactors Must Ship With Verification and Docs

Every structural change must update:

- this spec
- `AGENTS.md`
- the nearest `MODULE.md`
- the affected `skills/*/SKILL.md`

## 5. Target Layout

```text
apps/collector/src/goofish_insight/
  entrypoints/
    cli/
    web/
  application/
    services/
    dto/
    policies/
  domain/
    pricing/
    review/
    specs/
    items/
  infra/
    db/
    browser/
    ai/
    logging/
    config/
  presentation/
  pricing.py          # transition module, to be split further later
  item_llm_review.py  # transition module, to be split further later
  cli.py              # thin operational entrypoint only
```

Layer responsibilities:

- `entrypoints`
  parse input, call application services, shape output
- `application`
  orchestrate use cases and cross-module flows
- `domain`
  business rules, contracts, normalization, aggregation, pure calculations
- `infra`
  database access, browser automation, AI clients, logging, configuration
- `presentation`
  labels, filters, and view formatting only

## 6. Trace ID Rules

All architecture refactor work must be tracked by `Trace ID`.

Prefixes:

- `AR-CLI-*`
- `AR-WEB-*`
- `AR-REVIEW-*`
- `AR-BROWSER-*`
- `AR-PRICING-*`
- `AR-TEST-*`
- `AR-DOC-*`
- `AR-DEPLOY-*`

Allowed statuses:

- `planned`
- `in_progress`
- `completed`
- `blocked`
- `deferred`

Each trace item must record:

- objective
- affected files or modules
- current status
- verification command(s)
- notes or risks

## 7. Phase Plan

### Phase 0: Guardrails

Goal:

- stabilize settings loading
- stabilize smoke commands
- fix practical compatibility issues such as BOM or Windows shell encoding

Acceptance:

- common operator commands do not depend on accidental current-directory behavior
- self-check scripts run reliably in PowerShell

### Phase 1: Entrypoint Split

Goal:

- split CLI registration by domain
- separate FastAPI app factory from router modules
- preserve public command names and URLs

Acceptance:

- `python -m goofish_insight.cli --help` works
- `/`, `/progress`, `/healthz` work

### Phase 2: Web Query and View Split

Goal:

- split dashboard query logic, filter logic, and page view-model shaping
- keep progress-page logic isolated
- keep `presentation` limited to display concerns

Acceptance:

- `webapp.py` stays a thin factory
- `dashboard_page.py` is no longer a large mixed page-service module

### Phase 3: LLM Review Split

Goal:

- separate claim / review / apply responsibilities
- isolate provider client, prompt builder, and response parser boundaries
- keep one authoritative field contract

Acceptance:

- `domain/review/contracts.py` remains the single field-contract source
- `item_llm_review.py` no longer handles the entire lifecycle alone

### Phase 4: Browser and Collector Adapters

Goal:

- move attached-browser, search capture, and homepage feed behavior toward `infra/browser`
- keep orchestration in application services

Acceptance:

- `collect-search`
- `collect-batch`
- `refresh-home-feed`
- `watch-home-feed`

all rely on the same browser gateway path

### Phase 5: Repository and Job Model Cleanup

Goal:

- reduce duplicate query logic across web, CLI, and workers
- assess whether review claim / lease should move from `items` state to explicit job tables

Acceptance:

- core reads and writes are less duplicated and have clearer ownership

### Phase 6: Deployment and Observability

Goal:

- model `web / collector-worker / review-worker / scheduler` as explicit runtime units
- improve health checks and structured logging
- document deployment and restart behavior clearly

Acceptance:

- deployment docs clearly explain how each runtime starts, restarts, and is health-checked

## 8. Traceability Matrix

### Completed

| Trace ID | Objective | Affected Files | Status | Verification |
| --- | --- | --- | --- | --- |
| `AR-CLI-01` | Split CLI command registration by domain | `cli.py`, `entrypoints/cli/admin.py`, `entrypoints/cli/collect.py`, `entrypoints/cli/feed.py`, `entrypoints/cli/pricing.py`, `entrypoints/cli/review.py`, `entrypoints/cli/maintenance.py` | `completed` | `python -m goofish_insight.cli --help` |
| `AR-WEB-01` | Reduce `webapp.py` to a thin app factory | `webapp.py`, `entrypoints/web/app.py`, `entrypoints/web/routers/dashboard.py`, `entrypoints/web/routers/progress.py` | `completed` | `/`, `/progress`, `/healthz` return `200` |
| `AR-REVIEW-01` | Extract LLM review contracts and validation | `item_llm_review.py`, `domain/review/contracts.py` | `completed` | `python -m unittest discover apps/collector/tests` |
| `AR-REVIEW-02` | Split `item_llm_review.py` into claim / review / apply responsibilities | `item_llm_review.py`, `application/services/review_queries.py`, `application/services/review_batches.py`, `application/services/review_ingest.py`, `application/services/review_apply.py`, `entrypoints/cli/review.py`, `scripts/run_item_llm_review_worker.py` | `completed` | `python -m unittest discover apps/collector/tests` |
| `AR-DOC-01` | Sync architecture docs to current layering | `AGENTS.md`, `apps/**/MODULE.md`, `skills/**/SKILL.md` | `completed` | `python skills/repo-module-doc-writer/scripts/audit_docs.py` |
| `AR-TEST-01` | Stabilize skill smoke and self-check scripts | `scripts/test_skills.ps1`, `skills/goofish-attached-collector/scripts/check_attached_collector.py` | `completed` | `powershell -ExecutionPolicy Bypass -File scripts/test_skills.ps1` |

### In Progress

| Trace ID | Objective | Affected Files | Status | Verification |
| --- | --- | --- | --- | --- |
| `AR-TEST-02` | Add route and CLI integration coverage for the new layout | `apps/collector/tests/test_review_entrypoints.py`, `apps/collector/tests/test_web_services.py`, `apps/collector/tests/test_item_llm_review_preview.py` | `in_progress` | entrypoint smoke covers review CLI registration plus `/`, `/progress`, `/items/{item_id}`, and `/healthz` |

### Planned

| Trace ID | Objective | Affected Files | Status | Verification |
| --- | --- | --- | --- | --- |
| `AR-BROWSER-01` | Unify browser adapter path | future `infra/browser/*`, `entrypoints/cli/collect.py`, `entrypoints/cli/feed.py` | `planned` | collection and feed flows share one browser gateway |
| `AR-PRICING-01` | Split `pricing.py` further into domain and application pieces | `pricing.py`, future `domain/pricing/*`, future `application/services/*` | `planned` | pricing rules, aggregators, and use-case shaping are separated |
| `AR-DEPLOY-01` | Improve runtime health and deployment clarity | `entrypoints/web/*`, `docs/06-deployment.md` | `planned` | health endpoints and runtime docs are explicit |

## 9. Current Status Review

### 9.1 What Is Already Better

- CLI commands are no longer all implemented in one file
- web app creation has a real factory and router boundary
- dashboard filtering, query composition, and pricing-oriented page shaping now have separate service modules
- LLM review field schema and type validation now have a single shared contract module
- LLM review claim, intake gating, batch review, and write-back now have dedicated service modules instead of one mixed workflow file
- review CLI registration, compatibility facade exports, and core web routes now have committed smoke coverage
- docs and skills now reflect the current code layout
- Python tests, skills smoke, and docs audit all currently pass

### 9.2 What Still Does Not Meet the Target

- CLI registration modules still rely on large injected dependency lists rather than settled service interfaces
- LLM provider access still runs through `specs.py` helpers instead of a dedicated `infra/ai` adapter
- integration coverage is still too thin outside the dashboard and review entrypoints
- generated runtime artifacts still appear in normal diffs and add review noise

## 10. Change Protocol

For future architecture work, follow this exact order:

1. update this spec first
2. assign or reuse a `Trace ID`
3. make only the code changes that belong to that trace item
4. run the matching tests and smoke commands
5. sync `AGENTS.md`, relevant `MODULE.md`, and relevant `SKILL.md`
6. update the trace item status here

This is the required flow-trace for architecture work in this repository.

## 11. Verification Baseline

Current local baseline:

```powershell
python -m unittest discover apps/collector/tests
powershell -ExecutionPolicy Bypass -File scripts/test_skills.ps1
python skills/repo-module-doc-writer/scripts/audit_docs.py
$env:PYTHONPATH = (Join-Path (Get-Location) 'apps\collector\src'); python -m goofish_insight.cli --help
```

Web smoke baseline:

```python
from fastapi.testclient import TestClient
from goofish_insight.webapp import create_app

app = create_app()
client = TestClient(app)

assert client.get("/").status_code == 200
assert client.get("/progress").status_code == 200
assert client.get("/healthz").status_code == 200
```

## 12. Documentation Sync Rules

Each completed trace item must update:

- `docs/08-architecture-refactor-spec.md`
- `AGENTS.md`
- the nearest `MODULE.md`
- the affected `skills/*/SKILL.md`

Meaning:

- this spec explains why, scope, state, and acceptance
- `AGENTS.md` explains how other models should understand and operate the repo now
- `MODULE.md` explains directory-level responsibilities
- `SKILL.md` explains the current operator workflow

## 13. References

- FastAPI: Bigger Applications - Multiple Files
- FastAPI: Deployment Concepts
- SQLAlchemy: Session Basics
- Pydantic: Settings Management
- Playwright: Authentication
- Playwright: Browser Contexts / Isolation
- Alembic: Autogenerate / Check
