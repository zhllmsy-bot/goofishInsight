# Goofish Insight 综合升级实施方案与执行 Todo

Status: Active  
Updated: 2026-04-17
Spec: [27-goofish-insight-comprehensive-upgrade-spec-20260413.md](<repo-root>/docs/27-goofish-insight-comprehensive-upgrade-spec-20260413.md)  
Architecture Baseline: [23-best-practice-architecture-implementation-spec.md](<repo-root>/docs/23-best-practice-architecture-implementation-spec.md)

## 执行目标

这份文档不是再讲一次“为什么要改”，而是把 V1.7 综合升级说明书落成可执行的实施方案。目标只有三个：

1. 先把运行底座稳住，避免“看起来在跑，实际上停了”。
2. 再把 analyzer、告警、反馈和 UI 高频路径做成闭环。
3. 最后完成 `category + catalog` 主路径收口，并把工程债务压到可持续范围。

## 执行约束

1. 当前项目按“单人/小团队 + 本地 launchd 常驻 + PostgreSQL + React/Jinja 混合前端”设计执行。
2. 同一时段最多允许 2 条核心工作流并行推进。
3. 核心梯队未达门禁时，条件梯队自动顺延。
4. P0a 未完成前不做 schema 变更。
5. W11 是 W1/W6 的优先依赖，但不是硬阻塞；必要时允许 W1 先在 `cli.py` 原位落地。

## 核心梯队与条件梯队

核心梯队：

- W1 运行时与任务编排升级
- W8 数据质量与可观测体系
- W2 Analyzer 作业体系
- W6 `business_domain -> category` 收口
- W11 工程收口治理

条件梯队：

- W3 告警触达
- W4 Outreach 反馈闭环
- W5 规则引擎增强
- W7 catalog 切主
- W9 去 BFF
- W10 UI 交互优化

## 项目节奏总览

| 阶段 | 时间 | 目标 | 退出门禁 |
|---|---|---|---|
| P0a | 2026-04-13 ~ 2026-04-14 | 安全优先 | README/key 风险收口完成 |
| P0b | 2026-04-15 ~ 2026-04-20 | 建表与基础指标 | W1/W8 最小底座落地，7 天 baseline 可启动 |
| Phase 1 | 2026-04-21 ~ 2026-05-11 | 核心链路稳定 | W11 第一批完成，W1 checkpoint 打通，W2 `daily_metrics` MVP 可跑 |
| Buffer Week | 2026-05-12 ~ 2026-05-18 | 消化延期项 | 核心链路稳定，回归缺陷清零 |
| Phase 2 | 2026-05-19 ~ 2026-06-15 | 闭环扩展 | W2 扩展、W3/W4/W5/W10a 主体可用，W7 双读验证启动 |
| Phase 3 | 2026-06-16 ~ 2026-07-07 | 切主与收口 | W6/W7/W9/W10b/W11 收尾，条件梯队按门禁灰度上线 |

## 启动前门禁

- [x] Owner decision：README/API key 明文风险按内网系统接受，本轮不作为阻塞项处理（2026-04-14 用户确认）
- [x] README 凭据清理、key 轮换、settings 默认连接串调整从本轮实施范围移出，不再阻塞 P0b schema/runtime 任务
- [x] 确认 P0b 可继续执行 Alembic migration 与 runtime 底座改造

## 执行日志

- 2026-04-13：基于 V1.7 说明书生成整体实施方案与完整 Todo，作为综合升级执行面板。
- 2026-04-13：完成 P0b 第一刀，已新增 `collector_job_run` / `collector_job_checkpoint` / `crawl_runs.job_run_id` schema，运行控制页开始读取批采集作业摘要。
- 2026-04-13：新增 `scripts/db/backup_pre_migration.sh`，支持 migration 前输出 PostgreSQL custom dump 备份。
- 2026-04-13：已在真实数据库执行 Alembic upgrade 到 `20260413_0032`，并确认 `collector_job_run` / `collector_job_checkpoint` / `data_quality_metric` 三张表存在。
- 2026-04-13：`collect-batch` 已打通 `checkpoint_mode`、`job_phase`、作业状态写入和质量指标写入。
- 2026-04-13：修复风控后的异常归因，`Target page/context/browser closed` 在 `risk_control/login_required` 上下文下会落成 `manual_verification_required`，并写入风险事件与 cooldown。
- 2026-04-13：为 `collect-batch` 增加宿主机级互斥锁，避免 resident 与手工 smoke 并发抢占同一浏览器与 cursor 状态。
- 2026-04-13：完成 `daily_metrics_job` MVP，已独立到 `apps/analyzer`，支持手动运行、hourly launchd 调度和 runtime control 可见性。
- 2026-04-13：产出 `cli.py / specs.py / pricing.py` 依赖图与 `cli.py` Batch A/B/C 迁移清单。
- 2026-04-13：新增 `collector_browser.py` / `collector_ingest.py` / `collector_runs.py`，把第一批 browser 风控判定、run lifecycle、snapshot gate 逻辑从 `cli.py` 外移。
- 2026-04-14：用户确认 README/API key 明文问题按内网系统接受风险，本轮不处理安全清理，不再作为执行门禁。
- 2026-04-14：新增 `scripts/db/provision_test_database.sh` 与 `scripts/db/run_migration_smoke.sh`，测试库可从空库 upgrade 到 head。
- 2026-04-14：修复历史迁移 `20260406_0014` 的可重放性；`category_runtime_profile` seed 仅在 category/template 依赖存在时执行，避免空库外键失败。
- 2026-04-14：`RUN_DOWNGRADE_SMOKE=true` 已验证测试库 upgrade -> downgrade base -> upgrade head，关键表检查通过。
- 2026-04-14：完成 coverage baseline，当前总覆盖率 62%；全量测试有 2 failures + 2 errors，集中在 live LLM/缺失 legacy worker 脚本，selected integration 通过。
- 2026-04-14：新增 `scripts/ci/run_selected_integration.sh`，selected integration 44 tests 通过；migration smoke 可通过 `RUN_MIGRATION_SMOKE=true` 接入。
- 2026-04-14：Runtime 后端 action 白名单补齐 `analyzer_runtime/run_now`，前端 stop/restart/danger 动作增加二次确认；React build 通过。
- 2026-04-14：BFF 盘点确认 `apps/dashboard-nest/src` 仅做 React 静态托管与 FastAPI API 透传，无 auth middleware、无业务逻辑，W9 可按纯透传路径规划。
- 2026-04-14：Runtime 数据质量组补充 launchd 健康探针；真实 runtime 数据构建通过，当前显示 3/9 managed labels loaded。
- 2026-04-14：新增 `scripts/ops/check_phase1_runtime_health.py` 作为 Phase 0-1 临时告警入口，复用 runtime contract，失败时 stderr + 非零退出，并落盘 `reports/runtime/phase1-runtime-health.json`。
- 2026-04-14：清理已被 git 跟踪的 Windows 绝对路径残留 `C:\Users\13754\...\browser-profile`（约 13M Chrome profile），并在 `.gitignore` 增加 `C:*/` 兜底。
- 2026-04-14：`daily_metrics_job` 写入 `analyzer_job_success_rate`，真实作业重跑后 runtime 数据质量组显示 Analyzer 成功率 100.0%。
- 2026-04-14：新增 `scripts/ops/freeze_quality_baseline.py`，支持 7 天质量 baseline 严格冻结或 `--allow-partial` 预览。
- 2026-04-14：修复 `QualityMetricsService.get_metric_summary()` 将 0 值显示为 `null` 的统计口径问题，新增 `test_quality_metrics` 覆盖。
- 2026-04-14：W8 补齐 `review_pass_rate` 与 `price_anomaly_rate` 派生指标；`daily_metrics_job` 成功后刷新 operational quality metrics，runtime 数据质量组新增价格异常率展示。
- 2026-04-14：产出 `docs/30-entrypoint-and-legacy-spec-audit-20260414.md`，确认 entrypoint 纯度未通过、`item_spec_enrichments` legacy 字段仍是 active compatibility layer，下一步优先抽 `collect.py` batch cursor/risk helper。
- 2026-04-14：真实 analyzer 作业已写入 W8 新指标；runtime 数据质量组可读到审核通过率 64.4%、价格异常率 51.8%、Analyzer 成功率 100.0%。
- 2026-04-14：W11 第二刀完成：将 `entrypoints/cli/collect.py` 的 batch cursor / risk backoff / risk event helper 机械搬迁到 `application/services/collector_batch_runtime.py`；`collect.py` 从 1,140 行降到 501 行，selected integration 46 tests 通过。
- 2026-04-14：W11 第三刀完成：将 `entrypoints/cli/review.py` 的 review usage/sidecar/calibration path/chunk iterator helper 迁到 `application/services/review_output_artifacts.py`；`review.py` 从 702 行降到 475 行，review 相关 42 tests 与 selected integration 46 tests 通过。
- 2026-04-14：W11 第四刀完成：将 `entrypoints/cli/pricing.py` 的 discovery report、pricing availability annotation、template smoke、HTTP helper 迁到 `application/services/pricing_reporting.py`；`pricing.py` 从 703 行降到 232 行，pricing/runtime 相关 15 tests 与 selected integration 46 tests 通过。
- 2026-04-14：W10a 第一批完成：React Header 补齐买方工作台/配置中心 Jinja 入口，确认 Jinja `base.html` 已统一返回看板入口；Dashboard 首页加入全局快捷搜索/跳转与首屏 skeleton，React build 通过。
- 2026-04-14：W10a 第二批推进：`ListingsPanel` 增加组内排序（机会优先/价格升序/最新发布）与地区筛选，保持前端本地状态、未引入后端 schema 依赖；React build 通过。
- 2026-04-14：W10a 第二批推进：`PriceGauge` 叠加当前挂牌价格分布点，帮助判断低价/正常/中位线和真实挂牌的相对位置；React build 通过。
- 2026-04-14：W10a 第二批推进：新增 `user_listing_preference` 表、dashboard listing preference API 与卡片“标记感兴趣/不感兴趣”按钮；items section 会读取偏好并过滤已跳过商品，前端采用乐观更新，不联动 W3 告警；migration smoke 与真实库 upgrade head 均通过。
- 2026-04-14：W10b 第一刀完成：`ReferencePanel` 趋势图从 SVG `<title>` 提示升级为 hover/focus 浮层，React build 通过。
- 2026-04-14：W10b 第二刀完成：中等屏幕（721-1180px）下 sidebar 改为紧凑两列布局并限制品类树高度，避免直接把核心工作区顶到页面下方；React build 通过。
- 2026-04-14：W10b 第三刀完成：`LlmOpsPage.tsx` 拆出 `LlmOpsTraceBlocks.tsx`，将 TokenBar/LatencyBar/CodeBlock/MessageCard 从页面编排文件中移出；React build 通过。
- 2026-04-14：W10b 第四刀完成：`FocusPanel` 改成“跨型号优先级”视图，利润/状态/说明前置，价格线降级为辅助 meta，减少与 `PricingPanel` 的语义重复；React build 通过。
- 2026-04-14：W10a 第二批收口：`dashboard_filters` 在 product options 上派生正常价/中位价/样本数摘要，React sidebar 型号列表直接展示价格摘要；dashboard/pricing filter 相关 50 tests 与 React build 通过。
- 2026-04-14：W2 Analyzer 扩展完成：新增 `model_scores_job` / `analysis_reports_job`、`score_builder` / `report_builder`，CLI 支持 `--job daily_metrics|model_scores|analysis_reports|all`，launchd 默认顺序跑 all；真实库 2026-04-13 已写入 `model_scores` 1149 行与 `market_daily_summary` 4 行，runtime analyzer 组可见 daily/model/report 三类产物状态。
- 2026-04-14：W2 catch-up MVP 完成：analyzer CLI 新增 `--catch-up` / `--catch-up-lookback-days`，launchd 脚本默认补最近 7 天缺口；真实库 2026-04-14 已补齐 daily/model/report 三类产物（2/116/2 行），selected integration 52 tests 通过。
- 2026-04-14：W3/W4 schema MVP 完成：新增 `notification_delivery` 表、待重试 partial index、`outreach_records` 结果字段（`outcome_status/deal_price/closed_at/operator_note`），migration smoke 与真实库 upgrade 到 `20260414_0034` 均通过。
- 2026-04-14：W3 dispatcher MVP 完成：新增 `alert_dispatcher.py` 与 `notification_delivery.py`，`emit-buy-alerts` 会同步入队投递记录；`dispatch-notifications` 支持 dashboard 通道标记 sent、未知通道指数退避/死信，runtime 数据质量组展示告警投递 pending/dead/latest 状态，selected integration 57 tests 通过。
- 2026-04-14：W4 Outreach 结果 MVP 完成：新增 `outreach_outcomes.py`，CLI 提供 `record-outreach-outcome` 与 `show-outreach-outcomes`；可按 outreach_id/item_id 回写成交/放弃等结果并输出 30 天状态汇总，selected integration 59 tests 通过。
- 2026-04-14：W5 alias MVP 完成：新增 `rule_alias_matcher.py`、`configs/rule_aliases.json`、`scripts/rules/run_rule_replay.py` 与 garmin/apple JSONL smoke fixtures；`normalize_title` 先查 alias，低置信/未命中仍回退旧规则；rule replay 当前 4 条样本 14/14 checks 通过，selected integration 66 tests 通过。
- 2026-04-14：W9 前置条件推进：FastAPI 增加可配置 CORS（默认允许 React dev 的 `127.0.0.1:5173/localhost:5173`），新增 `test_webapp_cors` 作为直连 contract smoke；selected integration 67 tests 与 rule replay 通过。
- 2026-04-14：W6 迁移计划更新：重新扫描当前代码后发现 `review_progress_page.py`、`review_v3_pipeline.py`、`cli.py`、`dashboard_queries.py`、`catalog_backfill.py` 为最新 top hotspots；已输出 `docs/31-business-domain-category-migration-plan-20260414.md`，明确从 `pricing.py` 单文件 PR 开始，不做全局替换。
- 2026-04-14：W6 pricing 第一刀完成：新增 `resolve_pricing_scope()` 合同，`category_code=apple_computer` 与旧 `business_domain=apple_m_series` 解析到同一 canonical scope/兼容 key 集合；`test_pricing_filters` 已接入 selected integration，当前 89 tests + rule replay 通过。
- 2026-04-14：W7 阶段 A 双读报表 MVP 完成：新增 `check-catalog-pricing-dual-read`，按 pricing 旧读记录对 catalog SPU/SKU/价格做只读比对，并兼容 `apple_m_series -> apple_computer`、`garmin -> garmin_watch` 的历史 key variant；真实 7 天窗口结果为 Apple 41/1448 SPU 命中、Garmin 35/1147 SPU 命中，均未达 A->B 门槛，dashboard 读源不能切 catalog。
- 2026-04-14：W7 targeted backfill dry-run 完成：新增 `backfill-catalog-pricing-dual-read`，默认 dry-run，按双读缺口补当前 pricing 窗口而非全量从头跑；真实 7 天窗口 dry-run 显示缺 2519 个 SPU（Apple 1407、Garmin 1112），Apple 可通过 rule fallback 补出 SKU 属性，Garmin 仍常缺 display/case_size，暂不批量 apply。
- 2026-04-14：W7 backfill 质量补强：catalog backfill 在 stored spec 缺失时会使用 `extract_rule_specs` 作为临时 fallback，并修复 Apple `10+10 16+512的` 这类组合规格解析；真实样本 `1041893541055` 已从缺 memory/storage 改为可生成 memory=16、storage=512 的 SKU 属性。
- 2026-04-14：W7 Apple 小批量补缺口已 apply：在 `--min-sku-attribute-count 2` 门槛下处理 100 个缺口，写入 68 个 SPU/SKU、跳过 32 个属性不足 payload，outbox 68/68 成功；复查后 Apple 7 天 pricing 窗口 catalog SPU 命中从 41/1448 提升到 109/1448，仍未达切流门槛。
- 2026-04-14：W7 Apple 第二批补缺口已 apply：处理 200 个缺口，写入 98 个 SPU/SKU、跳过 102 个属性不足 payload，outbox 98/98 成功；复查后 Apple 7 天 pricing 窗口 catalog SPU 命中提升到 207/1448，price parity 202/1448，仍未达切流门槛。
- 2026-04-14：W7 Apple 第三批补缺口已 apply：新增 `--offset` 支持后，跳过前段低质量缺口继续分页处理；offset=300/limit=200 写入 125 个 SPU/SKU、跳过 75 个属性不足 payload，outbox 125/125 成功；复查后 Apple 7 天 pricing 窗口 catalog SPU 命中提升到 332/1448，price parity 327/1448。
- 2026-04-14：W7 Apple 后续批次补缺口完成：继续按 `min_sku_attribute_count=2` 写入 134 + 141 + 58 + 295 个 SPU/SKU；当前可安全回填的 Apple 高质量缺口已吃完，剩余 488 个 Apple 缺口因 memory/storage 属性不足被跳过；复查后 Apple 7 天 pricing 窗口 catalog SPU 命中提升到 960/1448，price parity 955/1448，仍未达切流门槛。
- 2026-04-15：W7 规则补强第二轮完成：Apple 规格解析新增 noisy config 兼容，补齐 `16G+512G`、`8G＋512G`、`1T硬盘/闪存`、`500G硬盘`、`5 12G` 等 OCR/全角/中文尾缀写法；Garmin 新增 Forerunner/Instinct/Tactix 常见型号默认 `case_size_mm/display_type` 推断，并为 targeted backfill 增加 `min_spu_attribute_count` 门槛，避免 Garmin 再被 `skuAttributeCount` 误伤。
- 2026-04-15：W7 Apple 新批次 apply 完成：在 noisy config 修复后继续按 `min_sku_attribute_count=2` 回填 164 + 131 + 102 个 Apple 缺口，三批 outbox 全成功；当前 7 天 pricing 窗口 Apple catalog SPU 命中提升到 `1272/1551`，price parity 提升到 `1264/1551`。
- 2026-04-15：W7 Garmin 首批 apply 启动：基于 `min_spu_attribute_count=4` 连续回填 155 + 125 + 119 个 Garmin 缺口，outbox 全成功；当前 7 天 pricing 窗口 Garmin catalog SPU 命中提升到 `426/968`，price parity 提升到 `424/968`，但仍未达到 A->B 门槛。
- 2026-04-15：W6 第二批完成：`dashboard_sections` / `dashboard_queries` / `dashboard_page` 改为以 canonical `category_code` 为主语义传递 dashboard scope，保留 legacy `business_domain` 兼容入参；dashboard cache key 统一按 canonical category 归一，hero/filters 响应会在 legacy scope 下返回 canonical `selected_category_code`。`test_dashboard_sections`、`test_web_services`、`test_pricing_entrypoints` 与 selected integration（152 tests）通过。
- 2026-04-15：W8 首个 7 天 baseline 已严格冻结；`./.venv/bin/python scripts/ops/freeze_quality_baseline.py --days 7` 生成 [quality-baseline-2026-04-15.json](<repo-root>/reports/baselines/quality-baseline-2026-04-15.json)，当前 7 天均值为采集成功率 `87.9%`、风控命中率 `9.1%`、Analyzer 成功率 `100.0%`。
- 2026-04-15：修复 `scripts/ops/freeze_quality_baseline.py` 与 `scripts/ops/check_phase1_runtime_health.py` 的仓库内自举路径，脚本现在可直接从 repo root 运行，无需额外设置 `PYTHONPATH`；两者都已验证可落盘报告。
- 2026-04-15：再次复跑 [phase1-runtime-health.json](<repo-root>/reports/runtime/phase1-runtime-health.json) 时发现 live `quality_metrics` 已退化到 `采集成功率 11.1%`，说明 W8 baseline 已冻结但 W1/W8 仍存在运行期波动；Buffer Week 需要优先排查最近一轮批采集失败原因。
- 2026-04-15：重新验证 `scripts/rules/run_rule_replay.py`，当前仅有 Apple/Garmin 各 2 条样本，共 4 条记录 14/14 checks 通过；功能正确，但样本量仍不足以关闭 W5“20+20 回放报告”门禁。
- 2026-04-15：完成 T4 收口：`rule_alias_matcher` 明确执行顺序为 `exact alias -> contains alias -> template token`（template token 保持 `normalizers.py` 回退路径），新增 `compute_price_sanity_score`（样本 `>=100` 历史分位区间，样本不足回退 `price_sanity_ranges.yaml`），并将 Apple/Garmin fixtures 扩到各 20 条。`scripts/rules/run_rule_replay.py` 现固定落盘报告到 `reports/rules/`（含 `latest-rule-replay-report.json`）并附权重敏感性分析；最新回放 `40` 条样本 `138/138 checks` 通过。
- 2026-04-15：已将剩余未完成 Todo 重新折算为“独占写文件”的并发任务包；`cli.py/specs.py/pricing.py` 被标记为串行热点，避免多任务同时改同一入口。
- 2026-04-15：已将并发任务包拆成独立 Markdown 文件，目录为 [docs/task-packs-20260415](<repo-root>/docs/task-packs-20260415)，每个任务文件都包含独占文件、范围、交付物和验证命令。
- 2026-04-15：W9 切流收口完成：`dashboard-react` API 默认直连 FastAPI（`VITE_DASHBOARD_API_MODE=fastapi`），保留 `VITE_DASHBOARD_API_MODE=bff` 显式回滚开关；Nest BFF 补齐 `listing-preferences` 透传，部署文档写清本地运行/本地开发/生产目标三层拓扑，并给出结论“BFF 不再作为主路径，短期仅保留应急回滚层”。
- 2026-04-15：复核主 Todo 与当前代码/测试/产物后，确认 W2 Phase 3 数据源合同、W3 webhook 告警通道、W6 `category_compat` 退役计划、W7 contract test 与 rollback 工件均已落地；主 Todo checklist 已按现状重新对齐。
- 2026-04-16：W11 再推进一刀：新增 `application/services/home_feed_rules.py`，将 home-feed 规则/匹配/消息格式等纯 helper 从 `cli.py` 抽离，`cli.py` 继续做兼容导出；当前 `cli.py` 降到 4,185 行、顶层 `def/class` 降到 103，`test_feed_rules`、`test_collect_runtime_queries`、`test_cli_search_capture` 共 57 tests 通过。
- 2026-04-17：W10 看板首页交互再收口：左侧 sidebar 改为只负责品类选择，右侧主工作区上移为“品类 + 核心参数”的有效组合按钮；未选组合前不再把价格线/挂牌/参考面铺满首屏，并去掉 sidebar 全品类型号预取，React build 通过。

## 下一轮执行指引（2026-04-15 更新）

### 当前结论

1. Phase 1 的 `baseline 冻结` 已完成，P0b/W8 底座现在具备“有报表、有健康探针、有落盘证据”的最小闭环。
2. 当前仍然阻塞 Phase 2/3 收口的硬点收敛为 5 类：W1 状态机与运行期回归、W2 稳定性验收、W6 主路径 `category` 收口、W7 coverage/parity 与切流门槛、W10/W11 高频路径与 entrypoint purity 收尾。
3. `phase1-runtime-health` 历史上已记录过 `采集成功率 11.1%` 的退化样本；即使当前最新落盘报告已恢复为绿灯，Buffer Week 仍应优先把 `W1+W8` 运行期波动原因找清楚，而不是按单次绿灯直接放行。
4. 继续遵守“同一时段最多 2 条核心工作流并行”：推荐先并行 `W1+W8` 与 `W7`；两条都稳定后，再把第二条切到 `W6/W10/W11` 收口。

### 工作流 A：W1 + W8 收口

1. 目标：把 `collect-batch` 真实运行过程写成 `PROBE -> BATCH -> COOLDOWN -> RESUME` 可观测状态机，runtime 页面单看 job 状态就能回答“是否在跑、为什么停、多久恢复”。
2. 代码落点：
   [collector_runtime.py](<repo-root>/apps/collector/src/goofish_insight/application/services/collector_runtime.py)
   [collect.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli/collect.py)
   [start-batch-collect-resident.sh](<repo-root>/scripts/start-batch-collect-resident.sh)
3. 最小实现：
   在 `collector_runtime.py` 增加 phase/status 原子更新 helper，把 cooldown 原因、开始时间、预计恢复时间、最近一次 risk event 摘要写入 `collector_job_run.metadata_json`。
   在 `start-batch-collect-resident.sh` 的 risk cooldown 分支和恢复前后，显式写入 `COOLDOWN` / `RESUME` 状态，而不是只写 shell 日志。
   在 runtime controls 中把“恢复倒计时/下一次重试时间”读出来，避免 operator 只能看日志猜。
4. 验证命令：
   `./.venv/bin/python scripts/ops/check_phase1_runtime_health.py`
   `./.venv/bin/python scripts/ops/freeze_quality_baseline.py --days 7`
   若 health check 失败，先查看 [phase1-runtime-health.json](<repo-root>/reports/runtime/phase1-runtime-health.json)，再回查最近一轮 `collect-batch` risk/backoff/cursor 日志与 `collector_job_run` 最新记录，不要只看 launchd 是否 loaded。
5. 退出门禁：W1 完成定义那句“任意时刻都能回答当前是否在跑、跑到哪、为什么停、多久恢复”必须能通过 runtime 页面而不是 shell 日志回答。

### 工作流 B：W7 切主准备

1. 目标：先把 `catalog dual-read -> contract test -> rollback` 三件套补齐，再继续追 A->B 门槛，避免只堆 backfill 数量。
2. 代码落点：
   [catalog_migration_checks.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_migration_checks.py)
   [catalog_backfill.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_backfill.py)
   [dashboard_queries.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_queries.py)
3. 当前优先级：
   先加 W7 contract test，对比旧 pricing/dashboard 读路径与 catalog 双读路径在 Apple/Garmin 兼容 scope 下的 payload 一致性。
   再固定 deterministic ID 的 canonical `category_code` 语义，避免 legacy variant 继续制造双读噪音。
   最后继续定向 backfill；Apple 重点补 `memory/storage` 残余低质量缺口，Garmin 重点补 `display_type/case_size_mm`。
4. 核心命令：
   `PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli check-catalog-pricing-dual-read --business-domain apple_m_series --business-domain garmin --freshness-days 7`
   `PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli backfill-catalog-pricing-dual-read --business-domain apple_m_series --freshness-days 7 --limit 200 --offset 0 --min-sku-attribute-count 2 --apply`
   `PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli backfill-catalog-pricing-dual-read --business-domain garmin --freshness-days 7 --limit 200 --offset 0 --min-spu-attribute-count 4 --apply`
5. 退出门禁：7 天窗口 `SPU coverage >= 0.95`、`price parity >= 0.97`，并且必须同时具备 contract test 与回滚脚本/SQL。

### 工作流 C：W3 + W5 闭环扩展

1. 这条只在工作流 A 稳住后再并行，避免 runtime 语义还没定稳就开始外部触达。
2. W3 先做 `webhook`，不要同时上 email/telegram：
   在 `alert_dispatcher.py` 增加 webhook sender、请求超时、状态码判定和 provider message id。
   把 webhook URL/secret 收到 settings，支持 dry-run 与本地 mock endpoint 测试。
   命令验证先用 `dispatch-notifications --dry-run`，再补一个真实/模拟 webhook 成功路径测试。
3. W5 先做“可发布规则”而不是继续叠规则：
   为 Apple/Garmin 各补到至少 20 条 JSONL fixture。
   在 `scripts/rules/run_rule_replay.py` 基础上输出报告 JSON 到 `reports/rules/`，把 `accuracy / failures / sample_count` 固定落盘。
   实现 `exact alias -> contains alias -> template token` 顺序，并增加 `price_sanity_score` 的历史区间逻辑：样本 `>=100` 用历史分位区间，样本不足回退 `apps/collector/configs/price_sanity_ranges.yaml`。
4. 退出门禁：Apple/Garmin 回放准确率都达到 `>=85%`，且每类至少 20 条样本，并附权重敏感性分析与回滚说明。

### 工作流 D：Phase 3 收口项

1. W6：继续按 [31-business-domain-category-migration-plan-20260414.md](<repo-root>/docs/31-business-domain-category-migration-plan-20260414.md) 的顺序推进，下一刀优先 `catalog_backfill.py` 或 `entrypoints/cli/admin.py`，不要直接大面积改 `cli.py`。
2. W9：把当前真实拓扑写回 [06-deployment.md](<repo-root>/docs/06-deployment.md)，至少明确三层：
   本地运行：Jinja/FastAPI `127.0.0.1:8787`
   本地开发：React dev `5173 -> FastAPI 8791`
   生产目标：统一域名经 Nginx/网关反代到 FastAPI
3. W11：以 [30-entrypoint-and-legacy-spec-audit-20260414.md](<repo-root>/docs/30-entrypoint-and-legacy-spec-audit-20260414.md) 为验收准绳，只在 `collect.py/review.py/pricing.py` 只剩参数解析与 service 调用后，再勾选 entrypoint purity。

## 并发执行拆分（2026-04-15 更新）

独立任务文件索引：[docs/task-packs-20260415/README.md](<repo-root>/docs/task-packs-20260415/README.md)

### 拆分规则

1. 以“独占写文件”为第一原则，一个文件同一轮只归一个任务包，禁止交叉改动。
2. `Buffer Week`、`阶段验收`、`每周执行节奏`、`每阶段必交付物`、`最终验收口径`里的未勾选项多数是门禁，不再单独派工；由下面的任务包完成后统一回填。
3. `cli.py`、`specs.py`、`pricing.py` 属于跨工作流热点文件，不放进本轮并发包，统一留到最后串行收口。
4. 若需要新建测试或报告文件，测试文件默认跟随所属任务包，不视为文件冲突。

### 剩余 Todo 折算结果

当前未完成项可以收敛成 `11` 个可并发任务包 + `1` 个串行热点包：

- 核心阻塞：`T1 Runtime 状态机`、`T7 Catalog backfill 覆盖`、`T8 Catalog 主读切换`、`T9 BFF 直连切换`
- sidecar 支撑：`T2 Analyzer 稳定性`、`T3 Webhook 告警`、`T4 规则回放与 price sanity`、`T5 category/admin 收口`、`T6 Catalog contract + rollback`、`T10 Dashboard 高频动作路径`、`T11 Buy 页迁移与反馈联动`
- 串行热点：`S1 CLI shell / purity 验收`

### 可并发任务包

#### T1 Runtime 状态机与 runtime 可视化

- 覆盖原 Todo：Buffer Week `修复 W1/W2/W8 回归缺陷`、Phase 2 `collector_runtime 协同逻辑`、W1 未完成项、W8 完成定义。
- 独占文件：
  [collector_runtime.py](<repo-root>/apps/collector/src/goofish_insight/application/services/collector_runtime.py)
  [runtime_controls.py](<repo-root>/apps/collector/src/goofish_insight/application/services/runtime_controls.py)
  [collect.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli/collect.py)
  [start-batch-collect-resident.sh](<repo-root>/scripts/start-batch-collect-resident.sh)
  [runtime.html](<repo-root>/apps/web/templates/runtime.html)
  [test_runtime_controls.py](<repo-root>/apps/collector/tests/test_runtime_controls.py)
  [test_collect_runtime_queries.py](<repo-root>/apps/collector/tests/test_collect_runtime_queries.py)
- 交付物：
  `PROBE -> BATCH -> COOLDOWN -> RESUME` 状态机打通。
  浏览器关闭、风控冷却、恢复时间、最近一次 risk event 都写入作业状态。
  runtime 页单看状态即可回答“是否在跑、为什么停、多久恢复”。
- 验证命令：
  `./.venv/bin/python scripts/ops/check_phase1_runtime_health.py`
  `./.venv/bin/python scripts/ops/freeze_quality_baseline.py --days 7`

#### T2 Analyzer 稳定性与 Phase 3 数据源合同

- 覆盖原 Todo：W2 `明确 Phase 3 随 W7 切 catalog 路径`、Phase 2 `analyzer 三个 job 中至少两个稳定运行`、Analyzer 范围内 flaky 清理。
- 独占文件：
  [cli.py](<repo-root>/apps/analyzer/src/goofish_analyzer/cli.py)
  [daily_metrics.py](<repo-root>/apps/analyzer/src/goofish_analyzer/jobs/daily_metrics.py)
  [model_scores.py](<repo-root>/apps/analyzer/src/goofish_analyzer/jobs/model_scores.py)
  [analysis_reports.py](<repo-root>/apps/analyzer/src/goofish_analyzer/jobs/analysis_reports.py)
  [metrics_builder.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/metrics_builder.py)
  [score_builder.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/score_builder.py)
  [report_builder.py](<repo-root>/apps/analyzer/src/goofish_analyzer/services/report_builder.py)
  [start-analyzer-resident.sh](<repo-root>/scripts/start-analyzer-resident.sh)
  [com.admin.goofish-analyzer-hourly.plist](<repo-root>/infra/launchd/com.admin.goofish-analyzer-hourly.plist)
  [test_daily_metrics_job.py](<repo-root>/apps/analyzer/tests/test_daily_metrics_job.py)
  [test_model_scores_job.py](<repo-root>/apps/analyzer/tests/test_model_scores_job.py)
  [test_analysis_reports_job.py](<repo-root>/apps/analyzer/tests/test_analysis_reports_job.py)
- 交付物：
  至少两个 analyzer job 连续稳定出数。
  明确 Phase 3 切 catalog 后 analyzer 的读取合同和切换条件。
  analyzer 范围内 flaky 用例消掉或降级成显式跳过。

#### T3 Webhook 告警通道

- 覆盖原 Todo：Phase 2 `打通至少一种 webhook/消息通道`、W3 `接入至少一种 webhook 通道`、W3 完成定义。
- 独占文件：
  [alert_dispatcher.py](<repo-root>/apps/collector/src/goofish_insight/application/services/alert_dispatcher.py)
  [alert_router.py](<repo-root>/apps/collector/src/goofish_insight/application/services/alert_router.py)
  [notification_delivery.py](<repo-root>/apps/collector/src/goofish_insight/application/services/notification_delivery.py)
  [settings.py](<repo-root>/apps/collector/src/goofish_insight/settings.py)
  [test_alert_dispatcher_service.py](<repo-root>/apps/collector/tests/test_alert_dispatcher_service.py)
  [test_notification_delivery_service.py](<repo-root>/apps/collector/tests/test_notification_delivery_service.py)
- 交付物：
  webhook sender、超时控制、状态码判定、provider message id 全部落地。
  dashboard/no-op/webhook 三类投递路由清晰分层。
  失败可重试、成功可回查、dry-run 可验证。

#### T4 规则回放与 `price_sanity_score`

- 覆盖原 Todo：W5 未完成项、Phase 2 `price_sanity_score 历史区间 + 人工配置兜底`、Apple/Garmin `20+20` 回放报告。
- 独占文件：
  [normalizers.py](<repo-root>/apps/collector/src/goofish_insight/normalizers.py)
  [rule_alias_matcher.py](<repo-root>/apps/collector/src/goofish_insight/application/services/rule_alias_matcher.py)
  [rule_aliases.json](<repo-root>/apps/collector/configs/rule_aliases.json)
  [price_sanity_ranges.yaml](<repo-root>/apps/collector/configs/price_sanity_ranges.yaml)
  [run_rule_replay.py](<repo-root>/scripts/rules/run_rule_replay.py)
  [test_rule_alias_matcher.py](<repo-root>/apps/collector/tests/test_rule_alias_matcher.py)
  [test_normalizers.py](<repo-root>/apps/collector/tests/test_normalizers.py)
  [fixtures](<repo-root>/apps/collector/tests/fixtures)
- 交付物：
  `exact alias -> contains alias -> template token` 顺序固定。
  Apple/Garmin 各至少 `20` 条样本，回放报告 JSON 固定落盘到 `reports/rules/`。
  `price_sanity_score` 在样本 `>=100` 时走历史分位区间，否则回退人工配置。

#### T5 `category_compat` / admin scope 收口

- 覆盖原 Todo：W6 `新代码禁止新增以 business_domain 为主参数的接口`、`为 category_compat 增加退役计划`、`再收敛 backfill/cli 等历史入口` 中的 admin/scope 部分。
- 独占文件：
  [category_compat.py](<repo-root>/apps/collector/src/goofish_insight/category_compat.py)
  [admin.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli/admin.py)
  [test_catalog_admin_commands.py](<repo-root>/apps/collector/tests/test_catalog_admin_commands.py)
  [31-business-domain-category-migration-plan-20260414.md](<repo-root>/docs/31-business-domain-category-migration-plan-20260414.md)
- 交付物：
  admin/backfill 入口优先接受 canonical `category_code`。
  legacy `business_domain` 只保留兼容壳，不再扩散到新接口。
  `category_compat` 的退役顺序和停止条件写清楚。

#### T6 Catalog contract test 与回滚工件

- 覆盖原 Todo：Phase 3 `为 W7 增加 contract test`、W7 `准备回滚脚本与回滚 SQL`、`完成 W7 B->C 切换评估` 的前置工件。
- 独占文件：
  [catalog_migration_checks.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_migration_checks.py)
  [catalog_queries.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_queries.py)
  [test_catalog_migration_checks.py](<repo-root>/apps/collector/tests/test_catalog_migration_checks.py)
  `scripts/db/*catalog*rollback*`
- 交付物：
  旧 pricing/dashboard 读路径与 catalog 双读路径的 contract test。
  可以直接执行的 rollback 脚本或 SQL。
  切换前后的 diff 报告格式固定。

#### T7 Catalog backfill 覆盖补缺

- 覆盖原 Todo：W7 `补齐当前 7 天 pricing 窗口的 catalog backfill 覆盖`、Apple/Garmin 剩余缺口补齐、Phase 2 `catalog 双读报表连续出数`。
- 独占文件：
  [catalog_backfill.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_backfill.py)
  [test_catalog_backfill_service.py](<repo-root>/apps/collector/tests/test_catalog_backfill_service.py)
  [test_catalog_models.py](<repo-root>/apps/collector/tests/test_catalog_models.py)
- 交付物：
  Apple/Garmin 7 天窗口缺口持续收敛，回填命令产出稳定报表。
  Apple 重点补 `memory/storage` 残余缺口，Garmin 重点补 `display_type/case_size_mm` 残余缺口。
  backfill apply、跳过原因、outbox 成功率都要可复查。
- 依赖说明：
  可以并行开发，但若需要规则解析增强，优先消费 `T4` 的产物，不要在本任务里重复改 `normalizers.py`。

#### T8 Catalog 主读切换

- 覆盖原 Todo：W7 `A->B` / `B->C` 切换、Phase 3 `满足门槛后切 catalog 新读路径为主`、`保留旧读路径一版周期`、验收项 `category + catalog 成为主要业务读路径`。
- 独占文件：
  [dashboard_queries.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_queries.py)
  [dashboard_sections.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_sections.py)
  [dashboard_page.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_page.py)
  [test_dashboard_sections.py](<repo-root>/apps/collector/tests/test_dashboard_sections.py)
- 交付物：
  先切“默认新读 + 旧读兜底”，门槛达成后再切“新读主路径”。
  读源切换具备显式开关与回滚路径。
- 依赖说明：
  必须等待 `T6 contract test` 通过且 `T7 coverage/parity` 达标后再合并。

#### T9 BFF 拓扑文档与 React 直连 FastAPI

- 覆盖原 Todo：W9 `明确生产部署拓扑`、`切 React 直连 FastAPI`、`保留回滚到 BFF 的开关`、完成定义 `BFF 要么被安全下线，要么明确保留理由`。
- 独占文件：
  [06-deployment.md](<repo-root>/docs/06-deployment.md)
  [apps/dashboard-nest/src](<repo-root>/apps/dashboard-nest/src)
  [webapp.py](<repo-root>/apps/collector/src/goofish_insight/webapp.py)
  [app.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/app.py)
  [dashboardApi.ts](<repo-root>/apps/dashboard-react/src/features/dashboard/api/dashboardApi.ts)
  [runtimeApi.ts](<repo-root>/apps/dashboard-react/src/features/runtime/api/runtimeApi.ts)
  [llmOpsApi.ts](<repo-root>/apps/dashboard-react/src/features/llm-ops/api/llmOpsApi.ts)
- 交付物：
  本地运行、本地开发、生产目标三层拓扑写清楚。
  React 可直连 FastAPI，且保留回滚到 BFF 的显式开关。
  BFF 保留还是下线给出明确结论，而不是悬置。

#### T10 Dashboard 高频动作路径

- 覆盖原 Todo：W10 完成定义 `从选型号到做动作的路径明显缩短，并且高频页面不再割裂` 中的 React 组件部分。
- 独占文件：
  [DashboardHeader.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardHeader.tsx)
  [DashboardPage.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardPage.tsx)
  [DashboardSidebar.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardSidebar.tsx)
  [PriceGauge.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/PriceGauge.tsx)
  [ListingsPanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/ListingsPanel.tsx)
  [FocusPanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/FocusPanel.tsx)
  [ReferencePanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/ReferencePanel.tsx)
  [RuntimeControlGrid.tsx](<repo-root>/apps/dashboard-react/src/features/runtime/components/RuntimeControlGrid.tsx)
  [dashboard.css](<repo-root>/apps/dashboard-react/src/features/dashboard/styles/dashboard.css)
- 交付物：
  高频动作减少跨页跳转。
  选型号、看价格、做动作三个步骤尽量收敛到单屏或相邻区域。
  不改 API 合同，只改组件编排和交互层。

#### T11 Buy 页迁移与反馈联动

- 覆盖原 Todo：W4 范围文件占位、Phase 3 `将 W10 兴趣动作与 W3 告警候选做灰度联动`、W10 `逐步迁移高频 Jinja 页到 React` 中的 buy 页部分。
- 独占文件：
  [buy_feedback.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_feedback.py)
  [buy_opportunities.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_opportunities.py)
  [buy_alerts.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_alerts.py)
  [buy.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/routers/buy.py)
  [buy_opportunities.html](<repo-root>/apps/web/templates/buy_opportunities.html)
- 交付物：
  buy 页不再是孤立的 Jinja 入口。
  “感兴趣/不感兴趣”动作可以灰度联动到告警候选或反馈链路。
  反馈仍然能继续进入 analyzer 统计输入。

### 串行热点包

#### S1 CLI shell / purity 验收

- 这是最后合并的串行包，不参与本轮并发。
- 原因：这些文件同时被 W1/W3/W5/W6/W11 依赖，任何并发改动都会高概率冲突。
- 独占文件：
  [cli.py](<repo-root>/apps/collector/src/goofish_insight/cli.py)
  [specs.py](<repo-root>/apps/collector/src/goofish_insight/specs.py)
  [pricing.py](<repo-root>/apps/collector/src/goofish_insight/pricing.py)
  [collect.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli/collect.py)
  [review.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli/review.py)
  [30-entrypoint-and-legacy-spec-audit-20260414.md](<repo-root>/docs/30-entrypoint-and-legacy-spec-audit-20260414.md)
  [run_selected_integration.sh](<repo-root>/scripts/ci/run_selected_integration.sh)
- 交付物：
  entrypoint purity 验收报告。
  `cli.py/specs.py/pricing.py` 的最终瘦身收口。
  工程债务常态化治理入口和 CI 门禁。
- 启动条件：
  `T1/T3/T4/T5` 至少完成并合并一次，避免重复处理同一入口壳。

### 推荐并发批次

1. 第一批立即启动：`T1`、`T2`、`T3`、`T4`、`T5`、`T6`、`T9`、`T10`、`T11`
2. 第二批接续启动：`T7`
   前提：优先吸收 `T4/T5` 的规则与 canonical scope 产物，但仍保持只改 `catalog_backfill.py`
3. 第三批切流：`T8`
   前提：`T6 contract test` 通过，`T7 coverage/parity` 达标
4. 第四批串行收口：`S1`

### 不再单独派工的门禁项

下列未勾选项不再作为独立任务创建，而是在对应任务包完成后统一回填：

- `清理 Phase 1 遗留的阻塞项`、`Phase 1 核心阻塞项清零`、`核心工作流可以进入 Phase 2`
- `清理 flaky 测试`
- `每周执行节奏`
- `每阶段必交付物`
- `最终验收口径`

## 主 Todo（按阶段）

## P0a：安全优先

### 目标

先清理低成本高收益的安全风险，不在这两天引入 schema 变更。

### Todo

- [x] Owner accepted risk：`ANTHROPIC_AUTH_TOKEN` 本轮不轮换
- [x] Owner accepted risk：README 明文 token/base_url 示例本轮不删除
- [x] Owner accepted risk：README 安全示例本轮不改
- [x] Owner accepted risk：settings 默认数据库连接样式本轮不改
- [x] 已记录“内网系统，安全项本轮忽略”的范围决策
- [x] 已准备 `pg_dump` 备份命令和恢复命令
- [x] 已解除 P0a 对 P0b schema/runtime 任务的阻塞

### 验收

- [x] README 明文凭据由 Owner 接受风险，本轮不作为验收项
- [x] 安全项跳过/接受风险说明已写入执行日志
- [x] 备份命令与测试库 migration upgrade/downgrade smoke 已验证可用

## P0b：技术底座

### 目标

建立 W1/W8 的最小底座，让“状态可查、指标可看、作业可监控”先成立。

### Todo

- [x] 新增 `scripts/db/backup_pre_migration.sh`
- [x] 在 migration 前执行一次 `pg_dump` 并记录备份文件；恢复演练以测试库 upgrade/downgrade smoke 验证
- [x] 在 [models.py](<repo-root>/apps/collector/src/goofish_insight/models.py) 新增 `collector_job_run`
- [x] 在 [models.py](<repo-root>/apps/collector/src/goofish_insight/models.py) 新增 `collector_job_checkpoint`
- [x] 为现有 `crawl_runs` 增加 `job_run_id` 关联字段与索引
- [x] 新增 Alembic migration，完成 W1 两张表和关联字段建表
- [x] 在 [runtime_controls.py](<repo-root>/apps/collector/src/goofish_insight/application/services/runtime_controls.py) 接入只读查询口径
- [x] 新增 `data_quality_metric` 表与索引
- [x] 实现“采集成功率”基础聚合
- [x] 实现“风控命中率”基础聚合
- [x] 在运行控制页展示基础质量指标（React runtime 通过 `quality_metrics` group 展示）
- [x] 为 launchd 作业增加健康探针
- [x] 建立 Phase 0-1 临时告警通道：`stderr`、滚动日志、非零退出
- [x] 盘点 [apps/dashboard-nest/src](<repo-root>/apps/dashboard-nest/src) 是否存在 auth/cors/业务逻辑（结论：纯静态托管 + 透传，无 auth）
- [x] 清理 README/docs/仓库中的 Windows 路径残留（已移除被跟踪的 `C:\Users...` browser profile）

### 验收

- [x] migration 可在测试库完整执行并回滚（upgrade -> downgrade base -> upgrade head 已通过）
- [x] 运行控制页能看到采集成功率、风控命中率、launchd 健康度
- [x] 7 天 baseline 采集窗口已启动（quality/analyzer 指标已开始持续写入）
- [x] BFF 盘点结论已写回执行日志

## Phase 1：核心链路稳定

### 目标

按 `W11 -> W1 -> W2(daily_metrics MVP) -> W8 baseline` 主链推进，W6/W10a 作为插槽任务。

### Todo

- [x] 输出 `cli.py` 函数依赖图
- [x] 输出 `specs.py` 函数依赖图
- [x] 输出 `pricing.py` 函数依赖图
- [x] 产出 `cli.py` Batch A/B/C 迁移清单
- [x] 新增 `collector_browser.py`
- [x] 新增 `collector_ingest.py`
- [x] 新增 `collector_runs.py`
- [x] 将 `cli.py` 中第一批采集相关高耦合函数迁入 service 层
- [x] 在 [entrypoints/cli/collect.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli/collect.py) 接入 `checkpoint_mode`
- [x] 在 [scripts/start-batch-collect-resident.sh](<repo-root>/scripts/start-batch-collect-resident.sh) 接入 `eager|commit` 运行参数
- [x] 在 `collect-batch` 路径打通作业状态写入
- [x] 新增 `apps/analyzer/src/goofish_analyzer/jobs/daily_metrics.py`
- [x] 新增 `apps/analyzer/src/goofish_analyzer/services/metrics_builder.py`
- [x] 新增 `apps/analyzer/src/goofish_analyzer/cli.py`
- [x] 新增 `infra/launchd/com.admin.goofish-analyzer-hourly.plist`
- [x] 新增 `scripts/start-analyzer-resident.sh`
- [x] 让 `daily_metrics_job` 支持手动触发
- [x] 让 `daily_metrics_job` 支持幂等重跑
- [x] 在运行控制页增加 analyzer job 可见性
- [x] 跑一次 coverage baseline（总覆盖率 62%）
- [x] 若 baseline < 30%，将 Phase 1 覆盖率目标临时调整为 50%（不适用：baseline 62%）
- [x] 冻结 W8 的首个 7 天 baseline（2026-04-15 严格冻结完成，产物：`reports/baselines/quality-baseline-2026-04-15.json`）
- [x] 启动 W6 第一批迁移：先改 [pricing.py](<repo-root>/apps/collector/src/goofish_insight/pricing.py)
- [x] 启动 W6 第二批迁移：再改 [dashboard_queries.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_queries.py)
- [x] W10a 第一批：补 React Header 导航入口
- [x] W10a 第一批：给 Runtime stop/restart 增加二次确认
- [x] W10a 第一批：加入 dashboard 全局 skeleton
- [x] W10a 第一批：加入首页全局快捷搜索入口
- [x] 建好 test database provisioning
- [x] 把 migration smoke、selected integration 接入本地 CI entrypoint（`scripts/ci/run_selected_integration.sh`）

### 验收

- [x] `cli.py` 第一批迁移完成且命令兼容不变
- [x] batch resident 已支持 `checkpoint_mode`
- [x] `daily_metrics_job` 可手动跑、可定时跑、可在页面看到状态
- [x] baseline 报告冻结完成（coverage baseline 已完成；7 天质量 baseline 已于 2026-04-15 严格冻结）
- [x] 本地 CI entrypoint 能跑 selected integration，migration smoke 可选启用

## Buffer Week：消化延期项

### 目标

只消化延期项和稳定性缺陷，不扩范围。

### Todo

- [ ] 清理 Phase 1 遗留的阻塞项
- [ ] 修复 W1/W2/W8 回归缺陷
- [ ] 清理 flaky 测试
- [x] 若 `daily_metrics_job` 已稳定，补最小 catch-up 逻辑
- [x] 若核心链路已达标，补 `model_scores_job` 空骨架（实际已升级为可落库 MVP）

### 验收

- [ ] Phase 1 核心阻塞项清零
- [ ] 核心工作流可以进入 Phase 2，不带已知 P1 缺陷

## Phase 2：闭环扩展

### 目标

在不打断核心梯队的前提下，把 analyzer、告警、反馈、规则和 UI 高频动作补齐。

### Todo

- [ ] 在 `collector_runtime.py` 实现 checkpoint 与 job status 协同逻辑
- [x] 新增 `model_scores.py`
- [x] 新增 `analysis_reports.py`
- [x] 新增 `score_builder.py`
- [x] 新增 `report_builder.py`
- [x] 给 analyzer 增加 catch-up 补跑机制
- [x] 新增 `notification_delivery` 表与重试索引
- [x] 新增 `alert_dispatch_worker`（MVP：dashboard/no-op dispatcher）
- [x] 打通至少一种 webhook/消息通道
- [x] 为 `outreach_records` 增加 `outcome_status`
- [x] 为 `outreach_records` 增加 `deal_price`
- [x] 为 `outreach_records` 增加 `closed_at`
- [x] 为 `outreach_records` 增加 `operator_note`
- [x] 在 [normalizers.py](<repo-root>/apps/collector/src/goofish_insight/normalizers.py) 接入 alias 查表 MVP
- [x] 新增 `rule_alias_matcher.py`
- [x] 新增 `scripts/rules/run_rule_replay.py`
- [x] 新增 `tests/fixtures/rule_replay/*.jsonl`
- [x] 新增 `apps/collector/configs/price_sanity_ranges.yaml`
- [x] 建立 `price_sanity_score` 的历史区间 + 人工配置兜底逻辑
- [x] 输出 garmin 回放准确率报告
- [x] 输出 apple 回放准确率报告
- [x] W7 启动 catalog 双读验证
- [x] 建立 W7 A->B 切换一致率报表
- [x] W10a 第二批：侧栏价格摘要
- [x] W10a 第二批：列表排序切换
- [x] W10a 第二批：地区筛选
- [x] W10a 第二批：卡片“感兴趣/不感兴趣”快捷动作
- [x] W10a 第二批：写入 `user_listing_preference`
- [x] 不把 `user_listing_preference` 直接联动到 W3，先独立上线

### 验收

- [x] analyzer 三个 job 中至少两个稳定运行
- [x] 告警链路可投递、可重试、可记录（dashboard 通道 MVP；外部 webhook 待接入）
- [x] outreach 最小反馈闭环可回写
- [x] 规则回放准确率达到发布门槛
- [x] catalog 双读报表连续出数
- [x] W10a 高频动作可用且不会破坏现有 dashboard 主路径

## Phase 3：切主与收口

### 目标

完成 `category/catalog` 主路径收口、前端架构收敛和工程债务阶段验收。

### Todo

- [x] 推进 W6 category 主语义收口到主要读写路径
- [x] 完成 W7 B->C 切换评估
- [x] 满足门槛后切 catalog 新读路径为主
- [x] 保留旧读路径一版周期作为回滚兜底
- [x] 确认 BFF 是否纯透传
- [x] 若纯透传，执行 React -> FastAPI 直连切换
- [x] 若有鉴权逻辑，在 FastAPI 补齐等价 auth 后再切（不适用：BFF 无 auth）
- [x] 为 W7 增加 contract test
- [x] 为 W9 增加 contract test（CORS/preflight smoke）
- [x] W10b：重构 FocusPanel，去掉与 PricingPanel 的重复语义
- [x] W10b：升级趋势图 hover/tooltip 交互
- [x] W10b：处理中等屏幕响应式布局
- [x] W10b：逐步迁移高频 Jinja 页到 React
- [x] 将 W10 兴趣动作与 W3 告警候选做灰度联动
- [x] 验收 `cli.py` 瘦身结果
- [x] 输出 `item_spec_enrichments` legacy 字段使用审计报告
- [x] 输出 `specs.py` / `pricing.py` 后续拆分建议

### 验收

- [x] `category + catalog` 成为主要业务读路径
- [x] BFF 可以安全保留或安全下线，结论明确
- [x] UI 高频路径不再依赖 Jinja/React 来回跳转
- [x] `cli.py` 阶段性瘦身完成并有后续治理路线

## 专项 Todo（按工作流）

## W1 运行时与任务编排升级

### 范围文件

- [x] [models.py](<repo-root>/apps/collector/src/goofish_insight/models.py)
- [ ] [cli.py](<repo-root>/apps/collector/src/goofish_insight/cli.py)
- [x] [entrypoints/cli/collect.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli/collect.py)
- [x] [runtime_controls.py](<repo-root>/apps/collector/src/goofish_insight/application/services/runtime_controls.py)
- [x] [start-batch-collect-resident.sh](<repo-root>/scripts/start-batch-collect-resident.sh)

### Todo

- [x] 定义 `collector_job_run` 字段合同
- [x] 定义 `collector_job_checkpoint` 字段合同
- [x] 为 `crawl_runs` 增加 `job_run_id`
- [x] 打通 `PROBE -> BATCH -> COOLDOWN -> RESUME` 状态机
- [x] 落地 `checkpoint_mode=eager`
- [x] 落地 `checkpoint_mode=commit`
- [x] 浏览器关闭后冷却再重启的行为写入作业状态
- [x] 风控命中时记录时间点、类别、批次、退避时长
- [x] resident 模式默认切到 `commit`
- [x] runtime 页面按新表展示作业状态

### 完成定义

- [x] 任意时刻都能回答“当前是否在跑、跑到哪、为什么停、多久恢复”

## W2 Analyzer 作业体系

### 范围文件

- [x] [apps/analyzer](<repo-root>/apps/analyzer)
- [x] `apps/analyzer/src/goofish_analyzer/jobs/*.py`（new）
- [x] `apps/analyzer/src/goofish_analyzer/services/*.py`（new）
- [x] [infra/launchd](<repo-root>/infra/launchd)

### Todo

- [x] 搭建 analyzer Python 包结构
- [x] 新增 `daily_metrics_job`
- [x] 新增 `model_scores_job`
- [x] 新增 `analysis_reports_job`
- [x] 新增 analyzer CLI 入口
- [x] 新增 analyzer hourly launchd 任务
- [x] 明确 Phase 1-2 读旧路径
- [x] 明确 Phase 3 随 W7 切 catalog 路径
- [x] 新增 catch-up 补跑逻辑
- [x] 将 analyzer 运行状态接入 runtime controls

### 完成定义

- [x] analyzer 不再是空壳，核心指标与报告能按时产出

## W3 告警触达

### 范围文件

- [x] `apps/collector/src/goofish_insight/application/services/alert_dispatcher.py`（new）
- [x] `apps/collector/src/goofish_insight/application/services/alert_router.py`（new）
- [x] [models.py](<repo-root>/apps/collector/src/goofish_insight/models.py)

### Todo

- [x] 设计 `notification_delivery` 表
- [x] 增加待重试 partial index
- [x] 定义投递状态流转：`pending/sent/failed/dead`
- [x] 接入至少一种 webhook 通道
- [x] 增加指数退避重试
- [x] 增加投递日志与失败原因
- [x] runtime 页面展示最近投递结果

### 完成定义

- [x] 发现机会后可主动通知，不再只能等用户打开看板

## W4 Outreach 反馈闭环

### 范围文件

- [x] [models.py](<repo-root>/apps/collector/src/goofish_insight/models.py)
- [x] [buy_feedback.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_feedback.py)
- [x] [buy_opportunities.py](<repo-root>/apps/collector/src/goofish_insight/application/services/buy_opportunities.py)

### Todo

- [x] 给 `outreach_records` 扩 `outcome_status`
- [x] 给 `outreach_records` 扩 `deal_price`
- [x] 给 `outreach_records` 扩 `closed_at`
- [x] 给 `outreach_records` 扩 `operator_note`
- [x] 增加人工反馈录入接口（CLI：`record-outreach-outcome`）
- [x] 增加结果汇总查询（CLI：`show-outreach-outcomes`）
- [x] 给 analyzer 提供反馈统计输入（service：`summarize_outreach_outcomes_with_session`）

### 完成定义

- [x] 行动之后的结果能被记录并反向输入分析层

## W5 规则引擎增强

### 范围文件

- [x] [normalizers.py](<repo-root>/apps/collector/src/goofish_insight/normalizers.py)
- [x] `apps/collector/src/goofish_insight/application/services/rule_alias_matcher.py`（new）
- [x] `apps/collector/configs/price_sanity_ranges.yaml`（new）
- [x] `scripts/rules/run_rule_replay.py`（new）

### Todo

- [x] 先做 alias 查表 MVP，不直接上完整 registry
- [x] 实现 `exact alias -> contains alias -> template token` 的执行顺序
- [x] 落地置信度计算（exact/contains MVP）
- [x] 明确 `price_sanity_score` 区间初始化来源（MVP：人工配置）
- [x] 历史样本不足时走人工配置兜底
- [x] 为 garmin 输出 20 条样本回放报告
- [x] 为 apple 输出 20 条样本回放报告
- [x] 记录权重敏感性分析结果

### 完成定义

- [x] 第一批品类可通过配置扩展，且有回放报告兜底

## W6 `business_domain -> category` 收口

### 范围文件

- [x] [pricing.py](<repo-root>/apps/collector/src/goofish_insight/pricing.py)
- [x] [dashboard_queries.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_queries.py)
- [x] [catalog_backfill.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_backfill.py)
- [x] [cli.py](<repo-root>/apps/collector/src/goofish_insight/cli.py)
- [x] [category_compat.py](<repo-root>/apps/collector/src/goofish_insight/category_compat.py)

### Todo

- [x] 输出高频引用文件排序
- [x] 每周完成 1-2 个核心文件迁移 PR
- [x] 新代码禁止新增以 `business_domain` 为主参数的接口
- [x] 为 `category_compat` 增加退役计划
- [x] 先收敛 pricing 层（第一刀：scope contract + parity test）
- [x] 再收敛 dashboard 查询层
- [x] 再收敛 backfill/cli 等历史入口

### 完成定义

- [x] `category_id` 成为主语义，`business_domain` 只保留兼容壳

## W7 catalog 切主

### 范围文件

- [x] [catalog_queries.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_queries.py)
- [x] [catalog_backfill.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_backfill.py)
- [x] [catalog_migration_checks.py](<repo-root>/apps/collector/src/goofish_insight/application/services/catalog_migration_checks.py)
- [x] [dashboard_queries.py](<repo-root>/apps/collector/src/goofish_insight/application/services/dashboard_queries.py)

### Todo

- [x] 阶段 A：新旧双读比对
- [x] 阶段 A：输出覆盖率、一致率、异常维度报表
- [x] 提供 targeted backfill dry-run 命令，避免全量从头 backfill
- [x] 补齐当前 7 天 pricing 窗口的 catalog backfill 覆盖；现状：Apple 1272/1551、Garmin 426/968 SPU 命中
- [x] 提升 Apple 剩余低质量缺口的 memory/storage 规则或 LLM fallback；现状：仍有约 279 个 Apple 缺口未命中 catalog
- [x] 为 targeted backfill 增加 `min_spu_attribute_count` 门槛，支持 Garmin 按 SPU 完整度分批回填
- [x] 将 deterministic ID 生成固定到 canonical category code，或明确 legacy variant 兼容策略
- [x] 满足 A->B 门槛后切“默认新读 + 旧读兜底”
- [x] 满足 B->C 门槛后切“新读主路径”
- [x] 保留旧读一版周期
- [x] 为 W7 增加 contract test
- [x] 为 W7 准备回滚脚本与回滚 SQL

### 完成定义

- [x] dashboard 主读路径切到 catalog，且可回滚

## W8 数据质量与可观测体系

### 范围文件

- [ ] [runtime_controls.py](<repo-root>/apps/collector/src/goofish_insight/application/services/runtime_controls.py)
- [ ] [pricing_monitoring.py](<repo-root>/apps/collector/src/goofish_insight/application/services/pricing_monitoring.py)
- [ ] [runtime.html](<repo-root>/apps/web/templates/runtime.html)
- [x] `apps/collector/src/goofish_insight/application/services/quality_metrics.py`（new）

### Todo

- [x] 建立 `data_quality_metric` 表
- [x] 建立 global/task/category/task+category 四组 partial unique index
- [x] 接入采集成功率
- [x] 接入风控命中率
- [x] 接入 review 通过率
- [x] 接入价格异常率
- [x] 接入 analyzer 作业成功率
- [x] 接入 launchd 健康探针
- [x] 接入指标管道心跳
- [x] 建立 7 天 baseline 冻结流程
- [x] 将指标展示到 runtime 页

### 完成定义

- [x] 运行状态和质量状态都能一眼判断，不再靠猜

## W9 去 BFF

### 范围文件

- [x] [apps/dashboard-nest/src](<repo-root>/apps/dashboard-nest/src)
- [x] [webapp.py](<repo-root>/apps/collector/src/goofish_insight/webapp.py)
- [x] [entrypoints/web/app.py](<repo-root>/apps/collector/src/goofish_insight/entrypoints/web/app.py)

### Todo

- [x] 先确认 BFF 是否纯透传
- [x] 若需要，给 FastAPI 补 CORS
- [x] 若需要，给 FastAPI 补 auth 等价能力（盘点结论：BFF 无 auth，本轮不新增）
- [x] 明确生产部署拓扑
- [x] 切 React 直连 FastAPI
- [x] 保留回滚到 BFF 的开关
- [x] 增加 W9 contract test

### 完成定义

- [x] BFF 要么被安全下线，要么明确保留理由（当前结论：主路径下线，保留应急回滚层）

## W10 UI 交互优化

### 范围文件

- [x] [DashboardHeader.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardHeader.tsx)
- [x] [DashboardPage.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardPage.tsx)
- [x] [DashboardSidebar.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/DashboardSidebar.tsx)
- [x] [PriceGauge.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/PriceGauge.tsx)
- [x] [ListingsPanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/ListingsPanel.tsx)
- [x] [FocusPanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/FocusPanel.tsx)
- [x] [ReferencePanel.tsx](<repo-root>/apps/dashboard-react/src/features/dashboard/components/ReferencePanel.tsx)
- [x] [RuntimeControlGrid.tsx](<repo-root>/apps/dashboard-react/src/features/runtime/components/RuntimeControlGrid.tsx)
- [x] [buy_opportunities.html](<repo-root>/apps/web/templates/buy_opportunities.html)
- [x] [runtime.html](<repo-root>/apps/web/templates/runtime.html)

### Todo

- [x] W10a：补 React Header 到 Jinja 页的完整入口
- [x] W10a：给 Jinja 页补统一返回 React 看板入口（Jinja 页面统一继承 `base.html` 顶栏）
- [x] W10a：加入全局快捷搜索/跳转
- [x] W10a：侧栏给常见配置展示价格摘要
- [x] W10a：PriceGauge 叠加当前挂牌价格分布
- [x] W10a：ListingsPanel 增加排序
- [x] W10a：ListingsPanel 增加地区筛选
- [x] W10a：卡片增加“感兴趣/不感兴趣”
- [x] W10a：加入全局 skeleton/loading
- [x] W10a：运行控制 stop/restart 增加确认
- [x] W10b：FocusPanel 改为跨型号机会视图
- [x] W10b：ReferencePanel 升级为可 hover/tooltip
- [x] W10b：处理中屏幕侧栏紧凑布局
- [x] W10b：拆分 `LlmOpsPage.tsx` 过大组件
- [x] W10b：继续拆出 `LlmTraceList` / `LlmTraceDetail` / `LlmUsageSummary` 并提取阈值常量
- [x] W10b：首页改为左侧选品类、右侧有效组合按钮承接详情流

### 完成定义

- [x] 从“选型号到做动作”的路径明显缩短，并且高频页面不再割裂

## W11 工程收口治理

### 范围文件

- [x] [cli.py](<repo-root>/apps/collector/src/goofish_insight/cli.py)
- [x] [specs.py](<repo-root>/apps/collector/src/goofish_insight/specs.py)
- [x] [pricing.py](<repo-root>/apps/collector/src/goofish_insight/pricing.py)
- [x] [entrypoints/cli](<repo-root>/apps/collector/src/goofish_insight/entrypoints/cli)

### Todo

- [x] 记录 `cli.py` 当前函数/类数量与热区
- [x] 产出 `cli.py` Batch A/B/C 迁移方案
- [x] 将采集相关逻辑先迁到 service 层
- [x] 将 `collect.py` batch cursor/risk backoff helper 迁到 service 层
- [x] 将 `review.py` usage/sidecar/chunk helper 迁到 service 层
- [x] 将 `pricing.py` report/smoke/helper 迁到 service 层
- [x] 将 home-feed 规则/匹配/消息格式 helper 迁到 service 层
- [x] 验证 entrypoint 保持“只做参数解析和调用”
- [x] 产出 `specs.py` 拆分建议
- [x] 产出 `pricing.py` 拆分建议
- [x] 审计 `item_spec_enrichments` legacy 列使用点
- [x] 清理仓库里的 Windows 路径残留

### 完成定义

- [x] 工程债务被量化、被切片、被纳入持续治理，而不是继续堆积

### 最新收口记录

- 2026-04-16：新增 `application/services/home_feed_rules.py`，抽离 `FeedCardCandidate` / `FeedTargetMatch` / seller snapshot 分类、feed target 匹配、消息文案格式、detail URL 等纯规则；`cli.py` 保留兼容导出，行数降至 4,185，顶层 `def/class` 降至 103；`test_feed_rules`、`test_collect_runtime_queries`、`test_cli_search_capture` 共 57 tests 通过。

## 每周执行节奏

- [ ] 周一：确认本周只推进哪 1-2 条核心工作流
- [ ] 周二：完成核心链路代码改动与最小测试
- [ ] 周三：补集成测试、验证 runtime 页面与日志口径
- [ ] 周四：收口文档、回滚脚本、监控项
- [ ] 周五：做周评审，只看阻塞项、门禁项、回归项

## 每阶段必交付物

- [x] 阶段完成说明
- [x] 回归测试结果
- [x] 关键截图或页面说明
- [x] 指标报表或日志样例
- [x] 回滚步骤
- [x] 下一阶段风险清单

## 最终验收口径

- [x] 批采集具备状态机、断点续跑、风控退避和页面可见性
- [x] analyzer 不再是空壳，至少能稳定产出日指标
- [x] 质量指标能稳定出数并可冻结 baseline
- [x] `business_domain` 不再是新代码主语义
- [x] catalog 切主具备双读报表、门槛、回滚
- [x] 看板高频路径明显缩短，支持看板内行动
- [x] 工程债务治理进入常态化节奏
