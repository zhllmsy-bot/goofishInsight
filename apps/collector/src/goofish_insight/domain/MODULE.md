# Domain Layer

## Purpose

`domain/` contains reusable rules, policies, and contracts that should not depend on CLI or web transport details.

## Current Subdomains

- `catalog/`: category, template, attribute, and model-catalog contracts
- `review/`: review statuses, gates, and validation policy

## Boundary

Keep stable enums, validation rules, and decision policy here when they must be shared by multiple services.
