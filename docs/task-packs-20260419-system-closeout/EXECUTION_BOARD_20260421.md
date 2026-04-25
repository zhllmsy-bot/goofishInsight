# Goofish Insight 收口执行板（2026-04-21）

Status: Active  
Updated: 2026-04-22

## 目标

把“评估问题 -> 拆任务 -> 逐条落地 -> 回归验证 -> 运行采集”串成可执行闭环，避免只停在建议层。

## 任务分解（独立可验收）

- [x] T01 单前端主路径收口（React 为唯一主工作台）  
  Task Pack: `C01-react-primary-surface-closeout.md`  
  Result: `/`、`/runtime`、`/buy/opportunities`、`/items/:id` 维持 React Shell 主入口，相关路由合同测试持续通过。

- [x] T02 看板筛选 -> 买方机会 -> 反馈回写 -> 返回看板 闭环测试  
  Task Pack: `C05-primary-workflow-contract-tests.md`  
  Result: 后端 round-trip + 前端 BuyWorkbench 闭环测试已补齐并通过。

- [x] T03 看板筛选 -> runtime -> 返回看板 闭环测试  
  Task Pack: `C05-primary-workflow-contract-tests.md`  
  Result: 后端 round-trip + 前端 Runtime 返回路径测试已补齐并通过。

- [x] T04 analyzer 边界收口（买方决策入口迁入 analyzer）  
  Task Pack: `C06-analyzer-boundary-decoupling.md` / `C07-buy-side-domain-move-to-analyzer.md`  
  Result: buy 入口改为 analyzer service hub，collector 侧保留薄适配层。

- [x] T05 buy feedback 错误契约统一（404/400）  
  Task Pack: `C08-pricing-and-alert-domain-contracts.md`  
  Result: `BuyFeedbackError` 映射到 HTTP 语义并补充测试覆盖。

- [x] T06 采集运行修复：analyzer/schema 路径依赖  
  Task Pack: `C10-runtime-and-resident-product-surface.md`  
  Result: runtime 脚本、launchd、CLI 统一 `PYTHONPATH=apps/collector/src:apps/analyzer/src:packages/schema/src`。

- [x] T07 采集运行修复：home feed 决策表缺失  
  Task Pack: `C10-runtime-and-resident-product-surface.md`  
  Result: Alembic 升级到 head，`home_feed_item_decision` 缺表问题消除。

- [x] T08 采集运行修复：category_validation_status 长度溢出  
  Task Pack: `C10-runtime-and-resident-product-surface.md`  
  Result: 新增 migration `20260421_0037`，字段长度 32 -> 64，风控分类状态写入恢复。

- [x] T09 本地采集实跑验证（attached browser batch collect）  
  Task Pack: `C10-runtime-and-resident-product-surface.md`  
  Result: `collect-batch --only-task garmin-fenix --parallel-tabs 1` 本轮已完整跑完；`show-health` 最新多条 run 均 `status=completed` 且连续 `pages_succeeded=5`（如 `2b97d904-9a65-4c15-9a32-31de4a52912d`）。

- [x] T10 双前端遗留面彻底清退说明（admin/support-only 标注 + 文档对齐）  
  Task Pack: `C01-react-primary-surface-closeout.md` / `C14-documentation-reality-alignment.md`  
  Result: `/config/categories|templates|tasks` 入口切到 React，`/config/attributes|models|raw-cate-policy` 标记为 legacy admin/support。

- [x] T11 analyzer 适配层去 collector 深依赖（第二轮）  
  Task Pack: `C06-analyzer-boundary-decoupling.md` / `C09-analyzer-job-runtime-contract.md`  
  Result: 新增 analyzer adapter 边界 allowlist 契约测试并纳入 baseline，防止依赖反向扩散。

- [x] T12 统一质量门禁脚本（Python + React + Nest）  
  Task Pack: `C13-monorepo-tooling-alignment.md` / `C15-quality-gates-and-release-baseline.md`  
  Result: `verify-baseline` 与 `scripts/ci/run_dashboard_checks.sh` 已切换到 Nest e2e，并纳入本轮闭环/配置路由相关 Python 测试子集。

- [x] T13 buy-side template monitoring 迁入 analyzer（collector 仅保留薄层）  
  Task Pack: `C07-buy-side-domain-move-to-analyzer.md` / `C08-pricing-and-alert-domain-contracts.md`  
  Result: `buy_template_monitoring` 新建到 analyzer，collector `pricing_monitoring` 改为 shim，`/api/buy/template-monitoring` 改由 analyzer service 提供。

## 本轮关键验证结果

- Python:
  - `apps.analyzer.tests.test_buy_template_monitoring`
  - `apps.analyzer.tests.test_buy_decision_hub`
  - `apps.collector.tests.test_buy_entrypoints`
  - `apps.collector.tests.test_pricing_entrypoints`
  - `apps.analyzer.tests.test_adapter_boundary_contract`
  - Result: PASS（18 tests）

- React:
  - `BuyWorkbenchPage.test.tsx`
  - `RuntimePage.test.tsx`
  - `workspaceFlows.test.ts`
  - Result: PASS（7 tests）

## 下一步执行顺序

1. 继续压缩 analyzer 对 collector 的剩余深依赖（pricing reporting / guidance 读模型口径）。  
2. 推进 C02/C03/C10 的产品面收口，缩小 legacy 模板在主流程中的存在感。
