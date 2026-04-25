# C08 Pricing / alert / explanation 领域收口

Status: In Progress (phase-1 landed, 2026-04-22)
Priority: P1

## 目标

把 pricing record、template snapshot、guidance threshold、alert hit rate、explanation 这些“半分析半应用”的领域合同清晰化，防止继续散落在多个 service 里。

## 为什么现在做

当前买方和看板都依赖 pricing 结果，但 pricing 合同仍分散在 collector service 与 analyzer service 中，属于高耦合地带。

## 范围

1. 明确 pricing record 的 canonical contract。
2. 明确 baseline / explanation / template guidance 的 contract。
3. 对外提供稳定读模型，不让 UI 直接耦合内部拼装细节。

## 不做

1. 不改业务指标本身。
2. 不做新一轮价格算法升级。

## 建议写文件范围

- `apps/collector/src/goofish_insight/application/services/pricing_*.py`
- `apps/analyzer/src/goofish_analyzer/services/buy_opportunities.py`
- `packages/schema/**`
- 相关 tests

## 验证

```bash
PYTHONPATH=apps/collector/src:apps/analyzer/src ./.venv/bin/python -m unittest apps.collector.tests.test_pricing_entrypoints apps.collector.tests.test_buy_opportunities_service
```

## 完成定义

1. pricing / alert / explanation 的输入输出合同可单独描述。
2. React 与 analyzer 消费统一读模型，而不是拼 service 内部字段。

## 2026-04-22 增量成果

1. pricing template monitoring 合同正式收口到 analyzer，collector 侧退化为兼容薄层。
2. feature flags 返回口径在 analyzer 内统一（contract/dashboard/opportunity/trend/alert-strict 五项）。
3. 针对 monitoring 输出增加 analyzer 侧单测，确保 tier/status 统计与 feature flag 合同稳定。
