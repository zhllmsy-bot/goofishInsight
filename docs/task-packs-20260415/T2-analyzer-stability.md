# T2 Analyzer 稳定性与 Phase 3 数据源合同

Status: Done
Priority: P1
Source Todo: W2 + Phase 2 analyzer 稳定项
Done At: 2026-04-15

## 目标

让 analyzer 三个 job 里至少两个稳定运行，并明确 Phase 3 随 W7 切 catalog 后的数据读取合同。

## 独占文件

- [cli.py](<repo-root>/apps/analyzer/src/goofish_analyzer/cli.py)
- [daily_metrics.py](<repo-root>/apps/analyzer/src/goofish_analyzer/jobs/daily_metrics.py)
- [model_scores.py](<repo-root>/apps/analyzer/src/goofish_analyzer/jobs/model_scores.py)
- [analysis_reports.py](<repo-root>/apps/analyzer/src/goofish_analyzer/jobs/analysis_reports.py)
- [metrics_builder.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/metrics_builder.py)
- [score_builder.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/score_builder.py)
- [report_builder.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/report_builder.py)
- [start-analyzer-resident.sh](<repo-root>/scripts/start-analyzer-resident.sh)
- [com.admin.goofish-analyzer-hourly.plist](<repo-root>/infra/launchd/com.admin.goofish-analyzer-hourly.plist)
- [test_daily_metrics_job.py](<repo-root>/apps/analyzer/tests/test_daily_metrics_job.py)
- [test_model_scores_job.py](<repo-root>/apps/analyzer/tests/test_model_scores_job.py)
- [test_analysis_reports_job.py](<repo-root>/apps/analyzer/tests/test_analysis_reports_job.py)

## 范围

- 排查并清理 analyzer 范围内 flaky。
- 固定至少两个 job 的稳定出数路径。
- 写清楚 Phase 3 切 catalog 后 analyzer 读旧路径/读新路径的切换条件。

## 交付物

- 至少两个 analyzer job 连续稳定出数
- Phase 3 catalog 数据源合同文档化
- analyzer 范围内失败用例被修复或显式降级

## 实际验收（2026-04-15）

- 已执行 `PYTHONPATH=apps/analyzer/src:apps/collector/src <repo-root>/.venv/bin/python -m unittest apps.analyzer.tests.test_daily_metrics_job apps.analyzer.tests.test_model_scores_job apps.analyzer.tests.test_analysis_reports_job apps.collector.tests.test_alert_dispatcher_service apps.collector.tests.test_notification_delivery_service apps.collector.tests.test_catalog_admin_commands apps.collector.tests.test_catalog_migration_checks apps.collector.tests.test_catalog_backfill_service apps.collector.tests.test_catalog_models apps.collector.tests.test_dashboard_sections apps.collector.tests.test_buy_alerts_service apps.collector.tests.test_buy_entrypoints apps.collector.tests.test_buy_feedback_service apps.collector.tests.test_buy_opportunities_service apps.collector.tests.test_outreach_outcomes_service`，合并单测 `134` 个通过。
- `apps/analyzer/src/goofish_analyzer/cli.py` 已明确 `legacy_items`、`catalog_dual_read`、`catalog_primary` 读模式和 Phase 3 切换门槛。
- `model_scores_job`、`analysis_reports_job` 的读路径已支持 catalog 主读，Phase 3 合同已写入 CLI 文档和测试断言。

## 验证

```bash
PYTHONPATH=apps/analyzer/src ./.venv/bin/python -m unittest \
  apps.analyzer.tests.test_daily_metrics_job \
  apps.analyzer.tests.test_model_scores_job \
  apps.analyzer.tests.test_analysis_reports_job
```
