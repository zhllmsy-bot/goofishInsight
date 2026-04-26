# ADR-0003 SKU 指纹与样本事实层

Status: Accepted
Date: 2026-04-26

## Context

Goofish Insight 的价格基线已经收敛到 `schema_id` 合同，但现有事实层仍然只保留 `items`、`item_snapshots` 和 `item_spec_enrichments`。随着买方侧继续扩展，样本需要有一个稳定、可回放、可审计的持久化层，才能把“同一 listing 属于哪个 SKU 指纹、当前是可计价样本还是缺字段样本”固定下来。

## Decision

新增两张显式事实表：

- `sku_fingerprints`
- `item_samples`

关键约束：

- `sku_fingerprints.schema_id` 为非空外键，必须复用 `sku_spec_schema_snapshots.schema_id`
- 指纹 hash 必须把 `schema_id` 作为 seed 的一部分
- `item_samples` 必须保留 `sample_state`、`missing_required_attrs`、`sample_quality_score`、`observed_at`
- `item_samples` 允许携带 `condition_multiplier`，但不把成色修正直接写进价格基线

## Consequences

- 价格基线输入从“只读记录”演进为“记录 + 样本事实”
- 同一 listing 在不同 schema 版本下会形成不同 fingerprint
- 样本状态可以独立追踪，而不会污染 `items` 或 `item_snapshots`
- 未来如果需要兼容 view，可以在不改写上层调用的前提下提供只读投影

## Non-Goals

- 不在本 ADR 中实现完整成色引擎
- 不在本 ADR 中引入 Redis 或分布式队列
- 不在本 ADR 中替换现有 `buy_price_baseline` 决策表
