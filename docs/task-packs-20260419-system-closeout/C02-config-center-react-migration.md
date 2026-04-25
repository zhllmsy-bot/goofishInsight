# C02 Config Center React 化与旧模板退场

Status: Proposed
Priority: P0

## 目标

把配置中心从 Jinja 模板页迁入 React 主工作台，让“配置、工作区、运行控制”不再跨两套前端来回跳。

## 为什么现在做

当前顶部导航已经把主运营页大多收回 React，但“配置中心”仍然直接跳旧模板页，导致产品面仍然分裂。

## 主要问题证据

- 顶部导航仍链接旧配置页：[DashboardHeader.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardHeader.tsx)
- Config 页面仍完全依赖模板渲染：[config.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/routers/config.py)
- 旧模板文件仍是主要载体：`apps/web/templates/config_*.html`

## 范围

1. 新建 React `config` 工作区壳层。
2. 先迁最常用的 `categories`、`templates`、`tasks` 三块。
3. 保持已有 `/api/config/*` JSON 合同不变。
4. 顶部导航切到 React config 工作区。
5. 旧模板页降级为 fallback/admin 入口。

## 不做

1. 不重构 config 后端 service。
2. 不一次性重做全部 config UX。
3. 不在这轮改数据库 schema。

## 建议写文件范围

- [DashboardHeader.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardHeader.tsx)
- [config.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/routers/config.py)
- `apps/dashboard-react/src/features/config/**`（new）
- `apps/dashboard-react/src/app/App.tsx` 中新增 config routes

## 验证

```bash
npm run test -w @goofish/dashboard-react
npm run typecheck -w @goofish/dashboard-react
PYTHONPATH=apps/collector/src:apps/analyzer/src ./.venv/bin/python -m unittest apps.collector.tests.test_config_entrypoints
```

## 完成定义

1. 用户从主工作台进入配置中心时，不再跳到旧模板页。
2. 至少三块核心配置可在 React 内完成查看和提交。
3. workspace query 保持策略在 config 内继续成立。
