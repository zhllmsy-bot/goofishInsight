# CLI Entrypoints

## Purpose

`entrypoints/cli` registers the operator-facing commands exposed through `python -m goofish_insight.cli`.

## Current Command Areas

- database and health
- collection and discovery
- review-v3 validation, compatibility sync, and second-pass cleaning
- spec enrichment and pricing
- buy-side baselines, opportunities, alerts, and feedback
- maintenance tasks such as seller classification

## Operating Notes

- The canonical runtime command is still `python -m goofish_insight.cli`.
- `review-v3-second-pass` is the canonical second-pass CLI.
- `scripts/run-ark-review-cleaning.sh` is the repo's Ark wrapper and now forwards into `review-v3-second-pass`.
