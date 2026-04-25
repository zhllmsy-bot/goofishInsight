# Category-Driven Smoke Checklist

更新时间：2026-04-07 01:20:00 CST

## 1. Schema

- `PYTHONPATH=apps/collector/src ./.venv/bin/alembic current`
- 预期输出：`20260407_0018 (head)`

## 2. Config Pages

- `http://127.0.0.1:8787/config/categories`
- `http://127.0.0.1:8787/config/attributes`
- `http://127.0.0.1:8787/config/templates`
- `http://127.0.0.1:8787/config/models`
- `http://127.0.0.1:8787/config/tasks`
- `http://127.0.0.1:8787/config/raw-cate-policy`

期望：
- 页面均返回 `200`
- 模板页支持 `categoryCode` 过滤
- 型号页支持 JSON 导入导出

## 3. Task Runtime

- 导出：`PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli export-task-config --output apps/collector/configs/monitor_tasks.json`
- 导入：`PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli import-task-config --config-path apps/collector/configs/monitor_tasks.json`
- 老任务回填：`PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli backfill-task-categories --force`

## 4. Category Resolution

- dry-run：`PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli backfill-item-category-resolution --dry-run --limit 20`

期望：
- 输出包含 `target_category_id / resolved_category_id / resolved_template_id`

## 5. Batch Collect

- `PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli collect-batch --only-task <task_key> --profile-key default`

期望：
- 任务列表优先来自数据库
- query 顺序按 `crawl_task_query.priority`
- `item/raw request/raw response/item snapshot` 都带 `task_query_id`

## 6. Discovery

- `PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli run-discovery --task-key <task_key> --profile-key default`

期望：
- 风控或登录校验时页面保持打开，等待人工处理

## 7. Pricing / Dashboard

- `PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli show-price-bands --category-code apple_computer --view spec`
- `PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli discover-models --category-code camera_interchangeable_lens`
- `http://127.0.0.1:8787/?category_code=apple_computer`

期望：
- pricing 行里包含 `category_code / category_name / category_id / template_id / model_catalog_id`
- dashboard 返回 `categoryCode / categoryName`

## 8. Resident Runtime

- 仅重启 dashboard：`launchctl kickstart -k gui/$(id -u)/com.admin.goofish-dashboard-8787`

注意：
- 不要主动重启 `9222 / 9223`
- 风控期间不要关闭用户正在验证的闲鱼页面
