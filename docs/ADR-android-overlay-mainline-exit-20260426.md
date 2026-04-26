# ADR-0001: Android overlay 主线退出决策

Status: Accepted
Date: 2026-04-26
Owners: core maintainers

## Context

项目当前目标是作为“Local-First 买手决策工作台”稳定运行。`apps/android-overlay` 在主仓中提供了 Android 辅助采集能力，但其维护模式与主链路能力（collector / analyzer / dashboard）不同，且会消耗额外测试、文档与运行上下文。

## Decision

确认 `apps/android-overlay` 不作为 v1.0 主线能力交付；主线 release 只追求：

1. `apps/collector`（采集/清洗/规则）
2. `apps/analyzer`（分析作业）
3. `apps/dashboard-react`（主工作台）
4. `apps/dashboard-nest`（回退/BFF）

`apps/android-overlay` 进入实验性边界，待下列任一方案完成后迁移出主仓：

- 移入 `labs/android-overlay` 并在主文档中声明实验性；
- 或独立仓库单独维护；
- 或明确归档、停止变更与依赖。

## Consequences

- `Android overlay` 的交付节奏从 v1.0 主路径剥离，减少主线门禁压力。
- 主文档中的“主站能力边界”更清晰，避免把 overlay 功能误入产品成功定义。
- 所有主链路用户体验测试和 CI 门禁可聚焦于稳定工作流。

## Validation

- 完成该 ADR 后，需在 `docs/38-goofish-insight-global-reassessment-v2-todolist-20260426.md` 将“主线退出决策”相关条目标记为已完成，并补充执行计划（迁移路径 + 归档时间）。

## Notes

- 该决策不意味着 overlay 功能废弃；只约束其不进入 v1.0 主交付 KPI。
