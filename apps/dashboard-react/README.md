# Dashboard React

`apps/dashboard-react` 是当前面向运营和买方决策的主 React 工作台，不是 Vite 脚手架示例。

## 当前职责

- 提供机会优先的主入口：优先处理 `/buy/opportunities` 机会队列，再回到首页证据看板核验
- 提供 React 版看板首页 `/`
- 提供 LLM DevOps 页面 `/llm-devops`
- 提供运行控制页面 `/runtime`
- 提供多 Agent 观测页面 `/agent-harness`
- 提供买方工作台 `/buy/opportunities`
- 通过 URL 保存当前工作区上下文，例如 `category_code`、`product_label`、`spec_label`

## 依赖的后端模式

前端支持两种 API 接入方式：

- `fastapi`
  直接访问 `apps/collector` 暴露的 FastAPI，默认 `http://127.0.0.1:8791`
- `bff`
  通过 `apps/dashboard-nest` 代理 API 并托管静态资源，默认使用当前页面 origin

相关环境变量：

- `VITE_DASHBOARD_API_MODE=fastapi|bff`
- `VITE_FASTAPI_ORIGIN=http://127.0.0.1:8791`
- `VITE_BFF_ORIGIN=http://127.0.0.1:8787`
- `VITE_LEGACY_ORIGIN=http://127.0.0.1:8791`
- `VITE_DASHBOARD_API_TIMEOUT_MS=30000`

## 本地开发

```bash
npm run dev -w @goofish/dashboard-react
```

默认访问地址：

- [http://127.0.0.1:5173](http://127.0.0.1:5173)

## 验证命令

```bash
npm run typecheck -w @goofish/dashboard-react
npm run test -w @goofish/dashboard-react
npm run build -w @goofish/dashboard-react
```

## 当前结构

```text
src/
  app/                    BrowserRouter 与 Provider 入口
  features/dashboard/     看板首页、筛选、价格与列表工作区
  features/buy/           买方机会工作台与反馈回写
  features/runtime/       常驻任务运行控制
  features/llm-ops/       LLM trace 与 token 使用观测
  features/agent-harness/ 多 Agent pilot 观测台
  shared/                 错误边界、PageHero、QueryClient、fetch 包装
```

## 当前边界

- React 前端负责工作流与可视化，不承担采集、价格计算或任务编排
- `/` 首页现在定位为“证据看板”，`/buy/opportunities` 才是面向操作者的主动作页
- 历史 Jinja 页面仍然存在，部分跳转会回落到旧页面
- URL 中只保存工作区语境，不把复杂服务端状态放进前端 store
