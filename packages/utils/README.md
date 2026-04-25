# @goofish-insight/utils

Status: Retired (legacy compatibility only)  
Updated: 2026-04-16

This package is kept for historical references and a small smoke check only. Do not add new consumers here.

## Why retired

- Current repo search shows no active imports outside this package.
- The package overlaps with app-local parsing and formatting code.
- A future shared package should only be recreated once there are at least two real consumers.

## Migration path

- Collector parsing and normalization belong in `apps/collector/src/goofish_insight/normalizers.py`.
- Dashboard UI formatting and selectors belong in feature-local `lib/` modules under `apps/dashboard-react/src/features/**`.
- If you need one of these helpers again, copy the logic into the owning app instead of depending on this package.

## Checks

```bash
npm run build
npm test
```

## Legacy API

The source files still expose the old extraction helpers for compatibility and smoke testing, but they are not a recommended shared dependency.
