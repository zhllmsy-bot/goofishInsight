# Goofish Insight 全局再评估 v2 执行 Todo

Status: Active
Updated: 2026-04-26
Spec: [37-goofish-insight-global-reassessment-v2-strategy-spec-20260426.md](<repo-root>/docs/37-goofish-insight-global-reassessment-v2-strategy-spec-20260426.md)

## 口径

- 本 todo 的 `[x]` 只表示当前仓库已有文件、代码、脚本或文档证据。
- 未实现的 12 周路线图不得为了“看起来完成”而勾选。
- 已经由专项文档完成的工作在这里作为依赖证据引用，不重复展开实现细节。

## 执行日志

- 2026-04-26：把全局再评估 v2 收口为战略 spec 与执行 todo。
- 2026-04-26：补齐 AGPLv3 `LICENSE`。
- 2026-04-26：补齐 `DISCLAIMER.md`。
- 2026-04-26：在 README 主文档区加入全局 v2 文档、许可证和免责声明入口。
- 2026-04-26：新增 `docs/PRODUCT_VISION.md` 与 `docs/DESIGN_BENCHMARK.md`。
- 2026-04-26：新增 Android 与 Jinja 双决策 ADR。
- 2026-04-26：新增 `sku_fingerprints` / `item_samples` ADR，并把样本持久化接入买方基线与机会作业。
- 2026-04-26：新增样本覆盖率/指纹命中率报告入口。
- 2026-04-26：补齐样本有效计数、recency 权重、MAD、质量 Tier、confidence_score 与 confidence_reasons 的基线/解释/前端读取链路。
- 2026-04-26：价格面板暴露 Schema vN、有效样本、近样本与样本原因标签。

## Phase 0：止血与合同冻结

- [x] 新增全局再评估 v2 战略 spec。
- [x] 新增全局再评估 v2 执行 todo。
- [x] 添加 AGPLv3 `LICENSE`。
- [x] 添加 `DISCLAIMER.md`。
- [x] README 增加全局 v2 文档入口。
- [x] README 增加许可证与免责声明入口。
- [x] 确认 `/` 固定为今日机会台，旧市场大盘进入 `/market`。
- [x] 确认项目定位为 Local-First 买手工作台，不做 v1.0 前 SaaS 化。
- [x] 确认现阶段不引入微服务作为默认答案。
- [x] 新增 `docs/PRODUCT_VISION.md`，写明北极星、反目标和 v1.0 边界。
- [x] 新增 `docs/DESIGN_BENCHMARK.md`，只保留合法可引用的参照文字、链接和自有截图。
- [x] 写一份 Android overlay 主线退出 ADR。
- [x] 写一份 Jinja legacy 收敛 ADR。

## Phase 1：SKU 指纹与样本事实层

- [x] `category_attr_template_item` 已支持 `role / weight / normalization / enum_values`。
- [x] `sku_spec_schema_snapshots` 已作为 schema 生效层落地。
- [x] `buy_price_baseline.schema_id` 已接入价格基线。
- [x] 当前价格指纹合同明确为 `baseline_key + schema_id`。
- [x] 写显式 `sku_fingerprints / item_samples` ADR，说明是否新增表、演进旧表或建立兼容 view。
- [x] 实现 `sku_fingerprints` 或等价持久化合同。
- [x] 实现 `item_samples` 或等价持久化合同。
- [x] 指纹 hash 包含 `schema_id`。
- [x] item sample 保留 `sample_state`、`missing_required_attrs`、`sample_quality_score` 和 `observed_at`。
- [ ] baseline 输入从 item sample 资格过滤读取，而不是重复散落 eligibility 规则。
- [x] Apple / Garmin / Camera 三类目指纹命中率统计进入报告。
- [x] 单元测试覆盖同一 listing 在不同 schema 下产生不同 fingerprint hash。
- [x] 单元测试覆盖 missing required locking attr 不进入 `eligible` sample。

## Phase 2：样本可靠度与价格合同

- [ ] 定义 `effective_sample_count` 与 `recency_weighted_sample_count`。
- [x] 定义 `effective_sample_count` 与 `recency_weighted_sample_count`。
- [x] baseline 输出 P15/P35/P50。
- [x] baseline 输出 MAD。
- [x] baseline 输出 Tier A/B/C/D。
- [x] baseline 输出 `confidence_score` 与 `confidence_reasons`。
- [x] Tier D 禁止输出强买入建议。
- [x] 详情 Sheet 展示 sample count、Tier、schema version 和样本原因。
- [ ] 价格 baseline golden tests 覆盖小样本、离散高、过期样本和缺字段样本。
- [ ] 发布前验收：Apple / Garmin 核心 SKU baseline 可回放到样本集合。

## Phase 3：成色修正器

- [ ] 定义 `condition_grade` 枚举。
- [ ] 定义 `warranty_state` 与 `accessory_state`。
- [ ] 定义 `damage_flags`。
- [ ] 实现 `condition_multiplier` 规则表。
- [ ] baseline 计算保留 raw price 与 normalized price。
- [ ] 机会详情展示成色修正证据。
- [ ] 单元测试覆盖同指纹不同成色样本归一化。
- [ ] 成色未知样本不应直接污染高置信 baseline。

## Phase 4：冷启动与邻近推理

- [ ] 定义邻近 SKU 距离函数。
- [ ] 定义 cold-start baseline 输出合同。
- [ ] cold-start 输出必须包含 uncertainty。
- [ ] cold-start 不允许给强买入动作，只能给参考区间。
- [ ] 实现 n < 5 样本时的降级路径。
- [ ] 单元测试覆盖无邻居、弱邻居、强邻居三种路径。

## Phase 5：配置后台专业化

- [ ] 为配置页 Inline Table Editor 写单独 spec。
- [ ] 为 UI view 与 YAML view 等价转换写单独 spec。
- [ ] 决定 `config/categories/*.yaml` 是否为长期真相源。
- [ ] 定义 DB 与 YAML 冲突策略。
- [ ] 实现模板属性 inline edit。
- [ ] 实现 YAML preview / validate / apply。
- [ ] 实现配置 diff 审计。
- [ ] 将模板完整性校验接入 CI。
- [ ] 支持通过 PR 审计配置变更。

## Phase 6：工程拆分与门禁

- [ ] 为 `cli.py` 拆分补 golden tests。
- [ ] 为 `specs.py` 拆分补 golden tests。
- [ ] 为 `pricing.py` 拆分补 golden tests。
- [ ] `cli.py` 退化为兼容入口和注册层。
- [ ] `specs.py` 拆为 extraction、normalization、schema、persistence。
- [ ] `pricing.py` 拆为 records、eligibility、baseline math、serialization。
- [ ] `runtime_controls.py` 拆为 process status、job commands、logs、health。
- [ ] Python 单文件软上限 30KB 检查接入脚本。
- [ ] CLI 子命令文件软上限 20KB 检查接入脚本。
- [ ] `npm run verify-baseline` 在发布前常绿。

## Phase 7：UI 与视觉后续收口

- [x] Dashboard 设计系统迁移完成并形成 audit 脚本。
- [x] 今日机会台 dense row benchmark 完成。
- [x] 详情 Sheet 主路径完成。
- [x] `J/K`、`Enter`、`A/D`、`G O/M/C` 键盘主路径完成。
- [ ] 基线卡显式展示 `Schema vN`。
- [ ] 旧 schema baseline 展示 `Schema Outdated` 状态。
- [ ] `SpecSchemaSnapshot` 前端类型与筛选器完全接入。
- [ ] 配置页迁入同一视觉密度，不再像数据库表单堆叠。
- [ ] `docs/DESIGN_BENCHMARK.md` 与 design-system audit 形成人工验收入口。

## Phase 8：Runtime 与主动情报

- [ ] 设计 `enrich_queue` 本地最小实现，优先使用 DB outbox 或现有 job 表。
- [ ] 设计 `baseline_compute_queue` 去重与 10 分钟 debounce。
- [ ] 设计 baseline stale fallback。
- [ ] 设计 Redis L1 cache 的引入条件，不在当前阶段默认引入。
- [ ] 实现价格塌陷预警。
- [ ] 实现机会爆发预警。
- [ ] 实现供给枯竭预警。
- [ ] 实现异常高价预警。
- [ ] 日活机会推送目标稳定在 10-30 条。

## Phase 9：技术栈收缩

- [ ] Android overlay 主线退出决策完成。
- [ ] 若保留，移动到 `labs/android-overlay` 或独立仓库。
- [ ] Jinja legacy 路径列出保留清单。
- [ ] Jinja legacy 路径列出删除清单。
- [ ] React 覆盖高频配置与回查流程。
- [ ] `apps/web` 只保留 admin/support 或被物理删除。
- [ ] analyzer 与 collector 的职责边界按买方服务继续迁移。

## Phase 10：Release

- [x] 新增 `CHANGELOG.md`。
- [x] README 顶部补齐 v0.1.0 本地启动最短路径。
- [x] `DISCLAIMER.md` 覆盖采集、账号、ToS、隐私和非投资建议。
- [ ] v0.1.0 release checklist。
- [ ] 至少 5 个真实买手使用反馈或等价内部试用记录。
- [ ] release 前执行 `npm run verify-baseline`。

## v1.0 前总验收

- [x] 合规文件和 README 入口存在。
- [ ] SKU 指纹、样本可靠度、成色修正在 Apple/Garmin 端到端可用。
- [ ] 今日机会台、详情 Sheet、反馈动作和 baseline 证据闭环。
- [ ] 配置页支持可审计改动。
- [ ] `cli.py / specs.py / pricing.py` 退出巨型单文件状态。
- [ ] Android overlay 主线退出决策完成。
- [ ] Jinja legacy 路径收敛到明确 support 边界。
- [ ] v0.1.0 可按 README 在本地复现。
