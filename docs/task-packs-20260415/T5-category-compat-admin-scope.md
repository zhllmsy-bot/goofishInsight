# T5 `category_compat` 与 admin scope 收口

Status: Done
Priority: P1
Source Todo: W6 admin/scope 收口
Done At: 2026-04-15

## 目标

让 admin/backfill 入口优先接受 canonical `category_code`，把 legacy `business_domain` 收缩为兼容层而不是新接口主语义。

## 独占文件

- [category_compat.py](<repo-root>/apps/collector/src/goofish_insight/category_compat.py)
- [admin.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli/admin.py)
- [test_catalog_admin_commands.py](<repo-root>/apps/collector/tests/test_catalog_admin_commands.py)
- [31-business-domain-category-migration-plan-20260414.md](<repo-root>/docs/31-business-domain-category-migration-plan-20260414.md)

## 范围

- admin/backfill 命令优先接受 `category_code`
- legacy alias 只作为兼容输入
- 给 `category_compat` 增加退役计划和停止条件
- 新代码不再新增以 `business_domain` 为主参数的接口

## 交付物

- `category_id/category_code` 成为 admin 入口主语义
- `category_compat` 退役路线明确

## 实际验收（2026-04-15）

- admin / backfill 入口已优先接收 `category_code`，`business_domain` 仅作为兼容别名保留。
- `category_compat.py` 的退役计划和停止条件已写入 `docs/31-business-domain-category-migration-plan-20260414.md`。
- `apps.collector.tests.test_catalog_admin_commands` 已通过，兼容输入与 canonical 输入的行为保持一致。

## 验证

```bash
PYTHONPATH=apps/collector/src ./.venv/bin/python -m unittest \
  apps.collector.tests.test_catalog_admin_commands
```
