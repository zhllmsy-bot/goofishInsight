# Web (Legacy Template Layer)

**Status**: Legacy — `apps/web` is the Jinja2 template and static asset layer for the internal dashboard, not the primary React workbench.

## What This Is

- Jinja2 templates and static assets served by `apps/collector` FastAPI
- Fallback for legacy page navigation
- Does not contain business logic or React components

## Primary Workbench

The current main operational workbench is **`apps/dashboard-react`**, not `apps/web`.

## Current Capability

- Legacy dashboard pages served via FastAPI+Jinja2
- Served at `http://127.0.0.1:8787` via `python -m goofish_insight.cli serve-web`

## Local Start

```bash
python -m goofish_insight.cli serve-web --host 127.0.0.1 --port 8787
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787).
