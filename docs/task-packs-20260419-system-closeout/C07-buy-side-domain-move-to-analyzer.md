# C07 Buy-side 决策链全量迁入 analyzer

Status: In Progress (phase-2 landed, 2026-04-22)
Priority: P1

## 目标

把买方机会、反馈、校准、提醒命中、基线解释等“买方决策链”完整迁入 analyzer，collector 只保留采集、落库、运行控制和 API 代理职责。

## 为什么现在做

现在只迁了一部分，仍有多个关键能力散落在 collector：

1. alert hit rate 在 collector。
2. pricing explanation 在 collector。
3. pricing templates / thresholds 等决策辅助还在 collector。

如果不收口，analyzer 还是假边界。

## 主要问题证据

- `buy_decision_hub` 仍直接 import collector 领域服务：[buy_decision_hub.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/buy_decision_hub.py)
- collector 仍保留 buy-side service 兼容层：`apps/collector/src/goofish_insight/application/services/buy_*`

## 范围

1. 迁移 buy-side 的 explanation / alert / threshold 相关决策逻辑。
2. 让 collector buy router 只依赖 analyzer export。
3. 清理 collector 中 buy-side 兼容 shim 的最终落点。

## 不做

1. 不改 buy 表结构。
2. 不重设计买方产品流程。

## 建议写文件范围

- [buy_decision_hub.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/buy_decision_hub.py)
- `apps/analyzer/src/goofish_analyzer/services/**`
- [buy.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/routers/buy.py)
- `apps/collector/src/goofish_insight/application/services/buy_*.py`

## 验证

```bash
PYTHONPATH=apps/collector/src:apps/analyzer/src ./.venv/bin/python -m unittest apps.analyzer.tests.test_buy_decision_hub apps.collector.tests.test_buy_entrypoints apps.collector.tests.test_buy_feedback_service
```

## 完成定义

1. buy-side 决策主逻辑集中在 analyzer。
2. collector 对 buy-side 的角色退化为 API / runtime / persistence glue。

## 2026-04-22 增量成果

1. 新增 analyzer service：`buy_template_monitoring.py`，把 `/api/buy/template-monitoring` 的核心统计逻辑迁入 analyzer。
2. collector `pricing_monitoring.py` 改为 shim，仅做 analyzer 转发，不再承载 buy-side 决策统计实现。
3. buy 路由改为直接调用 analyzer 的 `summarize_template_availability_monitoring_with_session`。
4. 新增 analyzer 单测 `test_buy_template_monitoring.py`，并与 buy/pricing 路由回归一并通过。
