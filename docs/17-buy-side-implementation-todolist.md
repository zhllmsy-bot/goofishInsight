# 二手买入决策实施 Todo

Status: Active
Updated: 2026-04-25
Spec: [16-buy-side-implementation-spec.md](<repo-root>/docs/16-buy-side-implementation-spec.md)

## 执行日志

- 2026-04-25：新增 `Daily Opportunity Pack`，买方工作台第一屏现在直接把 OPEN backlog 转成每日 TOP 20 处理队列，按 `立即看 / 可砍价 / 需复核` 分组，并把联系、跳过、成交与 ROI 表单接回现有反馈闭环。
- 2026-04-24：新增 Data Value Cockpit，买入工作台现在直接展示“有效商品 -> 结构化规格 -> 价格基线 -> 机会 -> 提醒 -> 反馈 -> 成交 -> ROI”漏斗；当前产品诊断会在反馈为 0 时明确标记为 `资源消耗态`，并提示优先消化 OPEN 机会而不是继续扩采集。
- 2026-04-24：将 React 工作台和机会详情页的“已成交”动作升级为成交结果表单，要求记录 `purchasePrice` / `expectedResalePrice` 并即时预览利润与 ROI；成交反馈现在会直接补强 `roiEvidenceCount` 与单机会 outcome proof。
- 2026-04-24：补齐真实 open engagement 埋点，机会详情页会写入 `detail_opened`，打开原始商品会写入 `listing_opened`；服务层保证 engagement 不改写 opportunity 决策状态，workbench 现可展示 `watch -> open -> contact` 漏斗。
- 2026-04-24：补齐第一版 buy-side 结果证据面，workbench 现展示 alert -> contacted -> purchased 的真实漏斗摘要与 ROI 证据覆盖；机会详情页同步展示单条机会的成交/ROI 证明状态。
- 2026-04-24：buy workbench 的校准建议现支持前端勾选后精选应用，操作者可在 React 工作台里选择要落地的 recommendation ids，而不是只能一键全量 apply。
- 2026-04-24：已将 `README.md`、`SPEC.md`、`docs/05-roadmap.md`、`docs/01-project-charter.md`、`docs/03-analysis-path.md`、`docs/04-frontend-path.md` 的高优入口口径收口到“二手买入决策助手”；仍保留少量历史深层文档待后续逐步清理。
- 2026-04-24：runtime `buy_jobs` 收口到类目作用域，当前类目可直接驱动 baseline / opportunity / alert 动作；同时明确 `buy_jobs` 默认不进入 resident runtime，而是作为按需分析单元留在 runtime control。
- 2026-04-24：将 baseline 构建主实现迁入 analyzer，新增 analyzer buy-side job 模块与直跑命令；至此 fair price / opportunity / calibration 主链都由 analyzer 承载，collector 只保留兼容入口。
- 2026-04-24：打通 feedback calibration apply 闭环，支持将建议回写到 runtime profile，并自动重建 baseline 与刷新 opportunity；workbench 现可展示当前生效阈值与机会分旋钮。
- 2026-04-23：补齐 runtime 控制台 `buy_jobs` 分组并接通 `build-buy-baselines` / `refresh-buy-opportunities` / `emit-buy-alerts` 动作，新增反馈汇总输出 `templateMismatchMissingFieldCounts`。
- 2026-04-22：补齐 analyzer `health/status` 的买方运行健康摘要，现可直接查看 `buy_price_baseline`、`buy_opportunity`、`buy_alert_event` 最近产出时间。
- 2026-04-08：已执行 Alembic `20260408_0019`，新增买方域 6 张表。
- 2026-04-08：已为 `apple_computer` 正式生成 baseline 895 条。
- 2026-04-08：已为 `garmin_watch` 正式生成 baseline 498 条。
- 2026-04-08：已按 `min_opportunity_score=85`、`limit=200` 为 `apple_computer` 写入首批机会 200 条。
- 2026-04-08：已按 `min_opportunity_score=85`、`limit=200` 为 `garmin_watch` 写入首批机会 200 条。
- 2026-04-08：已按 `min_opportunity_score=90`、`limit=50` 为 `apple_computer` 写入 dashboard inbox 提醒 50 条。
- 2026-04-08：已按 `min_opportunity_score=90`、`limit=50` 为 `garmin_watch` 写入 dashboard inbox 提醒 50 条。

## Phase 0：业务合同冻结

- [x] 固定业务方向为“二手买入决策助手”
- [x] 固定北极星目标：发现低于合理买入价、风险可控、转手不差的二手商品
- [x] 固定第一批目标大类：`apple_m_series`、`garmin_watch`
- [x] 固定第一阶段不做自动聊天、自动砍价、自动下单
- [ ] 将相关旧文档里的“泛采集平台”口径逐步更新为买方决策口径

## Phase 1：买方域数据模型

- [x] 新增 Alembic 迁移
- [x] 新增 `buy_watch_target`
- [x] 新增 `buy_price_baseline`
- [x] 新增 `buy_opportunity`
- [x] 新增 `buy_opportunity_risk`
- [x] 新增 `buy_alert_event`
- [x] 新增 `buy_decision_feedback`
- [x] 新增 ORM 模型
- [x] 补最小 metadata 测试
- [x] 跑模型测试

## Phase 2：合理价链路

- [x] 设计 `fair_price` 输入样本查询
- [x] 设计异常样本清洗规则
- [x] 实现配置级价格基线生成
- [x] 实现样本不足时的回退策略
- [x] 实现 `buy_ceiling`
- [x] 写入 `buy_price_baseline`
- [x] 新增 CLI `build-buy-baselines`

## Phase 3：机会池链路

- [x] 定义候选商品筛选条件
- [x] 关联 baseline 与最新商品
- [x] 计算 `discount_rate`
- [x] 计算 `risk_score`
- [x] 计算 `opportunity_score`
- [x] 写入或更新 `buy_opportunity`
- [x] 写入 `buy_opportunity_risk`
- [x] 新增 CLI `refresh-buy-opportunities`

## Phase 4：提醒链路

- [x] 建立 `watch_target` 命中规则
- [x] 建立提醒冷却规则
- [x] 写入 `buy_alert_event`
- [x] 先支持 dry-run 或 dashboard inbox 式提醒
- [x] 统计 `alert_hit_rate`

## Phase 5：买方工作台

 - [x] 新增买入目标页
 - [x] 新增机会列表页
 - [x] 新增机会详情页
 - [x] 新增价格基线页
 - [x] 在 Dashboard 加入“今日机会”卡片
- [x] 支持 `dismiss/contacted/purchased/not worth it`

## Phase 6：反馈闭环

- [x] 新增反馈写入接口
- [x] 新增反馈汇总任务
- [x] 输出误报原因统计
- [x] 反向调整 baseline 折扣系数、风险权重和识别阈值

## Phase 7：分析层收口

- [x] 在 `apps/analyzer` 新增买方分析作业模块
- [x] 将 `fair price` 计算迁入 analyzer
- [x] 将 `opportunity score` 聚合迁入 analyzer
- [x] 将反馈校准迁入 analyzer

## Phase 8：运行平面收口

- [x] 定义 buy jobs 的运行契约
- [x] 明确是否纳入 resident runtime
- [x] 明确 dashboard 控制页是否管理 buy jobs
- [x] 增加 baseline/opportunity/alert 健康检查

## Phase 9：数据价值利用率闭环

- [x] 新增 `/api/buy/data-value` 数据价值报告
- [x] 在 buy workbench 顶部展示 Data Value Cockpit
- [x] 将资源消耗态、决策未兑现、ROI 缺证据、价值闭环学习中定义为产品诊断状态
- [x] 展示按品类的 item/spec/opportunity/feedback/purchase/ROI 利用率
- [x] 在数据利用率低时明确建议优先消化 OPEN 机会
- [ ] 将 `emit-buy-alerts` 接入刷新后的 OPEN 机会运营节奏，避免机会刷新后提醒池停留在旧日期
- [x] 建立每日 TOP 20 OPEN 机会人工处理 SOP
- [ ] 当反馈覆盖率达到最低阈值后，才恢复扩品类或新增大规模采集任务
