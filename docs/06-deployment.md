# 服务器部署说明

Status: Active  
Updated: 2026-04-15  
Related Todo: [28-goofish-insight-upgrade-implementation-todolist-20260413.md](<repo-root>/docs/28-goofish-insight-upgrade-implementation-todolist-20260413.md)

## 1. 三层拓扑（W9 统一口径）

### 1.1 本地运行（单机日常）

- FastAPI + Jinja：`http://127.0.0.1:8787`
- 主要用途：本地运维、runtime 控制、Jinja 页面回查
- 访问方式：浏览器直接访问 FastAPI/Jinja，不经过 Nest BFF

### 1.2 本地开发（React 前端调试）

- React dev server：`http://127.0.0.1:5174`
- FastAPI API：`http://127.0.0.1:8791`
- 默认链路：React 直连 FastAPI（跨域由 FastAPI `DASHBOARD_CORS_ORIGINS` 控制）
- 回滚链路：通过开关切回 BFF（默认 `http://127.0.0.1:3000`）

React API 相关环境变量（`apps/dashboard-react`）：

- `VITE_DASHBOARD_API_MODE=fastapi|bff`（默认 `fastapi`）
- `VITE_FASTAPI_ORIGIN=http://127.0.0.1:8791`（`fastapi` 模式生效）
- `VITE_BFF_ORIGIN=http://127.0.0.1:3000`（`bff` 模式生效，缺省回退 `window.location.origin`）

### 1.3 生产目标（统一域名）

- 统一对外域名（示例）：`https://web.privateaitool.top`
- 网关/Nginx 反向代理到 FastAPI 服务（含 API 与静态）
- React 构建产物可由 FastAPI 或网关静态层托管，但 API 目标保持 FastAPI
- Nest BFF 进入“应急回滚层”而非主路径，不承载业务逻辑

## 2. BFF 处置结论（W9 完成定义）

- 结论：BFF 不作为主路径，保留为短期应急回滚通道。
- 原因：
  - 盘点确认 `apps/dashboard-nest/src` 当前仅做静态托管与 API 透传，无 auth middleware、无业务规则。
  - React 已具备直连 FastAPI 能力，主链路无需 BFF。
  - 保留显式开关可在 FastAPI 侧突发故障时快速切回透传链路，降低恢复成本。
- 退出条件（后续可下线 BFF）：
  - 连续稳定运行且无 BFF 回滚需求；
  - 生产网关/反代策略固化；
  - API 错误码与 CORS 策略在 FastAPI 侧稳定可观测。

## 3. 当前服务器与基础状态

- 部署目标：远程 Linux 服务器
- 编排方式：Docker Compose
- 数据库：PostgreSQL
- 临时管理入口：Adminer
- 当前服务器地址：`<server-host>`

当前在线服务（截至 2026-03-21）：

- PostgreSQL：`<server-host>:5432`
- Adminer：`http://<server-host>:8080`

已验证项：

- SSH 可登录
- Docker / Docker Compose 可用
- PostgreSQL 容器健康检查通过
- `app.healthcheck` 初始化表可查询
- 本地到 `8080` 和 `5432` 的连通性正常

部署过程中额外发现：

- 服务器无法直接访问 Docker Hub
- 最终采用“本机导出镜像 -> 上传服务器 -> 远端 `docker load`”离线路径

## 4. 已准备好的部署文件

- [docker-compose.yml](<repo-root>/docker-compose.yml)
- [.env.example](<repo-root>/.env.example)
- [001-bootstrap.sql](<repo-root>/infra/postgres/init/001-bootstrap.sql)

## 5. 建议的远程部署步骤

1. 在服务器上安装 Docker 和 Docker Compose。
2. 上传项目目录到服务器。
3. 复制 `.env.example` 为 `.env` 并填写真实密码。
4. 如果服务器可访问 Docker Hub，执行 `docker compose up -d`。
5. 如果服务器无法访问 Docker Hub，改走离线镜像导入。
6. 验证 PostgreSQL 与 Adminer 服务健康。

## 6. 安全建议

- 不建议将 PostgreSQL `5432` 直接暴露到公网。
- 如果需要远程查看数据，优先暴露 Web 看板或受控的管理页面。
- 如果必须开放 Adminer，至少加 IP 白名单或反向代理认证。
