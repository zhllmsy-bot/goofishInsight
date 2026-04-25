# S1 CLI shell / purity 验收

Status: Done
Priority: P0
Source Todo: W11 + 最终串行热点收口
Done At: 2026-04-15

## 目标

在前面任务包落定后，统一收口热点入口文件，完成 entrypoint purity 验收与工程债务常态化治理。

## 独占文件

- [cli.py](<repo-root>/apps/collector/src/goofish_insight/cli.py)
- [specs.py](<repo-root>/apps/collector/src/goofish_insight/specs.py)
- [pricing.py](<repo-root>/apps/collector/src/goofish_insight/pricing.py)
- [review.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli/review.py)
- [30-entrypoint-and-legacy-spec-audit-20260414.md](<repo-root>/docs/30-entrypoint-and-legacy-spec-audit-20260414.md)
- [run_selected_integration.sh](<repo-root>/scripts/ci/run_selected_integration.sh)

## 启动条件

- `T1/T3/T4/T5` 至少完成并合并一次
- `apps/collector/src/goofish_insight/entrypoints/cli/collect.py` 仅作为只读验收参考；本包不再编辑它，避免与 `T1` 冲突

## 范围

- 验证 entrypoint 只做参数解析和 service 调用
- 统一收口 `cli.py/specs.py/pricing.py`
- 把工程债务治理沉淀到 CI / 文档 / 验收项

## 交付物

- entrypoint purity 验收报告
- `cli.py` 阶段性瘦身完成并有后续治理路线
- 工程债务进入常态化治理节奏

## 验证

```bash
./scripts/ci/run_selected_integration.sh
```

## 实际验收（2026-04-15）

### 验收结论

- 通过。

### 已完成验证

- 已执行 `./scripts/ci/run_selected_integration.sh`：
  - `165` 项测试通过（`OK`）。
  - rule replay 通过，`accuracy = 1.0`（阈值 `minAccuracy = 0.85`）。

- 已执行 `./scripts/ci/run_selected_integration.sh`，`165` 项测试通过，rule replay `accuracy = 1.0`。
- 已执行 analyzer / collector 相关选中单测，`134` 项测试通过。
- `collect.py` 已收敛为轻量注册入口，batch 编排已下沉到 `collector_batch_runtime.py`。
- `cli.py`、`specs.py`、`pricing.py`、`review.py` 的热点路径已完成阶段性拆分，后续治理路线已写回主 Todo。
