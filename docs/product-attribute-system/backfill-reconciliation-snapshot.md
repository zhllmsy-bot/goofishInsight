# Backfill 对账快照

更新时间：2026-04-05

## 1. 目标模板

### Apple M 系列

- category: `33333333-3333-3333-3333-333333333101`
- template: `33333333-3333-3333-3333-333333333401`

### Garmin

- category: `22222222-2222-2222-2222-222222222101`
- template: `22222222-2222-2222-2222-222222222401`

## 2. 已落地样本

### Apple

- `3660a485-886b-54e5-96c6-4165e292088d`
  - `MacBook Air / 15.3in / M3 / 16G / 512G`
- `e8f821a5-ccb4-5eaf-b7f3-741a189e0af4`
  - `Mac mini / M4 / 16G / 256G`

### Garmin

- `0063e647-22d9-549c-9312-53765bb287c3`
  - `Instinct 3 / AMOLED / 50mm / Solar`
- `88229536-598f-5513-9f3d-fc92d83168b8`
  - `Instinct / AMOLED / 45mm`

## 3. 域级迁移执行结果

### Apple

严格模式命令：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli \
  run-catalog-backfill-migration apple_m_series --operator-id ops-bot --batch-size 500 --apply
```

结果：

- `totalCandidates = 3923`
- `processedCount = 2892`
- `skippedCount = 741`
- `failedCount = 290`
- 主要 warning：`missing_memory_gb`、`missing_storage_gb`

补跑命令：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli \
  run-catalog-backfill-migration apple_m_series --operator-id ops-bot --batch-size 500 --apply --allow-warnings
```

补跑结果：

- `processedCount = 290`
- `skippedCount = 3633`
- `failedCount = 0`

### Garmin

严格模式命令：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli \
  run-catalog-backfill-migration garmin --operator-id ops-bot --batch-size 500 --apply
```

结果：

- `totalCandidates = 301`
- `processedCount = 145`
- `skippedCount = 2`
- `failedCount = 154`
- 主要 warning：`missing_display_type`、`missing_case_size_mm`

补跑命令：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli \
  run-catalog-backfill-migration garmin --operator-id ops-bot --batch-size 500 --apply --allow-warnings
```

补跑结果：

- `processedCount = 154`
- `skippedCount = 147`
- `failedCount = 0`

## 4. Outbox 校验

执行：

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli process-catalog-outbox --apply
```

结果：

- Apple / Garmin 两个域的迁移事件都已消费完成
- 当前 `pendingOutboxTotal = 0`
- `failedCount = 0`

## 5. 最终对账结果

### Apple M 系列类目

- `legacyItemTotal = 22166`
- `legacyEnrichedItemTotal = 3923`
- `migratedSpuTotal = 3923`
- `coverageRatio = 1.0`

### Garmin 类目

- `legacyItemTotal = 8754`
- `legacyEnrichedItemTotal = 301`
- `migratedSpuTotal = 301`
- `coverageRatio = 1.0`

## 6. 结论

- 当前范围内的 enriched item backfill 已经完成
- `skip-existing`、warning 分类、`--allow-warnings` 补跑都已验证可用
- 这份快照可以作为 `.4` 开发库的最终 reconciliation 基线
