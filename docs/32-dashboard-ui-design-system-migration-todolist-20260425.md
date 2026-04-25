# Dashboard UI Design System Migration Todolist

Date: 2026-04-25

Goal: make Goofish Insight dashboard UI follow the buyer-decision design constitution: decision-first, quiet UI, loud data, one screen one job, token-only styling, dual theme, audited primitives, and bounded composite components.

## Status

- [x] Persist the constitution as a project rule for future UI work.
- [x] Add canonical design tokens and dual theme files.
- [x] Make Light the default theme and keep Dark available through system preference plus top-bar toggle.
- [x] Replace the old screen shell naming with `AppFrame`.
- [x] Add the required top-bar affordances: logo, global search, category switch, notification entry, theme entry, user entry.
- [x] Re-route `/` to today's opportunity decision desk and move the old market dashboard to `/market`.
- [x] Add `/watch` for watch targets plus baselines.
- [x] Add `/ops/runtime`, `/ops/llm-devops`, and `/ops/progress` under one ops workbench.
- [x] Keep legacy routes as redirects.
- [x] Install and expose the 16 shadcn-style primitives already needed by the React dashboard.
- [x] Add the 4 allowed business composites: `OpportunityCard`, `AnalyticsCard`, `KpiTile`, `PriceGauge`.
- [x] Start replacing bespoke opportunity/KPI/panel DOM with those composites in the opportunity-first surface.
- [x] Remove legacy raw-color feature styles by centralizing token-only app styles in `shared/styles/app-ui.css`.
- [x] Reduce handwritten CSS below the size budget.
- [x] Add a design-system audit script for raw colors, retired visual language, motion hazards, required theme files, and CSS budgets.
- [x] Wire design-system checks into dashboard React scripts and root audit scripts.
- [x] Wire design-system audit into the dashboard CI script.
- [x] Run full design-system audit.

## Current Evidence

- Design audit: `npm run design-system:audit -w @goofish/dashboard-react`
- Dashboard CI script: `bash scripts/ci/run_dashboard_checks.sh`
- CSS budget after migration: total dashboard CSS is under 20KB.
- Required theme files exist:
  - `apps/dashboard-react/src/themes/tokens.css`
  - `apps/dashboard-react/src/themes/light.css`
  - `apps/dashboard-react/src/themes/dark.css`
- Shared style entry: `apps/dashboard-react/src/shared/styles/app-ui.css`
- App shell entry: `apps/dashboard-react/src/shared/components/AppFrame.tsx`
- Business composite entry: `apps/dashboard-react/src/shared/components/business/index.ts`

## Current PR Gate Evidence

- [x] `npm run design-system:check -w @goofish/dashboard-react`
- [x] `npm run design-system:audit -w @goofish/dashboard-react`
- [x] `npm run verify-baseline`
- [x] Light and Dark visual inspection on the touched route
- [x] Decision states render both color and shape/text, never color only

Future dashboard UI PRs must keep these gates green:

- `npm run design-system:check -w @goofish/dashboard-react`
- `npm run design-system:audit -w @goofish/dashboard-react` for broad UI migrations
- `npm run verify-baseline` before reporting completion
- Light and Dark visual inspection on the touched route
- Decision states render both color and shape/text, never color only
