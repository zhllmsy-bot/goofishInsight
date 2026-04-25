# Dashboard React Architecture

## Why this refactor exists

The first dashboard iteration proved out the UX direction, but it concentrated routing, remote data access, URL state, interaction rules, and all major panels inside a single `App.tsx`. That shape is fast for a prototype and expensive for a product team.

This refactor moves the dashboard toward a feature-first structure with explicit separation between:

- server state
- client UI state
- presentation components
- selectors and formatting logic
- runtime validation

## Current structure

```text
apps/dashboard-react/src/
  app/
    App.tsx
    providers/
      AppProviders.tsx
  features/
    dashboard/
      api/
        dashboardApi.ts
        dashboardSchemas.ts
      components/
        DashboardHeader.tsx
        DashboardPage.tsx
        DashboardSidebar.tsx
        FocusPanel.tsx
        ListingsPanel.tsx
        PricingPanel.tsx
        PriceGauge.tsx
        ReferencePanel.tsx
        SelectionPanel.tsx
      hooks/
        useDashboardData.ts
        useDashboardStateGuards.ts
      lib/
        constants.ts
        formatters.ts
        selectors.ts
        urlState.ts
      store/
        dashboardUiStore.ts
      styles/
        dashboard.css
      types/
        dashboard.ts
  shared/
    lib/
      queryClient.ts
```

## Design choices

### Server state

- `TanStack Query` owns dashboard section fetching and caching.
- Section-level query keys make the slow reference panels independent from primary trading panels.
- Sidebar category product lists are prefetched and cached per category instead of being reconstructed ad hoc in view code.

### Client state

- `Zustand` owns UI-only state:
  - selected query
  - expanded category branch
  - active reference tab
- URL sync remains a thin hook so the store stays portable if the app later moves into Next.js routing primitives.

### Runtime validation

- `Zod` schemas validate every dashboard section response before it reaches the UI layer.
- Domain types are inferred from schemas to avoid drift between runtime and compile-time contracts.

### View composition

- `DashboardPage` is now a composition root, not a god component.
- Business rules such as listing classification and chip construction live in `selectors.ts`.
- Formatting and legacy link rules live in `formatters.ts`.

## What this still is not

This is a strong React front-end structure, but it is not yet a full Next.js App Router migration. That was deliberate for this pass:

- keep the new standalone dashboard service stable
- remove the monolith first
- make a future Next.js migration mechanical instead of risky

## Recommended next step

If we continue in the enterprise direction, the next high-leverage move is:

1. replace the standalone Vite entry with a Next.js 15 app shell
2. keep `features/dashboard/*` largely intact
3. move URL sync and route entry into App Router
4. introduce testing around selectors and panel rendering
