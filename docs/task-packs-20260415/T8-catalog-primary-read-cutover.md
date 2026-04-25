# T8 Catalog 主读切换

Status: Done
Priority: P0
Source Todo: W7 A->B/B->C 切流
Done At: 2026-04-15

## 目标

在 contract test 和 coverage/parity 达标后，把 dashboard 主读路径切到 catalog，并保留回滚开关。

## 独占文件

- [dashboard_queries.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_queries.py)
- [dashboard_sections.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_sections.py)
- [dashboard_page.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_page.py)
- [test_dashboard_sections.py](<repo-root>/apps/collector/tests/test_dashboard_sections.py)

## 前置条件

- `T6 contract test` 通过
- `T7 coverage/parity` 达标

## 范围

- 先切“默认新读 + 旧读兜底”
- 再切“新读主路径”
- 保留旧读一版周期

## 交付物

- `category + catalog` 成为主要业务读路径
- dashboard 主读路径切到 catalog，且可回滚

## 实际验收（2026-04-15）

- `dashboard_queries.py` 的默认读取模式已切到 `catalog_primary`，`dashboard_pricing_read_cache_signature()` 默认返回 `("catalog_primary", True)`。
- `dashboard_sections` / `dashboard_page` 继续保留 fallback 元数据和回滚开关，`test_dashboard_sections` 已通过。
- catalog 主读已经成为默认路径，仍可通过环境变量显式回退到旧读。

## 验证

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m unittest \
  apps.collector.tests.test_dashboard_sections
```
