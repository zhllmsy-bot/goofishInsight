# Goofish Insight 并发任务包索引

Status: Active
Updated: 2026-04-15
Source Todo: [28-goofish-insight-upgrade-implementation-todolist-20260413.md](<repo-root>/docs/28-goofish-insight-upgrade-implementation-todolist-20260413.md)

## 目的

把主 Todo 中剩余未完成项拆成可以独立派发、独立验收、尽量不改同一文件的任务包，方便并发执行。

## 拆分规则

1. 以“独占写文件”为第一原则，一个文件同一轮只归一个任务包。
2. `cli.py`、`specs.py`、`pricing.py` 属于跨工作流热点文件，不参与本轮并发，统一放到最后的串行收口包。
3. `Buffer Week`、阶段验收、每周节奏、阶段交付物、最终验收口径这类门禁项，不单独建任务包；对应任务完成后统一回填主 Todo。
4. 测试文件、fixtures、报告文件默认跟随所属任务包，不单独视为冲突源。

## 任务包总览

### 第一批可立即并发

- [T1 Runtime 状态机与 runtime 可视化](./T1-runtime-state-machine.md)
- [T2 Analyzer 稳定性与 Phase 3 数据源合同](./T2-analyzer-stability.md)
- [T3 Webhook 告警通道](./T3-webhook-alert-channel.md)
- [T4 规则回放与 price_sanity_score](./T4-rule-replay-and-price-sanity.md)
- [T5 category_compat 与 admin scope 收口](./T5-category-compat-admin-scope.md)
- [T6 Catalog contract test 与回滚工件](./T6-catalog-contract-and-rollback.md)
- [T9 BFF 拓扑文档与 React 直连 FastAPI](./T9-bff-cutover.md)
- [T10 Dashboard 高频动作路径](./T10-dashboard-action-flow.md)
- [T11 Buy 页迁移与反馈联动](./T11-buy-page-feedback-linkage.md)

### 第二批接续

- [T7 Catalog backfill 覆盖补缺](./T7-catalog-backfill-coverage.md)

### 第三批切流

- [T8 Catalog 主读切换](./T8-catalog-primary-read-cutover.md)

### 最后串行收口

- [S1 CLI shell / purity 验收](./S1-cli-purity-closeout.md)

## 推荐顺序

1. 先并发执行第一批。
2. `T7` 在吸收 `T4/T5` 产物后继续推进，但只允许改 `catalog_backfill.py` 一组文件。
3. `T8` 必须等待 `T6 contract test` 通过且 `T7 coverage/parity` 达标。
4. 最后再执行 `S1`，统一做 entrypoint purity 和热点文件收口。

## 不单独派工的门禁项

- `清理 Phase 1 遗留的阻塞项`
- `Phase 1 核心阻塞项清零`
- `核心工作流可以进入 Phase 2，不带已知 P1 缺陷`
- `清理 flaky 测试`
- `每周执行节奏`
- `每阶段必交付物`
- `最终验收口径`
