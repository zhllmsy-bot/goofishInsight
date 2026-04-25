# T19 Analyzer 可观测性与异常治理

Status: Done
Priority: P1
Source: Analyzer jobs 仍存在宽泛异常捕获且缺少统一日志入口
Done At: 2026-04-16

## 目标

先把 `apps/analyzer` 这条相对独立的执行链路治理好，建立一套可复用的 Python job logging/exception pattern，为后续 Collector 串行治理打样。

## 独占文件

- [daily_metrics.py](<repo-root>/apps/analyzer/src/goofish_analyzer/jobs/daily_metrics.py)
- [model_scores.py](<repo-root>/apps/analyzer/src/goofish_analyzer/jobs/model_scores.py)
- [analysis_reports.py](<repo-root>/apps/analyzer/src/goofish_analyzer/jobs/analysis_reports.py)
- [metrics_builder.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/metrics_builder.py)
- [score_builder.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/score_builder.py)
- [report_builder.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/report_builder.py)
- [test_daily_metrics_job.py](<repo-root>/apps/analyzer/tests/test_daily_metrics_job.py)
- [test_model_scores_job.py](<repo-root>/apps/analyzer/tests/test_model_scores_job.py)
- [test_analysis_reports_job.py](<repo-root>/apps/analyzer/tests/test_analysis_reports_job.py)
- `apps/analyzer/src/goofish_analyzer/logging.py`（new）

## 范围

- 增加 analyzer 统一 logger 初始化。
- 将 `except Exception` 收窄到预期错误，并把异常上下文写入日志。
- 保持 job 输出合同不变。
- 补足测试以覆盖“异常被记录且不会静默吞掉”的路径。

## 不做

- 不改 `apps/collector/**`
- 不接外部日志平台
- 不做全仓库 logging 框架改造

## 交付物

- Analyzer jobs 具备结构化日志入口
- 关键异常不会静默吞掉
- 为 Collector 侧日志治理提供可复制模板

## 验证

```bash
cd <repo-root> && PYTHONPATH=apps/analyzer/src ./.venv/bin/python -m unittest \
  apps.analyzer.tests.test_daily_metrics_job \
  apps.analyzer.tests.test_model_scores_job \
  apps.analyzer.tests.test_analysis_reports_job
```

## 完成定义

- Analyzer 侧不再依赖裸 `except Exception as exc` 静默跳过
- 失败路径有稳定日志字段
- 现有 job 测试全部通过

## 实际验收

- 已执行 `PYTHONPATH=apps/analyzer/src ./.venv/bin/python -m unittest apps.analyzer.tests.test_daily_metrics_job apps.analyzer.tests.test_model_scores_job apps.analyzer.tests.test_analysis_reports_job`
