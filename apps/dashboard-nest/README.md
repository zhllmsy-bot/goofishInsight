# Dashboard Nest

`apps/dashboard-nest` 不是通用 Nest 示例，而是 Goofish Insight 当前的前端托管层和 BFF 回退层。

## 当前职责

- 托管 `apps/dashboard-react` 的构建产物
- 对外提供 React 路由入口：
  - `/`
  - `/llm-ops`
  - `/llm-devops`
  - `/runtime`
  - `/buy/opportunities`
  - `/buy/opportunities/:opportunityId`
  - `/buy/targets`
  - `/buy/baselines`
  - `/config/categories`
  - `/config/templates`
  - `/config/tasks`
  - `/agent-harness`
- 代理 FastAPI 的 dashboard / buy / config / onboarding / progress / mobile-overlay / raw-response 接口，避免前端直连时的跨域与部署耦合

## 当前 API 代理

### Dashboard

- `/api/dashboard/sections/:section`
- `/api/dashboard/llm-traces/:traceKey`
- `/api/dashboard/runtime/status`
- `/api/dashboard/runtime/actions`
- `/api/dashboard/agent-harness/status`
- `/api/dashboard/listing-preferences`
- `/api/dashboard/items/:itemId`

### Buy

- `/api/buy/opportunities`
- `/api/buy/opportunities/:opportunityId`
- `/api/buy/targets`
- `/api/buy/baselines`
- `/api/buy/feedback`
- `/api/buy/feedback-quality`
- `/api/buy/feedback-calibration`
- `/api/buy/feedback-calibration/apply`
- `/api/buy/template-monitoring`

### Config

- `/api/config/categories`
- `/api/config/tasks`
- `/api/config/templates`
- `/api/config/templates/:templateId`
- `/api/config/templates/diff-preview`

### Onboarding

- `/api/onboarding/xianyu/coverage`
- `/api/onboarding/xianyu/queue`
- `/api/onboarding/xianyu/queue/sync`
- `/api/onboarding/xianyu/queue/status`
- `/api/onboarding/xianyu/discovery`
- `/api/onboarding/xianyu/draft`
- `/api/onboarding/xianyu/persist`

### Progress

- `/api/progress/sections/:section`

### Mobile Overlay

- `/api/mobile-overlay/healthz`
- `/api/mobile-overlay/analyze`

### Raw Responses

- `/api/raw-responses/:rawResponseId`

默认上游：

- `http://127.0.0.1:8791`

可通过环境变量覆盖：

- `GOOFISH_DASHBOARD_BACKEND_ORIGIN`
- `GOOFISH_DASHBOARD_BACKEND_TIMEOUT_MS`

## 本地开发

```bash
npm run start:dev -w @goofish/dashboard-nest
```

生产启动：

```bash
npm run build -w @goofish/dashboard-nest
npm run start:prod -w @goofish/dashboard-nest
```

## 验证命令

```bash
npm run typecheck -w @goofish/dashboard-nest
npm run test -w @goofish/dashboard-nest -- dashboard-proxy.controller.spec.ts buy-proxy.controller.spec.ts dashboard-proxy.service.spec.ts
npm run test:e2e -w @goofish/dashboard-nest -- --runInBand
```

说明：

- 当前 e2e 仍依赖 `supertest` 临时监听端口；在受限沙箱里可能遇到 `listen EPERM`
- 因此日常收口更推荐先跑 proxy 层单测，再把 e2e 作为完整环境验证

## 当前边界

- 它不负责业务规则、价格计算或采集逻辑
- 它不是本地运维主入口的事实来源，事实来源仍然是 `apps/collector`
- 如果部署环境允许前端直连 FastAPI，它可以退化为静态托管层；如果不能直连，它承担 BFF 代理职责
