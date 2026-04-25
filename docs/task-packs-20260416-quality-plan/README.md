# Goofish Insight 质量改进任务包索引

Status: Proposed
Updated: 2026-04-16
Source: 2026-04-16 非安全项质量盘点与代码现状复核

## 目的

把当前非安全类工程问题拆成可以独立派发、独立验收、尽量不改同一文件的任务包，便于多名开发者并行推进。

## 当前结论

1. 安全与鉴权相关项本轮不纳入。
2. 部分原始盘点结论需要校正：
   - Python 端并非“完全没有测试”，当前 `apps/collector/tests` 已有大量单测，问题主要在 React 侧缺少测试基座与关键交互覆盖。
   - `/healthz` 已存在于 FastAPI 与 Nest；本轮更需要的是结构化日志、错误追踪入口、请求超时与 CI 门禁。
   - React 直连 FastAPI 与 BFF 回滚开关已经有基础实现，但 origin 解析、超时与配置入口仍分散。
3. 并发拆分以“独占写文件”为第一原则；热点文件继续放到最后串行收口。

## 拆分规则

1. 同一轮内，一个源码文件只属于一个任务包。
2. `cli.py`、`specs.py`、`pricing.py`、`DashboardPage.tsx`、`ListingsPanel.tsx` 这类热点文件不放进第一批并发任务，统一放到串行收口包。
3. 新增文件默认跟随所属任务包，不视为冲突源。
4. 任务包必须自带验证命令，且尽量使用当前仓库已经存在的测试/构建入口。

## 第一批可并发

- [T12 Dashboard API 配置收口与请求超时](./T12-dashboard-api-config-and-timeouts.md)
- [T13 React Error Boundary 与路由恢复](./T13-react-error-boundary-and-route-recovery.md)
- [T14 Dashboard 可访问性语义补强](./T14-dashboard-accessibility-hardening.md)
- [T15 LLM Ops 组件拆分与常量提取](./T15-llm-ops-component-split.md)
- [T16 JS 工具链对齐与 React 测试基座](./T16-js-toolchain-alignment.md)
- [T19 Analyzer 可观测性与异常治理](./T19-analyzer-observability-hardening.md)
- [T20 文档与脚本可移植性清理](./T20-docs-and-script-portability.md)

### 已完成

- [T17 CI 质量门禁与本地脚本规范化](./T17-ci-quality-gates.md)
- [T18 packages/utils 去留决策与 ESM 化](./T18-packages-utils-decision.md)

## 第二批串行收口

- [S2 Collector 日志基础设施与异常治理](./S2-collector-logging-and-exception-foundation.md)
- [S3 Dashboard 热点组件拆分收口](./S3-dashboard-hotspot-decomposition.md)
- [S4 Backend 热点文件拆分收口](./S4-backend-hotspot-refactor.md)

## 推荐顺序

1. 先并发执行 `T12` 到 `T20`。
2. `S2` 等待 `T19` 完成后再启动，避免 Python 侧日志策略分叉。
3. `S3` 等待 `T13` 与 `T14` 完成后再启动，避免 React 壳层和可访问性改动冲突。
4. `S4` 最后执行，统一处理 `cli.py` / `specs.py` / `pricing.py` 三个热点文件。

## 文件冲突约束

- `T12` 独占 dashboard API/origin 配置相关文件。
- `T13` 独占 React app shell、boundary 组件与其样式。
- `T14` 独占 Dashboard 导航/标签语义文件与对应样式。
- `T15` 独占 LLM Ops 页面及其子组件。
- `T16` 独占 JS package/config/test harness 文件。
- `T17` 独占 `.github/workflows` 与 `scripts/ci/*`。
- `T18` 独占 `packages/utils/**`。
- `T19` 独占 `apps/analyzer/**`。
- `T20` 独占 README、专项文档与启动脚本整理范围。
- `S2` 独占 Collector logging/exception cluster。
- `S3` 独占 `DashboardPage.tsx`、`ListingsPanel.tsx` 及新增子组件。
- `S4` 独占 `cli.py`、`specs.py`、`pricing.py` 及对应审计文档。

## 不单独派工的事项

- 安全与鉴权
- 生产监控服务选型本身
- CSS Modules 全面迁移
- 全仓库 except Exception 一次性清零

这些内容要么本轮明确排除，要么会被拆进串行收口包中逐步消化。
