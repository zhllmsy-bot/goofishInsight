# C06 Analyzer 边界去 collector 依赖

Status: In Progress (phase-1 landed, 2026-04-21)
Priority: P1

## 目标

把 analyzer 从“物理上独立、逻辑上继续依赖 collector 大量 service”的状态，收口成真正清晰的分析边界。

## 为什么现在做

现在 analyzer 已接管买方工作台的一部分逻辑，但仍大量直接 import collector 的 service、model、helper。边界没有真正形成，后续只会继续缠绕。

## 主要问题证据

- analyzer 直接依赖 collector service 与 model：[buy_decision_hub.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/buy_decision_hub.py)
- analyzer 多处直接 import `goofish_insight.*`：`apps/analyzer/src/goofish_analyzer/**`
- analyzer CLI 仍先把 collector src 注入 path：[cli.py](<repo-root>/apps/analyzer/src/goofish_analyzer/cli.py)

## 范围

1. 列出 analyzer 对 collector 的直接依赖清单。
2. 定义哪些依赖必须沉到共享 contract，哪些暂时可接受。
3. 优先移除 buy-side 领域里的 collector service 依赖。
4. 为 analyzer 建立更明确的 domain/service/export 边界。

## 不做

1. 不在这轮拆独立数据库层。
2. 不推动微服务拆分。

## 建议写文件范围

- `apps/analyzer/src/goofish_analyzer/services/**`
- [cli.py](<repo-root>/apps/analyzer/src/goofish_analyzer/cli.py)
- `apps/analyzer/tests/**`
- 可能新增 `packages/schema` 或 `packages/utils` 下的共享 contract 文件

## 验证

```bash
PYTHONPATH=apps/collector/src:apps/analyzer/src ./.venv/bin/python -m unittest apps.analyzer.tests.test_buy_decision_hub
```

## 完成定义

1. analyzer 对 collector 的依赖列表被显式压缩。
2. buy-side 分析域不再继续从 collector service 拼装逻辑。
3. analyzer 的职责能在代码层看出来，不只是 README 上看起来像。

## 2026-04-21 阶段成果

1. 买方工作台入口已经切到 analyzer hub：
   - `apps/collector/src/goofish_insight/entrypoints/web/routers/buy.py`
   - `apps/analyzer/src/goofish_analyzer/services/buy_decision_hub.py`
2. collector 侧 buy service 退化为薄适配层，不再扩展新决策逻辑：
   - `apps/collector/src/goofish_insight/application/services/buy_feedback.py`
   - `apps/collector/src/goofish_insight/application/services/buy_opportunities.py`
   - `apps/collector/src/goofish_insight/application/services/buy_alerts.py`
3. 已补 analyzer 边界验证：
   - `apps/analyzer/tests/test_buy_decision_hub.py`

## 2026-04-22 增量成果

1. 新增 adapter 边界契约测试，锁定 analyzer 对 `goofish_insight.*` 的允许依赖集合：
   - `apps/analyzer/tests/test_adapter_boundary_contract.py`
2. 将该边界契约并入统一质量门禁（`scripts/verify-baseline.sh`）。
