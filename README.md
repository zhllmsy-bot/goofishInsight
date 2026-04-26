# Goofish Insight

闲鱼公开列表数据采集、建模分析与买方决策系统。

## 当前系统形态

Goofish Insight 是一套面向闲鱼公开供给的二手买入决策系统。围绕稳定大类持续采集公开列表样本，完成型号与配置识别，建立合理价、买入上限与机会判断，并把结果沉淀为可执行的买方工作台。

当前重点大类：

- `apple_computer` — 苹果电脑
- `garmin_watch` — 佳明手表

已开始扩展或试运行的方向：

- `camera_body`、`camera_interchangeable_lens`、`mobile_market_history`

## 三层前端架构

| 层 | 模块 | 角色 |
|---|---|---|
| 主工作台 | `apps/dashboard-react` | React 前端，唯一主运营工作台 |
| BFF 回退层 | `apps/dashboard-nest` | 静态托管 + API 代理，部署时回退 |
| 旧模板层 | `apps/web` | Jinja2 模板与静态资产（legacy） |

后端事实源是 `apps/collector` 的 FastAPI，默认 `http://127.0.0.1:8791`。

## 主文档

- 系统级技术说明书：[SPEC.md](./SPEC.md)
- 全局再评估 v2 战略收口方案：[docs/37-goofish-insight-global-reassessment-v2-strategy-spec-20260426.md](./docs/37-goofish-insight-global-reassessment-v2-strategy-spec-20260426.md)
- 全局再评估 v2 执行 Todo：[docs/38-goofish-insight-global-reassessment-v2-todolist-20260426.md](./docs/38-goofish-insight-global-reassessment-v2-todolist-20260426.md)
- 产品愿景： [docs/PRODUCT_VISION.md](./docs/PRODUCT_VISION.md)
- 设计基准： [docs/DESIGN_BENCHMARK.md](./docs/DESIGN_BENCHMARK.md)
- 最佳实践改造方案：[docs/23-best-practice-architecture-implementation-spec.md](./docs/23-best-practice-architecture-implementation-spec.md)
- 买方业务技术实施书：[docs/16-buy-side-implementation-spec.md](./docs/16-buy-side-implementation-spec.md)
- 核心属性与 Schema 快照方案：[docs/33-core-attribute-role-schema-spec-20260425.md](./docs/33-core-attribute-role-schema-spec-20260425.md)
- Dashboard UI 宪法 v2：[docs/39-goofish-insight-ui-constitution-v2-20260426.md](./docs/39-goofish-insight-ui-constitution-v2-20260426.md)
- Bloomberg 买方终端 UI 方案：[docs/35-bloomberg-buy-terminal-ui-redesign-spec-20260425.md](./docs/35-bloomberg-buy-terminal-ui-redesign-spec-20260425.md)
- 架构重构追踪说明：[docs/08-architecture-refactor-spec.md](./docs/08-architecture-refactor-spec.md)
- 商品属性系统方案：[docs/product-attribute-system/README.md](./docs/product-attribute-system/README.md)
- ADR 与技术决策：
  - [ADR-0001 Android overlay 主线退出](./docs/ADR-android-overlay-mainline-exit-20260426.md)
  - [ADR-0002 Jinja legacy 收敛](./docs/ADR-jinja-legacy-convergence-20260426.md)

## 许可证与免责声明

- License: [GNU AGPLv3](./LICENSE)
- 使用边界与风险声明：[DISCLAIMER.md](./DISCLAIMER.md)
- 发布说明：[CHANGELOG.md](./CHANGELOG.md)

## 需求交付标准

本仓库交付必须基于当前仓库真实状态，不把规划文档当作已交付能力。必须明确区分"已落地""部分落地""仅文档规划"。

当前本地命令入口以 `python -m goofish_insight.cli` 为准。涉及采集、清洗、规格抽取、定价、机会刷新和 dashboard 运维时，优先使用该入口而不是历史 shell 包装脚本。

## 核心原则

- 只采集公开可见字段，不触碰聊天、手机号、地址、实名等隐私信息。
- 由浏览器正常发起请求，系统负责监听响应、解析结果和落库。
- 原始响应必须保留，分析结果必须可回溯。
- 规则优先，LLM 作为补强与审查能力。
- 买方判断必须服务实际决策，优先回答“值不值得买”“合理价是多少”“风险在哪里”。

## 目录结构

```text
goofish-insight/
  apps/
    collector/         采集、标准化、review、spec enrichment、dashboard API、runtime 控制
    analyzer/          分析作业、买方决策聚合、评分与报告
    dashboard-react/   React 主工作台（唯一主运营前端）
    dashboard-nest/    BFF 回退层 + 静态托管
    web/               Jinja2 模板与静态资产（legacy）
    android-overlay/   Android overlay 采集辅助端
  scripts/             本地运行、worker、模型、批处理脚本
  infra/               PostgreSQL 初始化、launchd plist、部署相关文件
  docs/                项目级文档、SOP 与方案说明
  packages/
    schema/            数据表设计与字段约定
```

## 运行架构

当前实际运行方式：

- **本地执行平面**：macOS 负责浏览器、采集、模型、dashboard、worker
- **远端数据平面**：PostgreSQL 作为主要数据存储
- **本地 `launchd`**：负责 resident runtime
- **Web 控制页**：部分本地进程控制

部署方向：远程服务器 + Docker Compose，PostgreSQL，Web 看板优先对外。

## Web Dashboard

```bash
python -m goofish_insight.cli serve-web --host 127.0.0.1 --port 8787
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787) to view captured listings, recent crawl runs, and item detail pages.

## v0.1.0 本地最短路径（示例）

```bash
cp .env.example .env           # 补齐运行参数
python -m goofish_insight.cli db-upgrade
python -m goofish_insight.cli collect-search --business-domain apple_computer --max-pages 1
python -m goofish_insight.cli enrich-specs --business-domain apple_computer --limit 50
python -m goofish_insight.cli build-buy-baselines --business-domain apple_computer
python -m goofish_insight.cli refresh-buy-opportunities --business-domain apple_computer
python -m goofish_insight.cli serve-web --host 127.0.0.1 --port 8787
```

每次发布前建议先运行：

```bash
npm run verify-baseline
```

## Buy Jobs 与冷启动兜底

- `python -m goofish_insight.cli queue-enrich-specs --business-domain apple_computer`
- `python -m goofish_insight.cli queue-buy-baselines --category-code apple_computer`
- `python -m goofish_insight.cli queue-buy-opportunities --category-code apple_computer`
- `python -m goofish_insight.cli process-buy-jobs --no-dry-run`

买方链路现在会持久化 `condition_adjusters / sku_neighbors / msrp_anchors / decision_feedback_log`：

- `condition_adjusters` 允许按品类配置成色 multiplier，并在无配置时回退启发式。
- `sku_neighbors` 为冷启动 SKU 提供邻近指纹回退。
- `msrp_anchors` 在基线缺失时提供 reference-only MSRP 锚点。
- `decision_feedback_log` 记录反馈闭环事件，连同 schema / fingerprint / baseline 证据一起落库。

## Dashboard 运行口径

- `python -m goofish_insight.cli serve-web` 启动的是 `apps/collector` 的 FastAPI 入口，既承载 React shell，也继续承载少量 legacy Jinja 运维/配置页，默认端口 `8787`。
- `apps/dashboard-react` 是主 React 工作台；当前路由口径是 `/` 直达今日机会台，`/market` 回到市场大盘，`/ops/*` 收敛运行与 LLM 观测页。
- `apps/dashboard-nest` 当前承担静态托管与 BFF 回退层角色，不是本地运维看板主入口。

## Spec Enrichment

The listing API does not expose all target specs as structured fields. Use the spec pipeline to normalize:

- Garmin: product line, model name, case size, solar, display type
- Apple: product line, chip family, screen size, CPU/GPU cores, memory, storage

Commands:

```bash
python -m goofish_insight.cli enrich-specs --business-domain garmin --limit 100
python -m goofish_insight.cli enrich-specs --business-domain apple_computer --limit 100
./scripts/run-ark-spec-enrichment.sh --business-domain apple_computer --limit 100
python -m goofish_insight.cli show-spec-summary --business-domain garmin
```

LLM fallback is optional and uses an OpenAI-compatible endpoint configured via `.env`.
`enrich-specs` is the first-pass structured extraction path: it resolves the item's category/template, exposes the template attribute list to the model, and persists extracted values into `item_spec_enrichments` plus normalized item fields.
`review-items-llm` remains a legacy review/anomaly-correction path. The canonical second-pass path is now `review-v3-second-pass`, while `enrich-specs` stays the primary extraction job.

## Skill Regression

Run the project skill regression suite from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/test_skills.ps1
```

The script validates every skill, runs each smoke test, and writes a machine-readable report to `reports/skill-test-report.json`.

## Delivery Baseline

Before reporting a code change as complete, run the unified baseline from the repository root:

```bash
npm run verify-baseline
```

The current P0 gates are:

- `npm run typecheck -w @goofish/dashboard-react`
- `npm run test -w @goofish/dashboard-react`
- `npm run typecheck -w @goofish/dashboard-nest`
- `npm run test:e2e -w @goofish/dashboard-nest -- --runInBand`
- `python -m compileall apps/collector/src apps/analyzer/src -q`
- `PYTHONPATH=apps/collector/src:apps/analyzer/src:packages/schema/src python -m unittest <selected modules>`

## Dashboard UI Gate

Dashboard UI work is governed by [UI constitution v2](./docs/39-goofish-insight-ui-constitution-v2-20260426.md). Treat it as the source of truth over older dashboard UI specs.

Required UI gates:

- start from a Figma or hand wireframe before implementation
- keep `/today` as the benchmark page before spreading patterns to other routes
- run `npm run design-system:check -w @goofish/dashboard-react` for ordinary UI work
- run `npm run design-system:audit -w @goofish/dashboard-react` for broad UI migrations
- include Light and Dark screenshots plus the pull request checklist for every UI PR

## 环境配置

使用 `.env` 文件或 shell 环境变量配置敏感信息：

```bash
# .env 文件示例
export ANTHROPIC_AUTH_TOKEN="your-token-here"
export ANTHROPIC_BASE_URL="https://your-api-endpoint"
export DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/goofish_insight"
```

**重要**：不要在代码或文档中提交真实的凭据。使用 `.env.example` 作为模板。
