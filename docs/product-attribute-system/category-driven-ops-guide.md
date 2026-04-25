# Category-Driven Collection Ops Guide

更新时间：2026-04-07 01:20:00 CST

## 主链路

`大类 -> runtime profile -> active template -> model catalog -> crawl task -> crawl_task_query -> items/specs/dashboard/pricing`

`monitor_tasks.json` 现在只负责：
- 保存 browser `profiles`
- 作为任务导入导出载体

## 配置页

- 大类：`/config/categories`
- 属性：`/config/attributes`
- 模板：`/config/templates`
- 型号库：`/config/models`
- 任务：`/config/tasks`
- raw cate policy：`/config/raw-cate-policy`

## 常用命令

### 任务

- 导出数据库任务
```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli export-task-config --output apps/collector/configs/monitor_tasks.json
```

- 从 `monitor_tasks.json` 导回数据库
```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli import-task-config --config-path apps/collector/configs/monitor_tasks.json
```

- 回填老任务大类绑定
```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli backfill-task-categories --force
```

### 分类解析

- 回填旧 item 的 category/template
```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli backfill-item-category-resolution --dry-run --limit 100
```

### 采集

- batch collect
```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli collect-batch --only-task <task_key> --profile-key default
```

- discovery
```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli run-discovery --task-key <task_key> --profile-key default
```

### Pricing / Dashboard

- 按大类出价带
```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli show-price-bands --category-code apple_computer --view spec
```

- dashboard 大类入口
```text
http://127.0.0.1:8787/?category_code=apple_computer
```

## Resident Runtime

- dashboard 单独热重启
```bash
launchctl kickstart -k gui/$(id -u)/com.admin.goofish-dashboard-8787
```

注意：
- 不要随意动 `9222 / 9223`
- 风控时不要自动关闭闲鱼验证页
- attached browser 模式下会保留 manual verification tab
- persistent context 模式下会持续等待人工处理
