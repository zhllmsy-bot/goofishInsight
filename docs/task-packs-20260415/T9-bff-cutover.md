# T9 BFF 拓扑文档与 React 直连 FastAPI

Status: Done
Priority: P1
Source Todo: W9 未完成项

## 目标

明确真实部署拓扑，完成 React 直连 FastAPI，并保留回滚到 BFF 的开关。

## 独占文件

- [06-deployment.md](<repo-root>/docs/06-deployment.md)
- [main.ts](<repo-root>/apps/dashboard-nest/src/main.ts)
- [app.module.ts](<repo-root>/apps/dashboard-nest/src/app.module.ts)
- [dashboard-proxy.controller.ts](<repo-root>/apps/dashboard-nest/src/dashboard-proxy.controller.ts)
- [dashboard-proxy.service.ts](<repo-root>/apps/dashboard-nest/src/dashboard-proxy.service.ts)
- [progress-proxy.controller.ts](<repo-root>/apps/dashboard-nest/src/progress-proxy.controller.ts)
- [webapp.py](<repo-root>/apps/collector/src/goofish_insight/webapp.py)
- [app.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/app.py)
- [dashboardApi.ts](<repo-root>/apps/dashboard-react/src/features/dashboard/api/dashboardApi.ts)
- [runtimeApi.ts](<repo-root>/apps/dashboard-react/src/features/runtime/api/runtimeApi.ts)
- [llmOpsApi.ts](<repo-root>/apps/dashboard-react/src/features/llm-ops/api/llmOpsApi.ts)

## 范围

- 文档化三层拓扑：本地运行、本地开发、生产目标
- React 直连 FastAPI
- 保留回滚到 BFF 的显式开关
- 最终明确 BFF 是保留还是下线

## 交付物

- W9 完成定义闭合
- BFF 可以安全保留或安全下线，结论明确

## 实施结果（2026-04-15）

- React API 默认切到 FastAPI 直连，且提供 `VITE_DASHBOARD_API_MODE=fastapi|bff` 显式开关：
  - `fastapi`（默认）使用 `VITE_FASTAPI_ORIGIN`（默认 `http://127.0.0.1:8791`）
  - `bff` 使用 `VITE_BFF_ORIGIN`（缺省回退 `window.location.origin`）
- Nest BFF 透传补齐 `POST /api/dashboard/listing-preferences`，保证回滚到 BFF 时 API 路径完整。
- [06-deployment.md](<repo-root>/docs/06-deployment.md) 已补齐三层拓扑口径（本地运行 / 本地开发 / 生产目标）并写明 BFF 结论：
  - BFF 不再作为主路径，短期保留为应急回滚层。

## 验证

```bash
cd apps/dashboard-react && npm run build
PYTHONPATH=apps/collector/src ./.venv/bin/python -m unittest \
  apps.collector.tests.test_webapp_cors
```
