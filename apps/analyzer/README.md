# Analyzer

`apps/analyzer` 是 Goofish Insight 的分析边界模块，负责聚合、评分、报告和买方决策读模型。

## 当前职责

- 买方决策聚合：`goofish_analyzer.services.buy_decision_hub`
- 买方机会刷新与查询：`goofish_analyzer.services.buy_opportunities`
- 买方反馈写回与质量统计：`goofish_analyzer.services.buy_feedback`
- 反馈校准建议：`goofish_analyzer.services.buy_feedback`
- 批处理核心：`daily_metrics` / `model_scores` / `analysis_reports` 的生成

## 当前边界

- `collector` 继续负责采集、落库、规则和运行控制，不再作为买方决策主入口继续膨胀
- analyzer 不负责采集、不负责浏览器驱动、不负责 runtime 控制
- analyzer 消费 `items` / `item_spec_enrichments` 等采集事实层产出，产出分析读模型

## 与 collector 的关系

- collector 是数据事实源，analyzer 是分析消费方
- 买方工作台的 workbench 聚合、机会刷新、反馈写回已经从 collector 迁入 analyzer
- `daily_metrics` / `model_scores` / `analysis_reports` 仍是 analyzer 的批处理核心
- 部分分析逻辑仍留在 collector 中（过渡期），后续继续迁入

## 当前状态

- 买方决策链路已基本迁入
- 聚合、评分、报表生成仍在过渡中，部分仍以 ad hoc CLI 和 shell 片段存在
- 目标：分析作业不再主要以 ad hoc CLI 存在，所有分析入口统一到 analyzer
