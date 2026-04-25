# T7 Catalog backfill 覆盖补缺

Status: Done
Priority: P0
Source Todo: W7 coverage/parity 收敛
Done At: 2026-04-15

## 目标

持续补齐 Apple/Garmin 7 天 pricing 窗口缺口，让 coverage/parity 接近切流门槛。

## 独占文件

- [catalog_backfill.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_backfill.py)
- [test_catalog_backfill_service.py](<repo-root>/apps/collector/tests/test_catalog_backfill_service.py)
- [test_catalog_models.py](<repo-root>/apps/collector/tests/test_catalog_models.py)

## 范围

- Apple：重点补 `memory/storage`
- Garmin：重点补 `display_type/case_size_mm`
- 回填报表要包含 apply、skip reason、outbox 成功率

## 依赖

- 优先吸收 `T4` 的规则增强
- 优先吸收 `T5` 的 canonical scope 语义
- 不在本任务里重复修改 `normalizers.py` 或 `admin.py`

## 交付物

- `catalog 双读报表连续出数`
- Apple/Garmin coverage/parity 明显收敛

## 实际验收（2026-04-15）

- Apple 与 Garmin 的 7 天 dual-read 已收敛到 `coverageRatio=1.0`，`priceParityRatio` 分别为 `0.9982` 和 `0.9977`。
- `process-catalog-outbox --apply` 已处理 `458` 个事件且 `failedCount=0`。
- 最终 `check-catalog-scoped-migration` 返回 `overallOk=true`，目标类别的 outbox 已清空。

## 验证

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m unittest \
  apps.collector.tests.test_catalog_backfill_service \
  apps.collector.tests.test_catalog_models
```
