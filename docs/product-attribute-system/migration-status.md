# Catalog 迁移状态

更新时间：2026-04-05

## 1. 当前已完成

### 1.1 数据模型与迁移

- Alembic 迁移已落地
- `.4` 开发库当前 revision 为 `20260405_0008`
- 核心表已就位：
  - `category`
  - `attribute_definition`
  - `attribute_option`
  - `category_attr_template`
  - `category_attr_template_item`
  - `product_spu`
  - `product_sku`
  - `product_spu_attr_value`
  - `product_sku_attr_value`
  - `outbox_event`
  - `product_attr_audit_log`

### 1.2 写链路

- 模板初始化
- 模板版本发布
- 商品 create
- 商品 replace
- 模板升级预检
- 模板自动升级 apply
- 模板 replace-plan preview/apply
- `snapshot` 同步写入
- `outbox_event` 写入
- 审计日志写入
- 旧表 backfill 模板 bootstrap
- 单条旧表 item backfill persist
- 批量旧表 item backfill dry-run
- 批量旧表 item backfill apply
- 域级 backfill migration runner
- backfill 对账报告与覆盖率汇总

### 1.3 读链路

- SPU 详情
- SKU 列表
- 模板详情
- 类目模板版本列表
- SPU 分页查询
- SKU 分页查询

### 1.4 运维与验证

- catalog outbox consumer 已实现
- `check-catalog-migration` 已实现
- `check-catalog-scoped-migration` 已实现
- `migration-smoke-check.md` 已提供 SOP
- 当前 catalog 相关单测：`100/100` 通过

## 2. 当前开发库验证状态

`.4` 开发库已验证：

- 类目：`phone`
- 模板版本：`v1 / v2 / v3`
- 样例 SPU：`8ba511b5-77db-4431-a905-4a4098ce09e8`
- 当前 SPU 模板：`11111111-1111-1111-1111-111111111403`
- 当前最新 outbox：`DONE`
- 已新增 backfill 类目与模板：
  - `apple_m_series`：`33333333-3333-3333-3333-333333333101 / 33333333-3333-3333-3333-333333333401`
  - `garmin_watch`：`22222222-2222-2222-2222-222222222101 / 22222222-2222-2222-2222-222222222401`
- 已真实写入 backfill 样本：
  - Apple SPU：`3660a485-886b-54e5-96c6-4165e292088d`
  - Garmin SPU：`0063e647-22d9-549c-9312-53765bb287c3`
- 已完成域级 backfill apply：
  - Apple：`legacyEnrichedItemTotal = 3923`，`migratedSpuTotal = 3923`，`coverageRatio = 1.0`
  - Garmin：`legacyEnrichedItemTotal = 301`，`migratedSpuTotal = 301`，`coverageRatio = 1.0`
- 两个域当前 `pendingOutboxTotal = 0`

迁移自检命令：

```bash
cd <repo-root>
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli check-catalog-migration \
  --category-id 11111111-1111-1111-1111-111111111101 \
  --spu-id 8ba511b5-77db-4431-a905-4a4098ce09e8 \
  --expected-template-id 11111111-1111-1111-1111-111111111403 \
  --page-size 20
```

域级 backfill 对账命令：

```bash
cd <repo-root>
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli report-catalog-backfill-reconciliation apple_m_series
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli report-catalog-backfill-reconciliation garmin
```

总检命令：

```bash
cd <repo-root>
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli check-catalog-scoped-migration \
  --category-id 11111111-1111-1111-1111-111111111101 \
  --spu-id 8ba511b5-77db-4431-a905-4a4098ce09e8 \
  --expected-template-id 11111111-1111-1111-1111-111111111403 \
  --business-domain apple_m_series \
  --business-domain garmin
```

## 3. 本轮已完成的迁移范围

本轮迁移的完成口径是：

- `items + item_spec_enrichments` 到 catalog 的映射已落地
- `apple_m_series` 与 `garmin` 两个业务域的目标模板已 bootstrap 到 `.4`
- enriched item 的 batch dry-run / batch apply / outbox drain / reconciliation 已全部跑通
- 当前这两个业务域的 enriched item 在 `.4` 开发库覆盖率都已达到 `1.0`

## 4. 超出本轮范围的后续工作

这些不是“当前迁移没做完”，而是下一阶段扩展项：

### 4.1 搜索索引真实写入

- 当前 outbox consumer 只做 catalog 侧一致性校验
- 还没有接真实搜索索引写入

### 4.2 正式业务接入

- 当前入口仍以内部工具 / admin 命令为主
- 还没有补正式鉴权、中间件、统一错误码、幂等表

### 4.3 非 enriched 历史数据策略

- 当前已完成的是 enriched item 迁移
- `legacyItemTotal` 大于 `legacyEnrichedItemTotal` 的那部分旧数据，仍需单独定义降级映射或补充 enrich 策略

### 4.4 生产级灰度切流

- 还没有执行生产级灰度读切换
- 还没有执行正式回滚演练

## 5. 结论

如果以“本轮约定的 catalog 迁移范围是否完成”为标准：

- 当前已经完成

如果以“是否已经进入生产级业务切流”为标准：

- 当前还没有开始正式切流

也就是说，现在已经从“设计阶段”推进到了“`.4` 开发库真实迁移完成，且本轮 scoped backfill 已经收口”的状态。
