# T1 Runtime 状态机与 runtime 可视化

Status: Done
Priority: P0
Source Todo: W1 + W8 + Buffer Week 回归项
Done At: 2026-04-15

## 目标

把 `collect-batch` 真实运行过程写成 `PROBE -> BATCH -> COOLDOWN -> RESUME` 可观测状态机，runtime 页面单看 job 状态就能回答“是否在跑、为什么停、多久恢复”。

## 独占文件

- [collector_runtime.py](<repo-root>/apps/collector/src/goofish_insight/application/services/collector_runtime.py)
- [runtime_controls.py](<repo-root>/apps/collector/src/goofish_insight/application/services/runtime_controls.py)
- [collect.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli/collect.py)
- [start-batch-collect-resident.sh](<repo-root>/scripts/start-batch-collect-resident.sh)
- [runtime.html](<repo-root>/apps/web/templates/runtime.html)
- [test_runtime_controls.py](<repo-root>/apps/collector/tests/test_runtime_controls.py)
- [test_collect_runtime_queries.py](<repo-root>/apps/collector/tests/test_collect_runtime_queries.py)

## 范围

- 在 `collector_runtime.py` 增加 phase/status 原子更新 helper。
- 把 cooldown 原因、开始时间、预计恢复时间、最近一次 risk event 摘要写入 `collector_job_run.metadata_json`。
- 在 resident shell 的 risk cooldown 分支和恢复前后显式写入 `COOLDOWN` / `RESUME`。
- 在 runtime controls 与 runtime 页展示恢复倒计时、下一次重试时间、最近失败原因。

## 不做

- 不修改 `apps/collector/src/goofish_insight/cli.py`
- 不修改 analyzer job
- 不修改 dashboard React API 合同

## 交付物

- `PROBE -> BATCH -> COOLDOWN -> RESUME` 状态机打通
- 浏览器关闭、风控冷却、恢复时间、最近 risk event 全部可见
- runtime 页面可直接回答“当前是否在跑、跑到哪、为什么停、多久恢复”

## 验证

```bash
./.venv/bin/python scripts/ops/check_phase1_runtime_health.py
./.venv/bin/python scripts/ops/freeze_quality_baseline.py --days 7
PYTHONPATH=apps/collector/src ./.venv/bin/python -m unittest \
  apps.collector.tests.test_runtime_controls \
  apps.collector.tests.test_collect_runtime_queries
```

## 完成定义

- W1 `打通 PROBE -> BATCH -> COOLDOWN -> RESUME 状态机`
- W1 `浏览器关闭后冷却再重启的行为写入作业状态`
- W1 `任意时刻都能回答“当前是否在跑、跑到哪、为什么停、多久恢复”`
- W8 `运行状态和质量状态都能一眼判断，不再靠猜`

## 实际验收（2026-04-15）

- `check_phase1_runtime_health.py` 通过：`ok=true`，`quality_metrics` 组为 `running`，关键检查均通过（采集成功率/风控命中率/指标时效/launchd 探针）。
- `freeze_quality_baseline.py --days 7` 通过：`ok=true`，7 天 baseline 可持续冻结。
- 运行态字段链路可见：`collect-batch` 支持 `phase/status` 与 `cooldown_reason/recovery_eta/next_retry_at/recent_risk_event/recent_failure_reason`；resident 脚本在冷却分支显式写入 COOLDOWN/RESUME 状态。
- 相关测试通过：`test_runtime_controls`、`test_collect_runtime_queries`（并包含在 selected integration 中）。
