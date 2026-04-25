# S2 Collector 日志基础设施与异常治理

Status: Proposed
Priority: P0
Source: Collector 仍是最重的运行主路径，宽泛异常与缺少统一 logging 是剩余高风险工程债

## 目标

在不碰热点巨型文件的前提下，先为 Collector 建立统一 logging foundation，并优先治理最容易静默失败的 service cluster。

## 启动条件

- `T19` 已完成并验证
- 第一批并发任务已合并，避免 logging 口径再被前端或 CI 任务反复改动

## 独占文件

- [settings.py](<repo-root>/apps/collector/src/goofish_insight/settings.py)
- [db.py](<repo-root>/apps/collector/src/goofish_insight/db.py)
- [collector_browser.py](<repo-root>/apps/collector/src/goofish_insight/application/services/collector_browser.py)
- [crawl_task_runtime.py](<repo-root>/apps/collector/src/goofish_insight/application/services/crawl_task_runtime.py)
- [review_ingest.py](<repo-root>/apps/collector/src/goofish_insight/application/services/review_ingest.py)
- [catalog_migration_checks.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_migration_checks.py)
- `apps/collector/src/goofish_insight/logging.py`（new）
- 相关测试文件（按上述模块对应补充）

## 范围

- 建立 Collector 统一 logger 初始化与上下文字段约定。
- 优先替换基础设施与边缘服务中的宽泛异常。
- 保持 CLI/Web 外部合同不变。
- 为后续热点文件治理提供 logging 基础能力。

## 不做

- 不改 `cli.py`
- 不改 `specs.py`
- 不改 `pricing.py`

## 交付物

- Collector 侧基础日志能力
- 首批关键 service 不再静默吞异常
- 后续热点文件可直接复用 logging helper

## 验证

```bash
cd <repo-root> && PYTHONPATH=apps/collector/src ./.venv/bin/python -m unittest \
  apps.collector.tests.test_catalog_migration_checks \
  apps.collector.tests.test_runtime_controls \
  apps.collector.tests.test_web_services
```

## 完成定义

- Collector 侧出现统一 logger 模块
- 首批 service cluster 的异常路径可观测
- 后续 `cli.py/specs.py/pricing.py` 无需再自行定义 logging 基础设施
