# T13 React Error Boundary 与路由恢复

Status: Done
Priority: P1
Source: 前端缺少 Error Boundary，任何运行时异常都可能白屏

## 目标

为 React 应用增加应用级与路由级兜底，让 Dashboard、LLM Ops、Runtime 页面在子树异常时能展示可恢复状态，而不是整页白屏。

## 独占文件

- [main.tsx](<repo-root>/apps/dashboard-react/src/main.tsx)
- [App.tsx](<repo-root>/apps/dashboard-react/src/app/App.tsx)
- [AppProviders.tsx](<repo-root>/apps/dashboard-react/src/app/providers/AppProviders.tsx)
- `apps/dashboard-react/src/shared/components/AppErrorBoundary.tsx`（new）
- `apps/dashboard-react/src/shared/components/RouteErrorState.tsx`（new）
- `apps/dashboard-react/src/shared/styles/error-boundary.css`（new）

## 范围

- 增加应用级 Error Boundary。
- 为主要路由提供统一 fallback 视图和“返回首页/重试”动作。
- 处理 React Query/异步渲染导致的常见错误展示。
- 为后续接入错误追踪预留 `onError` 钩子，但本任务不接第三方服务。

## 不做

- 不改页面业务逻辑
- 不改 Dashboard API 请求层
- 不在本任务里补 RTL 测试基座

## 交付物

- 任一路由渲染异常时都有可见 fallback
- Boundary 组件可复用于后续页面
- 后续接入 Sentry 只需要在 boundary hook 中补实现

## 验证

```bash
cd <repo-root>/apps/dashboard-react && npm run build
```

## 完成定义

- `main.tsx` 不再直接裸挂载 `<AppProviders><App /></AppProviders>`
- 核心路由具备统一错误页
- fallback 文案包含刷新、返回首页、查看运行状态等恢复动作
