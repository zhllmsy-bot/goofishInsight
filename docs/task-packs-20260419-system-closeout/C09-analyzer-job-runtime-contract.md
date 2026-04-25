# C09 Analyzer 作业入口与运行契约统一

Status: Done
Priority: P1
Done At: 2026-04-19

## 目标

把 analyzer 的 CLI、job 锁、source mode、运行状态、观测口径整理成统一运行契约，而不是"能跑，但认知分散"。

## 为什么现在做

当前 analyzer 作业入口已经不少，但运行方式、锁路径、source_mode、与 collector 的关系需要读代码才能拼出来。

## 主要问题证据

- analyzer CLI 过载且强依赖 collector path 注入：[cli.py](<repo-root>/apps/analyzer/src/goofish_analyzer/cli.py)

## 范围

1. 统一 analyzer job 的命名、锁路径、输出路径、source mode 说明。
2. 补最少但明确的 runtime status / health contract。
3. 为 resident 或调度调用方补清晰入口。

## 不做

1. 不改 daily_metrics / model_scores / analysis_reports 业务逻辑。

## 实际交付

1. 新增 `goofish_analyzer.contract` 模块，统一收口所有运行时常量：
   - `ANALYZER_JOBS`、`DEFAULT_LOCK_PATHS`、`SOURCE_MODES`、`PHASE3_CATALOG_SWITCH_GATES`
   - `JOB_NAMES`、`LOCK_JOB_NAMES`、`EXIT_CODE_ALREADY_RUNNING`
   - `JOB_STATUS_*`、`HEALTH_STATUS_*`
   - `build_source_contract()`、`resolve_lock_path()`

2. 重构 `cli.py`：
   - 所有常量从 `contract.py` 导入，消除旧私有常量
   - 新增独立命令：`run-daily-metrics`、`run-model-scores`、`run-analysis-reports`、`run-all`
   - 保留通用 `run-job --job <name>` 入口
   - 新增 `health` 命令输出作业健康状态 JSON
   - 新增 `status` 命令输出完整运行时摘要 JSON
   - 输出改为 JSON 序列化，确保结构化可解析
   - 清理 `__main__` 兼容代码

3. 统一 `daily_metrics.py`：
   - 移除重复的 `fcntl` 锁实现，改用共享 `_locking.py`
   - 移除本地 `_build_source_contract`，改用 `contract.build_source_contract`
   - 移除多余的顶层 `QualityMetricsService` 导入

4. 统一 `model_scores.py` 和 `analysis_reports.py`：
   - 移除本地 `_build_source_contract`，改用 `contract.build_source_contract`
   - 锁路径默认值从 `contract.DEFAULT_LOCK_PATHS` 获取

5. 更新 `README.md` 和 `MODULE.md` 记录统一运行契约

## 验证

```bash
PYTHONPATH=apps/collector/src:apps/analyzer/src ./.venv/bin/python -m goofish_analyzer.cli --help
```

```bash
PYTHONPATH=apps/analyzer/src:apps/collector/src ./.venv/bin/python -m unittest \
  apps.analyzer.tests.test_daily_metrics_job \
  apps.analyzer.tests.test_model_scores_job \
  apps.analyzer.tests.test_analysis_reports_job
```

## 完成定义

1. analyzer 作业运行契约可单独理解。✅ 通过 `contract.py` 和 `README.md` 统一收口
2. 调度 / resident / 文档引用同一套入口与口径。✅ CLI 命令、Python API、文档三方一致
