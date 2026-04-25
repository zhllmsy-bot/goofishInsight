# Review Calibration Labeling SOP

## Goal

Use human labels to decide:

- whether current review thresholds are reliable enough
- whether pricing-pool samples are safe enough for profit decisions
- which samples should stay on `Qwen3`
- which samples should move to dense second-pass
- which tail cases should stay manual

Do not use this SOP to maximize coverage. Use it to maximize trust in downstream pricing and profit conclusions.

## Files

The calibration builder produces two files:

- rich JSON
- flat CSV annotation sheet

Example:

- [review-calibration-initial-20260404.json](../reports/review-calibration-initial-20260404.json)
- [review-calibration-initial-20260404.annotation.csv](../reports/review-calibration-initial-20260404.annotation.csv)

## Buckets

Each sample belongs to one primary bucket:

- `valid`
- `invalid`
- `pending_audit`
- `high_profit_high_risk`

Interpretation:

- `valid`: current model thinks it is safely valid
- `invalid`: current model thinks it is safely invalid
- `pending_audit`: current system thinks it is too risky or unresolved
- `high_profit_high_risk`: current pricing context says this item could matter economically, but the review gate still blocks or doubts it

## Required Human Labels

Fill these columns first:

- `annotation_review_status`
- `annotation_pricing_safe`

Allowed values:

- `annotation_review_status`: `valid`, `invalid`, `pending_audit`
- `annotation_pricing_safe`: `true`, `false`

## Optional But Recommended Labels

- `annotation_risk_level`: `low`, `medium`, `high`
- `annotation_needs_dense_second_pass`: `true`, `false`
- `annotation_needs_manual_tail_review`: `true`, `false`
- `annotation_notes`

## How To Judge `annotation_review_status`

Mark `valid` when:

- the listing is clearly selling the target device
- it is not mainly buying, recycling, subsidy-service, 代拍, or导流
- product evidence is strong enough that this row should count as a real device sale sample

Mark `invalid` when:

- the post is clearly buying or recycling
- the post is mainly a service flow, subsidy flow, commercial ad, or accessory / parts listing
- the post is not really the target product

Mark `pending_audit` when:

- there is real ambiguity even after reading the row
- you would not trust it in pricing yet
- it feels too risky to collapse into either valid or invalid without more evidence

Do not force a row into `valid` or `invalid` just to reduce the pending bucket.

## How To Judge `annotation_pricing_safe`

This is stricter than review validity.

Mark `true` only when:

- you would allow this row to influence profit or收货判断
- the item looks like a real comparable market sample
- there is no major risk that this row would distort fair-price or buy-ceiling calculations

Mark `false` when:

- the listing may be real, but still too noisy for pricing
- the sample is economically misleading
- there is too much ambiguity in model/spec/accessories/sales context

A row can be:

- `annotation_review_status = valid`
- but `annotation_pricing_safe = false`

This is expected for profit-sensitive work.

## How To Set `annotation_needs_dense_second_pass`

Mark `true` when:

- first-pass behavior looks too weak or too noisy
- the row is recoverable by a more careful model
- the business value is high enough that a denser second-pass is justified

Good examples:

- current system put it in `pending_audit`, but you think it may be a true valid sale row
- current system marked it invalid, but you think it may be rescuable
- high-profit candidates where precision matters more than throughput

## How To Set `annotation_needs_manual_tail_review`

Mark `true` when:

- even dense second-pass may still be too risky
- the row is economically important and ambiguous
- a wrong decision would meaningfully distort pricing or profit conclusions

This is mainly for the high-value tail, not for common rows.

## Recommended Review Routine

1. Read `title`, `listing_description`, `condition_tags`, and current price first.
2. Check current model prediction and current pricing context.
3. Decide `annotation_review_status`.
4. Decide `annotation_pricing_safe`.
5. Only then decide whether the row belongs in dense second-pass or manual tail.

## Validation Before Evaluation

Always validate the sheet first:

```bash
cd <repo-root>
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli validate-review-calibration-set \
  reports/review-calibration-initial-20260404.annotation.csv
```

Then evaluate:

```bash
cd <repo-root>
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli evaluate-review-calibration-set \
  reports/review-calibration-initial-20260404.annotation.csv
```

## Reading The Evaluation

Focus on:

- `current_policy_metrics.auto_valid`
- `current_policy_metrics.auto_invalid`
- `current_policy_metrics.pricing_pool`
- `threshold_sweeps`
- `model_lane_observations`

The intended operating split is:

- `Qwen3` for broad first-pass screening
- dense second-pass for profit-sensitive or unresolved rows
- manual tail for the small, high-value ambiguous set

The calibration sheet is what decides where those boundaries should move.
