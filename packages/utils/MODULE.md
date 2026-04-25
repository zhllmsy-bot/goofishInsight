# Utils Package

Status: Retired legacy compatibility package.

## Purpose

Keep the historical extraction helpers available for smoke checks and reference.

## Boundary

Do not add new app code that depends on this package. New parsing and formatting logic belongs in app-local modules, and a shared package should only return if there are at least two real consumers.
