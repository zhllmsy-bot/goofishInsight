# T12 Dashboard API 配置收口与请求超时

Status: Proposed
Priority: P1
Source: 非安全类质量盘点中的 localhost / 无限挂起 / 配置分散问题

## 目标

把 Dashboard React 与 Nest BFF 的 API origin、回退策略、请求超时统一到单一配置层，避免同一逻辑分散在多个 API 文件里。

## 独占文件

- [dashboardApi.ts](<repo-root>/apps/dashboard-react/src/features/dashboard/api/dashboardApi.ts)
- [runtimeApi.ts](<repo-root>/apps/dashboard-react/src/features/runtime/api/runtimeApi.ts)
- [llmOpsApi.ts](<repo-root>/apps/dashboard-react/src/features/llm-ops/api/llmOpsApi.ts)
- [constants.ts](<repo-root>/apps/dashboard-react/src/features/dashboard/lib/constants.ts)
- [formatters.ts](<repo-root>/apps/dashboard-react/src/features/dashboard/lib/formatters.ts)
- [vite-env.d.ts](<repo-root>/apps/dashboard-react/src/vite-env.d.ts)
- [vite.config.ts](<repo-root>/apps/dashboard-react/vite.config.ts)
- [dashboard-proxy.service.ts](<repo-root>/apps/dashboard-nest/src/dashboard-proxy.service.ts)
- `apps/dashboard-react/src/shared/lib/dashboardApiConfig.ts`（new）
- `apps/dashboard-react/src/shared/lib/fetchJson.ts`（new）

## 范围

- 抽出统一的 Dashboard API 配置模块，处理 `fastapi|bff` 模式切换。
- 统一 legacy link 与 API origin 解析，消除重复实现。
- 为 fetch 请求增加默认超时、错误包装和 AbortSignal 透传。
- 对开发态缺失配置给出更明确的启动期报错或降级说明。
- 保持现有 API schema 和 URL 路径不变。

## 不做

- 不改 `DashboardPage.tsx`、`ListingsPanel.tsx`
- 不改 FastAPI 路由合同
- 不接入 Sentry 或外部监控 SDK

## 交付物

- React 侧只有一个 origin 解析入口
- API 请求具备统一超时策略
- BFF 与直连模式切换规则文档化并体现在代码常量中

## 验证

```bash
cd <repo-root>/apps/dashboard-react && npm run build
cd <repo-root>/apps/dashboard-nest && npm run build
```

## 完成定义

- 删除三处重复的 `resolveDashboardApiOrigin()`
- `legacyLink()` 不再使用独立的 origin 常量分支
- 请求默认不会无限等待
- 切换到 `VITE_DASHBOARD_API_MODE=bff` 时仍可正常回滚
