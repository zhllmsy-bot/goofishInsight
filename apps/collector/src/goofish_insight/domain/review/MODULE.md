# Review Domain

## Purpose

`domain/review` holds stable review statuses, policy thresholds, and review-gate logic.

## Current Reality

It is the shared contract layer for:

- valid versus invalid review outcomes
- pricing gate eligibility
- confidence thresholds and pending-audit behavior

## Boundary

Prompt wording belongs in services. Shared review meanings and gates belong here.
