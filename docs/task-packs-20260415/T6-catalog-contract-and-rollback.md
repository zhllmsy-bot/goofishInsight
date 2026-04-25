# T6 Catalog contract test 与回滚工件

Status: Done
Priority: P0
Source Todo: W7 contract/rollback 前置工件
Done At: 2026-04-15

## 目标

补齐 catalog 切主前最关键的防线：contract test、diff 报告格式、rollback 脚本或 SQL。

## 独占文件

- [catalog_migration_checks.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_migration_checks.py)
- [catalog_queries.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_queries.py)
- [test_catalog_migration_checks.py](<repo-root>/apps/collector/tests/test_catalog_migration_checks.py)
- `scripts/db/*catalog*rollback*`

## 范围

- 建立旧 pricing/dashboard 读路径与 catalog 双读路径 contract test
- 固定 diff 报告格式
- 提供直接可执行的 rollback 脚本或 SQL

## 交付物

- W7 contract test
- W7 rollback script / rollback SQL
- B->C 切换评估的前置工件

## 实际验收（2026-04-15）

- `catalog_migration_checks.py` 已产出双读 contract report、diff 报告和 rollback artifact。
- `scripts/db/catalog_dual_read_rollback.sh` 已可直接生成回滚备份和回滚 SQL 草案。
- 最终 `check-catalog-pricing-dual-read` 与 `check-catalog-scoped-migration` 均返回 `overallOk=true`，`test_catalog_migration_checks` 通过。

## 验证

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m unittest \
  apps.collector.tests.test_catalog_migration_checks
```
