# 靠谱二手价格指导助手生产 Todo

Status: Active  
Updated: 2026-04-11  
Spec: [19-reliable-price-assistant-technical-spec.md](<repo-root>/docs/19-reliable-price-assistant-technical-spec.md)  
Implementation: [20-reliable-price-assistant-production-implementation.md](<repo-root>/docs/20-reliable-price-assistant-production-implementation.md)

## 执行日志

- 2026-04-10：再次收紧技术说明书，固定 `pricingKeyFields` 只归 active template metadata 语义，不再给 runtime profile 留定义价格语义的口子。
- 2026-04-10：新增生产实施文档，固定 Phase 0 到 Phase 5 的实施路线、灰度开关、回滚策略与验收口径。
- 2026-04-10：启动生产 Todo，切换为按实施阶段连续推进。
- 2026-04-10：新增首批四个业务域 `pricingKeyFields` 设计表，结合现网 active template 明确主价格字段、模板完整度规则与挂牌修正因素。
- 2026-04-10：新增 `pricing_templates.py` 与 `pricing_thresholds.py`，让 dashboard 首次能返回模板合同、模板完整度和字段覆盖情况。
- 2026-04-10：已重启 `127.0.0.1:8791` 后端并验证 `filters` / `pricing` section 返回 `pricing_contract`。
- 2026-04-10：已把 `availabilityTier / pricingBlockReason / pricingEvidence` 接入 dashboard pricing section 输出，并验证 `Mac mini / M4 / 16G / 256G` 当前被正确标记为 `blocked`。
- 2026-04-10：修复 `3030` React/Nest 看板 launchd 常驻方式，当前 `127.0.0.1:3030` 与 `127.0.0.1:8791` 均已稳定运行。
- 2026-04-10：baseline 链路已双写 `pricingTemplate`，并补上 `templateKey / baselineLookupKey / availability`；相关单测通过。
- 2026-04-10：opportunity 链路已优先按 `templateKey` 匹配，`product / brand` 命中显式降级为 `degraded_product / degraded_brand`。
- 2026-04-10：机会池状态已接入模板门控；未命中明确模板或未达 `guidance_ready` 的结果统一降为 `REFERENCE_ONLY`。
- 2026-04-10：提醒链路已增加模板严格门控；`REFERENCE_ONLY` 与非模板级命中不再触发 alert。
- 2026-04-10：已正式重建 `apple_computer` 今日 baseline（674 条）并刷新机会池；当前 Apple 机会默认按模板门控进入 `REFERENCE_ONLY / OPEN` 分流。
- 2026-04-10：React 首页已开始消费 `pricing_contract / pricing_availability`，空价格状态会直接说明“模板未完整 / 证据不足 / 仅供参考”，不再只显示笼统空态。
- 2026-04-10：Apple 今日 baseline 分层结果为 `guidance_ready=45 / reference_only=37 / blocked=234 / incomplete=358`；机会池刷新后为 `OPEN=24 / REFERENCE_ONLY=2281`，alert dry-run 命中 13 条、去重跳过 2 条。
- 2026-04-11：React 首页完成模板属性选择器接线；切换品类/型号时会清空旧模板值，避免跨型号残留导致的错误定价请求。
- 2026-04-11：React 首页价格卡改为 `guidance_ready` 才显示；`incomplete / blocked / reference_only` 统一展示合同状态说明，不再展示误导性价格卡。
- 2026-04-11：趋势面板改为严格按当前选中型号（优先精确规格）匹配，未命中时显示空态，不再回退混入其他型号趋势卡。
- 2026-04-11：后端 insights 趋势聚合开始消费 `selected_filters` 与 `filtered_item_ids`，选中型号/模板后趋势候选不再回卷到其它型号历史快照。
- 2026-04-11：后端趋势进一步收口：当 `templateKeyPreview` 完整时，趋势卡只统计同 `templateKey` 的挂牌历史快照，并补充回归测试防止同型号不同内存/硬盘混算。
- 2026-04-11：采集链路写入 `item_snapshots.extra_json.template_key / template_completeness`；趋势聚合优先按快照模板键归属，缺少快照模板键的过渡回放自动降级为 `reference_only`。
- 2026-04-11：机会 payload 新增 `templateMatchErrorType`，用于记录模板命中失败类型（降级 product/brand、缺模板键、可用性不足）。
- 2026-04-11：反馈链路自动归类 `feedbackAction / feedbackCategory`，并带上模板命中上下文落盘到 `buy_decision_feedback.payload`。
- 2026-04-11：新增 `buy feedback quality` 汇总接口（按 `guidance_ready/reference_only` 分层统计反馈覆盖、采纳率、拒绝原因、模板命中质量）。
- 2026-04-11：新增 `buy feedback calibration` 回流引擎，自动输出模板字段补强建议、阈值调整建议、排序权重建议，并接入 `/api/buy/feedback-calibration` 与买入工作台侧栏。
- 2026-04-11：新增模板链路 feature flags（`PRICE_TEMPLATE_CONTRACT/DASHBOARD/OPPORTUNITY/TREND/ALERT_STRICT_MODE`），并接入合同、机会状态、趋势模板过滤、提醒严格门控。
- 2026-04-11：新增模板可用性监控接口与命令（`/api/buy/template-monitoring`、`show-template-monitoring`），输出四层 tier 分布与当前开关状态。
- 2026-04-11：新增模板化 smoke checklist 文档 `25-template-mode-smoke-checklist.md`。
- 2026-04-11：新增分层回滚文档 `26-template-mode-rollback-playbook.md`，固定按 alert -> opportunity -> trend -> contract 的回滚顺序。
- 2026-04-11：完成本地灰度验证：`/api/buy/template-monitoring` 显示模板开关全开，首页 `pricing` section 可在 `partial -> complete` 间正确切换，机会层维持 `guidance_ready/reference_only` 分流。
- 2026-04-11：新增自动化 `smoke-template-mode` 命令，统一检查模板开关、tier 分布、机会摘要、合同完整度、趋势模板对齐并输出 pass/warn/fail 报告。
- 2026-04-11：已用 `run_template_mode_smoke(base_url=127.0.0.1:8791, category=apple_computer)` 实跑通过，`overallStatus=pass`。
- 2026-04-11：已打通 CLI 依赖降级兜底（`alembic/playwright` 缺失时不阻断 pricing 命令），`python -m goofish_insight.cli smoke-template-mode --category-code apple_computer` 实跑通过。
- 2026-04-11：`smoke-template-mode` 已支持报告落盘，最新报告位于 `reports/latest-template-mode-smoke.json`（当次输出 `overallStatus=pass`）。
- 2026-04-11：dashboard 基础上下文不再用 `heartbeat_days` 裁剪定价候选，改为严格按 `pricing_freshness_days` 取样；避免型号/模板选项在左侧频繁消失。
- 2026-04-11：React 规格选择器增加空值去重清洗（`sanitizeFilterOptions`），空白 chip 与重复选项不再渲染。

## Phase 0：合同冻结与品类表冻结

- [x] 冻结 [19-reliable-price-assistant-technical-spec.md](<repo-root>/docs/19-reliable-price-assistant-technical-spec.md)
- [x] 新增 [20-reliable-price-assistant-production-implementation.md](<repo-root>/docs/20-reliable-price-assistant-production-implementation.md)
- [x] 新增生产 Todo，按生产阶段推进
- [x] 输出首批四个业务域的 `pricingKeyFields` 设计表
- [x] 明确首批四个业务域的模板完整度规则
- [x] 明确首批四个业务域的挂牌修正因素

## Phase 1：后端模板合同落地

- [x] 新增 `pricing_templates.py`
- [x] 新增 `pricing_thresholds.py`
- [x] 单点固定 `templateKey` canonicalization
- [x] 单点固定 `pricingKeyFields` / `requiredFields` / `templateCompleteness`
- [x] 单点固定 `availabilityTier` / `pricingBlockReason` / `pricingEvidence`
- [x] dashboard filters API 输出模板合同字段
- [x] dashboard pricing API 输出模板合同字段
- [x] 为模板合同新增单元测试

## Phase 2：首页收口到模板价格工作台

- [x] 右侧改为模板属性选择器，而不是旧 spec label chip
- [x] 模板不完整时禁止显示价格卡
- [x] 价格卡只显示当前模板价格
- [x] 趋势区只显示当前模板走势
- [x] 首页不再混入其他型号或其他模板的趋势卡
- [x] React 侧补模板合同消费与状态渲染

## Phase 3：baseline / opportunity 收口

- [x] baseline payload 双写 `pricingTemplate`
- [x] baseline 读路径优先 `templateKey`
- [x] opportunity payload 双写 `matchedTemplate*`
- [x] opportunity 先做模板匹配再评分
- [x] `degraded_product / degraded_brand` 强制降为 `REFERENCE_ONLY`
- [x] 非模板级命中不再触发提醒
- [x] watch target 支持 `pricingSelector`

## Phase 4：模板级趋势 v1

- [x] 新增模板级趋势聚合服务
- [x] 以 snapshot 时点模板归属聚合趋势
- [x] 过渡回放趋势只允许 `reference_only`
- [x] 首页接入模板级趋势
- [x] 趋势接口补测试

## Phase 5：反馈与校准闭环

- [x] 记录模板匹配错误原因
- [x] 记录人工拒绝机会时的模板/价格原因
- [x] 汇总 `reference_only` 与 `guidance_ready` 命中质量
- [x] 反馈回流到模板字段设计与阈值调整

## 运行与上线

- [x] 增加模板合同相关 feature flags
- [x] 增加 `guidance_ready / reference_only / blocked / incomplete` 监控
- [x] 增加模板化 smoke checklist
- [x] 增加分层回滚说明
- [x] 灰度上线首页模板模式
- [x] 灰度上线机会链路模板严格模式

## 当前进行中

- [x] Phase 1：实现模板合同服务第一刀，不切主流量
- [x] Phase 1：把 `availabilityTier` 真正接入价格区和后续 baseline / opportunity 链路
- [x] Phase 2：让 React 首页按模板合同收口，取消混合规格价格展示
- [x] Phase 4：开始接模板级趋势 v1，禁止同品类替代趋势卡
