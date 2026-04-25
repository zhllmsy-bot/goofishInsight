# Goofish Insight 系统收口任务包索引

Status: Active
Updated: 2026-04-22
Source: 2026-04-19 基于当前仓库真实状态的整体质量盘点与主线收口要求

## 目的

把当前仓库“全部该做的事”拆成可以独立派发、独立验收、尽量减少写文件冲突的任务包。

这批任务包不是泛化路线图，而是围绕当前仓库已经暴露出来的真实问题做系统收口：

1. React 主前端还没有彻底收完。
2. analyzer 虽然已经接手一部分买方决策逻辑，但边界还不稳。
3. BFF / FastAPI / React 三层合同仍不完整。
4. 配置、onboarding、runtime、overlay 这些运营面还没有统一成一个清晰产品面。
5. 文档叙事、工具链、验证口径仍然存在漂移。

## 当前总判断

当前仓库最应该做的不是继续加新功能，而是完成下面 5 件事：

1. 彻底结束“双前端”状态，明确 React 是唯一主工作台。
2. 把 analyzer 从“挂在 collector 上的分析脚本集”收成真正的分析边界。
3. 补齐主工作流的页面与 API contract，避免新页面只迁壳不迁能力。
4. 把配置、onboarding、overlay、runtime 这些运营面统一到同一套产品叙事。
5. 用统一验证和文档把真实现状钉死，防止再次漂移。

## 拆分规则

1. 一个源码热点文件同一轮尽量只归一个任务包。
2. 任务包优先围绕“完整问题闭环”拆，不围绕单个函数拆。
3. 每个任务包都必须带目标、范围、不做、验证、完成定义。
4. 文档任务包不能脱离代码现实单独扩张。
5. 未进入本批任务包的事情，视为“现在不做”而不是“忘了做”。

## 任务包总览

执行看板：[`EXECUTION_BOARD_20260421.md`](./EXECUTION_BOARD_20260421.md)
总待办快照：[`MASTER_TODOLIST_20260422.md`](./MASTER_TODOLIST_20260422.md)

### P0 主链路收口

- [C01 React 主前端彻底收口](./C01-react-primary-surface-closeout.md)
- [C02 Config Center React 化与旧模板退场](./C02-config-center-react-migration.md)
- [C03 Onboarding React 深度收口](./C03-onboarding-react-deepening.md)
- [C04 Dashboard Nest 路由与代理补齐](./C04-dashboard-nest-route-and-proxy-parity.md)
- [C05 主工作流闭环 E2E 合同测试](./C05-primary-workflow-contract-tests.md)

### P1 analyzer / domain 边界收口

- [C06 Analyzer 边界去 collector 依赖](./C06-analyzer-boundary-decoupling.md)
- [C07 Buy-side 决策链全量迁入 analyzer](./C07-buy-side-domain-move-to-analyzer.md)
- [C08 Pricing / alert / explanation 领域收口](./C08-pricing-and-alert-domain-contracts.md)
- [C09 Analyzer 作业入口与运行契约统一](./C09-analyzer-job-runtime-contract.md)

### P1 运营与运行面收口

- [C10 Runtime 与 resident 能力统一产品面](./C10-runtime-and-resident-product-surface.md)
- [C11 Mobile Overlay 接入主工作台](./C11-mobile-overlay-workbench-integration.md)
- [C12 Android Overlay 工程可交付化](./C12-android-overlay-delivery-hardening.md)

### P2 工具链、文档、验证收口

- [C13 Monorepo 工具链统一](./C13-monorepo-tooling-alignment.md)
- [C14 文档叙事与现状对齐](./C14-documentation-reality-alignment.md)
- [C15 质量门禁与交付基线收口](./C15-quality-gates-and-release-baseline.md)

## 推荐顺序

1. 先做 `C01`、`C04`、`C05`，把主前端和主链路合同钉住。
2. 再做 `C02`、`C03`，把剩余核心运营面收回 React。
3. 随后推进 `C06`、`C07`、`C08`、`C09`，完成 analyzer 真实边界收口。
4. 再处理 `C10`、`C11`、`C12`，把运行面和移动端辅助面纳入统一产品面。
5. 最后做 `C13`、`C14`、`C15`，统一工具链、文档和验收基线。

## 显式不现在做

1. 不做微服务化。
2. 不做新的 BFF 架构扩张。
3. 不做 Next.js 迁移。
4. 不做新的 task pack 文档扩写，除非直接服务于当前收口任务。
5. 不做新的业务大类扩张，先把现有 `apple_m_series`、`garmin_watch` 相关主链路收稳。

## 验收总口径

完成这批任务后，应该能明确回答：

1. React 是否已经成为唯一主运营前端。
2. analyzer 是否已经从 collector 的脚本附属层，变成稳定分析边界。
3. 主工作流是否具备跨页面、跨后端、跨部署模式的一致合同。
4. 文档、代码、验证结果是否终于说的是同一件事。
