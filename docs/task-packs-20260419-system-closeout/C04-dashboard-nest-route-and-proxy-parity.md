# C04 Dashboard Nest 路由与代理补齐

Status: In Progress (phase-1 landed, 2026-04-22)
Priority: P0

## 目标

让 `apps/dashboard-nest` 真正跟上当前 React 和 FastAPI 的主路径与 API 合同，避免 BFF 模式成为残缺回退层。

## 为什么现在做

当前 Nest 托管路由和代理明显落后于 FastAPI/React 实际能力。如果用户切到 `bff` 模式，会丢失 `progress`、`items`、`onboarding` 等页面和对应 API。

## 主要问题证据

- Nest React 路由未覆盖新页面：[app.controller.ts](<repo-root>/apps/dashboard-nest/src/app.controller.ts)
- Nest 代理未覆盖 buy/onboarding/item detail 等接口：[dashboard-proxy.controller.ts](<repo-root>/apps/dashboard-nest/src/dashboard-proxy.controller.ts)
- progress 代理单独分控制器，但范围有限：[progress-proxy.controller.ts](<repo-root>/apps/dashboard-nest/src/progress-proxy.controller.ts)

## 范围

1. 补齐 React 路由入口。
2. 补齐 item detail、buy、onboarding、progress 的 API 代理。
3. 统一 DashboardProxyService 的错误处理与超时复用。
4. 为 BFF 模式新增契约测试。

## 不做

1. 不新增业务逻辑。
2. 不改 FastAPI 接口定义。

## 建议写文件范围

- [app.controller.ts](<repo-root>/apps/dashboard-nest/src/app.controller.ts)
- [dashboard-proxy.controller.ts](<repo-root>/apps/dashboard-nest/src/dashboard-proxy.controller.ts)
- [progress-proxy.controller.ts](<repo-root>/apps/dashboard-nest/src/progress-proxy.controller.ts)
- [dashboard-proxy.service.ts](<repo-root>/apps/dashboard-nest/src/dashboard-proxy.service.ts)
- `apps/dashboard-nest/test/**`

## 验证

```bash
npm run test:e2e -w @goofish/dashboard-nest -- --runInBand
npm run typecheck -w @goofish/dashboard-nest
npm run build -w @goofish/dashboard-nest
```

## 完成定义

1. `bff` 模式下主工作流页面不缺口。
2. 代理能力覆盖当前 React 主工作台所需的核心 API。
3. FastAPI 与 Nest 在主工作流上不再各说各话。

## 2026-04-22 阶段成果

1. Nest React shell 入口已补 `/config/categories`、`/config/templates`、`/config/tasks`。
2. E2E 已覆盖并通过上述 3 条 config 路由入口。
