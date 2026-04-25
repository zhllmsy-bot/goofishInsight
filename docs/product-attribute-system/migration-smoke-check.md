# Catalog 迁移自检 SOP

## 1. 目的

在每次完成 catalog 迁移相关改动后，用统一命令确认：

- Alembic revision 正确
- 类目模板已发布
- SPU / SKU 查询链路可读
- 目标 SPU 模板版本符合预期
- catalog outbox 没有残留 pending/failed
- scoped backfill 域的覆盖率已达目标

## 2. 标准命令

```bash
cd <repo-root>
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli check-catalog-scoped-migration \
  --category-id 11111111-1111-1111-1111-111111111101 \
  --spu-id 8ba511b5-77db-4431-a905-4a4098ce09e8 \
  --expected-template-id 11111111-1111-1111-1111-111111111403 \
  --business-domain apple_m_series \
  --business-domain garmin \
  --page-size 20
```

## 3. 重点检查项

- `alembicRevision`
  - 应为当前 head，例如 `20260405_0008`
- `categoryTemplates.templateCount`
  - 应大于 `0`
- `spuPage.total`
  - 目标类目下应能查到数据
- `skuPage.total`
  - 目标 SPU 下应能查到 SKU
- `spuDetail.templateId`
  - 应与 `expectedTemplateId` 一致
- `latestCatalogOutbox.status`
  - 正常应为 `DONE`
- `backfillReconciliation[*].coverageRatio`
  - scoped 域应达到目标值，当前基线是 `1.0`
- `checks[*].ok`
  - 应全部为 `true`

## 4. 异常处理

- 如果 `spu_template_matches_expected = false`
  - 说明升级还没执行到目标模板，先查 `preview/apply` 历史
- 如果 `catalog_outbox_cleared = false`
  - 先执行：
  ```bash
  PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli process-catalog-outbox --apply
  ```
  - 然后重新跑 `check-catalog-scoped-migration`
- 如果 `*_coverage_complete = false`
  - 先跑对应域的 `report-catalog-backfill-reconciliation`
  - 再决定是否补跑 `run-catalog-backfill-migration --allow-warnings`
- 如果 `category_templates_available = false`
  - 先补模板初始化或模板版本发布

## 5. 适用场景

- 迁移脚本执行后
- 模板版本发布后
- 模板升级 / replace-plan 执行后
- 提交前或推送 OV 前的最终自检
