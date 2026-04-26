# ADR-0002: Jinja legacy 收敛决策

Status: Accepted
Date: 2026-04-26
Owners: core maintainers

## Context

项目存在两套 UI 执行面：React 主工作台与 Jinja legacy 运维页。双栈并存导致样式、交互和路由判断分裂，且增加了配置页、告警流、机会核验的长期维护成本。

## Decision

确认 `apps/web` 为 legacy 支持壳，不作为 V1.0 主操作路径，主线能力收敛为：

1. `apps/dashboard-react`：买方主决策入口（今日机会台为首页）
2. `apps/dashboard-nest`：静态托管与部署回退入口
3. `apps/web`：仅保留明确支持列表中的 admin/support 回查路径；不新增运营主链路功能。

若要继续支持 legacy，必须提供“支持边界清单”；否则在下一阶段启动前进入物理归档。

## Consequences

- React dashboard 成为唯一决策主站，视觉与交互收口更快。
- Jinja 页面不再参与核心机会页功能设计与 CI 关键路径，降低重复开发。
- 技术栈收缩后，配置页/机会页/反馈路径可复用统一组件系统（`OpportunityCard` 等）。

## Validation

- `README` 与 `docs` 中明确标注 `apps/web` 的支持边界。
- `docs/32-dashboard-ui-design-system-migration-todolist-20260425.md` 与 `docs/38-goofish-insight-global-reassessment-v2-todolist-20260426.md` 中，对 Jinja legacy 相关项目保持同步更新。
- 运行 baseline 验收时不得将 Jinja 新增功能作为 release gate 依赖。

## Migration Notes

- 保留最小回查与运维路径：仅限无法短期替代的历史流程，并为每个路径维护过渡说明。
- 新功能优先落地到 React 后，再评估 legacy 删除或独立归档。
