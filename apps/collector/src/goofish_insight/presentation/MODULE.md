# Presentation Layer

## Purpose

`presentation/` contains presentation-only helpers shared by templates and API serializers.

## Responsibilities

- display labels
- format helpers
- Jinja registrations
- UI-facing mapping helpers that do not need database writes

## Boundary

No ingestion, no browser control, and no heavy business decisions here.
