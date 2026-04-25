# Goofish Insight 全量独立任务总清单（2026-04-22）

Status: Active  
Owner: codex + user 协同推进

## 说明

每条任务都对应一个独立 task-pack md，可单独验收、单独回归、单独关闭。以下状态按 2026-04-22 最新代码与验证结果更新。

## 已完成（Done）

1. C01 React 主前端彻底收口（主路径）  
   File: `C01-react-primary-surface-closeout.md`
2. C05 主工作流闭环 E2E 合同测试  
   File: `C05-primary-workflow-contract-tests.md`
3. C09 Analyzer 作业入口与运行契约统一  
   File: `C09-analyzer-job-runtime-contract.md`
4. C12 Android Overlay 工程可交付化  
   File: `C12-android-overlay-delivery-hardening.md`
5. C13 Monorepo 工具链统一  
   File: `C13-monorepo-tooling-alignment.md`
6. C15 质量门禁与交付基线收口（phase-1）  
   File: `C15-quality-gates-and-release-baseline.md`

## 进行中（In Progress）

1. C04 Dashboard Nest 路由与代理补齐（phase-1 landed）  
   File: `C04-dashboard-nest-route-and-proxy-parity.md`  
   Next: 补齐剩余 BFF 主链路代理缺口，保持 FastAPI/Nest 路由对齐。
2. C06 Analyzer 边界去 collector 依赖（phase-2）  
   File: `C06-analyzer-boundary-decoupling.md`  
   Next: 继续把 pricing/guidance 决策读模型迁到 analyzer，collector 保持薄层。
3. C07 Buy-side 决策链全量迁入 analyzer（phase-2 landed）  
   File: `C07-buy-side-domain-move-to-analyzer.md`  
   Next: 继续清理剩余 buy-side shim，收敛 analyzer export。
4. C08 Pricing / alert / explanation 领域收口（phase-1 landed）  
   File: `C08-pricing-and-alert-domain-contracts.md`  
   Next: 固化 canonical pricing contract 到 analyzer 侧读模型。
5. C10 Runtime 与 resident 能力统一产品面  
   File: `C10-runtime-and-resident-product-surface.md`  
   Next: 把运行状态面做成运营可执行动作面，并与采集健康快照联动。

## 待启动（Proposed）

1. C02 Config Center React 化与旧模板退场（最终清退）  
   File: `C02-config-center-react-migration.md`
2. C03 Onboarding React 深度收口  
   File: `C03-onboarding-react-deepening.md`
3. C11 Mobile Overlay 接入主工作台  
   File: `C11-mobile-overlay-workbench-integration.md`
4. C14 文档叙事与现状对齐  
   File: `C14-documentation-reality-alignment.md`

## 当前并行执行焦点

1. 采集实跑：`collect-batch --only-task garmin-fenix --parallel-tabs 1` 已完成一轮，`show-health` 连续 `pages_succeeded=5`。  
2. 分层收口：buy-side template monitoring 已迁到 analyzer，继续推进 pricing/guidance 合同。
