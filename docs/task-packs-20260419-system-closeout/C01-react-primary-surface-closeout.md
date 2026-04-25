# C01 React 主前端彻底收口

Status: In Progress (main path completed, 2026-04-21)
Priority: P0

## 目标

把当前主运营路径涉及的页面全部收为 React 主前端，正式结束“双前端并存且边界不清”的状态。

## 为什么现在做

当前已经迁完 `/`、`/llm-devops`、`/runtime`、`/agent-harness`、`/buy/opportunities`、`/progress`、`/items/:itemId`、`/onboarding/xianyu`，但 React 壳层、FastAPI React shell、Nest 托管路由、旧模板遗留页仍未完全对齐。继续在这个状态上开发，会不断把产品工作流拆裂。

## 主要问题证据

- React 路由已经覆盖主工作区入口：[App.tsx](<repo-root>/apps/dashboard-react/src/app/App.tsx)
- FastAPI React shell 入口还没覆盖所有主路径：[react_shell.py](<repo-root>/apps/collector/src/goofish_insight/presentation/react_shell.py)
- Nest 托管路由落后于 FastAPI 实际入口：[app.controller.ts](<repo-root>/apps/dashboard-nest/src/app.controller.ts)
- 配置中心仍然是旧模板页：[config.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/routers/config.py)

## 范围

1. 统一定义“主运营前端”的页面范围。
2. 补齐 FastAPI React shell 支持的入口路径。
3. 补齐 Nest 托管层的 React 路由。
4. 清点旧模板页，标明哪些保留为 admin-only，哪些必须迁走。
5. 统一 README、SPEC、Web 文档里的前端口径。

## 不做

1. 不在这个任务里重写 Config 页面内容。
2. 不在这个任务里重写 onboarding 编辑器逻辑。
3. 不做视觉改版。

## 建议写文件范围

- [react_shell.py](<repo-root>/apps/collector/src/goofish_insight/presentation/react_shell.py)
- [app.controller.ts](<repo-root>/apps/dashboard-nest/src/app.controller.ts)
- [app.service.ts](<repo-root>/apps/dashboard-nest/src/app.service.ts)
- [README.md](<repo-root>/README.md)
- [apps/web/README.md](<repo-root>/apps/web/README.md)

## 验证

```bash
npm run build -w @goofish/dashboard-react
npm run build -w @goofish/dashboard-nest
PYTHONPATH=apps/collector/src:apps/analyzer/src ./.venv/bin/python -m unittest apps.collector.tests.test_review_entrypoints apps.collector.tests.test_onboarding_entrypoints
```

## 完成定义

1. 主运营路径的 React 入口列表有唯一真相来源。
2. FastAPI 与 Nest 对主前端路由的支持一致。
3. 剩余旧模板页被明确标记为 `admin/support only`，不再冒充主工作台。

## 2026-04-21 阶段成果

1. 主运营路径 `/`、`/runtime`、`/buy/opportunities`、`/items/:itemId` 已统一走 React shell。
2. 后端入口合同测试已覆盖主路径（见 `apps/collector/tests/test_review_entrypoints.py`）。
3. 剩余工作：配置中心等遗留模板页的产品定位标注与文档口径统一。

## 2026-04-22 增量成果

1. `/config/categories`、`/config/templates`、`/config/tasks` 已切换为 React shell 主入口。
2. 旧模板页目前仅保留 `/config/attributes`、`/config/models`、`/config/raw-cate-policy`，定位为 admin/support legacy 页面。
