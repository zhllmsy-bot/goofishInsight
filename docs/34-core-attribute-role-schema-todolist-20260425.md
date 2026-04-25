# 核心属性标记与规格 Schema 快照 Todo

Status: Active
Updated: 2026-04-25
Spec: [33-core-attribute-role-schema-spec-20260425.md](<repo-root>/docs/33-core-attribute-role-schema-spec-20260425.md)

## 执行日志

- 2026-04-25：启动核心属性标记机制；按当前仓库实际表结构，将声明层落在 `category_attr_template_item`，将生效层落在 `sku_spec_schema_snapshots`。

## Phase 0：合同冻结

- [x] 明确双层设计：模板声明层 + schema 快照生效层
- [x] 明确 `required` 复用现有 `is_required`
- [x] 明确当前价格指纹合同为 `baseline_key + schema_id`
- [x] 明确显式 `sku_fingerprints / item_samples` 是后续扩展，不在当前仓库硬造旁路

## Phase 1：声明层

- [x] `category_attr_template_item` 增加 `role`
- [x] `category_attr_template_item` 增加 `weight`
- [x] `category_attr_template_item` 增加 `normalization`
- [x] `category_attr_template_item` 增加 `enum_values`
- [x] 模板配置 API 支持读写上述字段
- [x] 模板 diff 覆盖 role/weight/normalization/enumValues
- [x] 单元测试覆盖模板声明层序列化和写入

## Phase 2：固化层

- [x] 新增 `sku_spec_schema_snapshots`
- [x] 新增 ORM 模型
- [x] 新增 active schema 快照服务
- [x] 模板发布或绑定 active template 时生成 schema snapshot
- [x] 迁移回填已有类目的 latest schema snapshot
- [x] `buy_price_baseline` 增加 `schema_id`
- [x] `buy_price_baseline` 唯一键升级为 `category_id + model_catalog_id + schema_id + baseline_key + baseline_date`

## Phase 3：价格链路接入

- [x] `load_pricing_records` 按类目加载 active schema
- [x] `role=locking & is_required=true` 缺失时排除 baseline 输入
- [x] baseline 写入 `schema_id`
- [x] baseline 序列化返回 schema 版本摘要
- [x] 单元测试覆盖缺失 locking required 不入 baseline

## Phase 4：API

- [x] 新增 `GET /api/categories/{code}/spec-schema`
- [x] API 返回 locking/required/variant/condition 分组
- [x] API 返回 weights/normalization/enumValues
- [x] API 在暂无持久快照时可从 active template 派生 fallback

## Phase 5：前端对接

- [ ] dashboard schema 类型增加 `SpecSchemaSnapshot`
- [ ] SKU 筛选器只允许 `locking` 字段做等值筛选
- [ ] 样本详情页按 role 分组展示规格
- [ ] baseline 卡片展示 `Schema vN · M locking attrs · valid_from 生效`
- [ ] 旧 schema baseline 增加 `Schema Outdated` 徽章
- [ ] 运维入口提供“按新 schema 回灌近 90 天”按钮

## Phase 6：异步与高可用

- [ ] 设计 `enrich_queue` 本地最小实现，先用数据库 outbox 或现有 job 表，不直接引入新消息基础设施
- [ ] 设计 `baseline_compute_queue` 去重与 10 分钟 debounce
- [ ] baseline 读路径接 Redis L1 缓存，TTL 5 分钟
- [ ] L2 `buy_price_baseline` miss 时允许 L3 实时计算并回写
- [ ] baseline 重算失败时沿用上一日快照并标记 `stale`
- [ ] schema 快照冲突时拒绝写入并报警

## Phase 7：显式指纹与样本表

- [ ] 评估是否新增 `sku_fingerprints`
- [ ] 评估是否新增 `item_samples`
- [ ] 若新增，`sku_fingerprints.schema_id` 必须为非空 FK
- [ ] 指纹 hash 必须包含 `schema_id`
- [ ] item sample 需要保留 `incomplete` 状态与缺失字段原因

## 验收清单

- [x] 每个属性可显式打 `role`，默认 `descriptive` 不参与计算
- [x] `role=locking & is_required=true` 的属性缺失时不入 baseline
- [x] baseline 挂 `schema_id`，可查历史 schema 定义
- [x] 模板变更不影响旧 baseline 可读性
- [ ] 前端筛选器仅允许在 locking attrs 上等值筛选
- [ ] 基线卡显式展示 Schema 版本号
- [ ] 基线查询 P99 < 100ms（Redis 后完成）
- [ ] 属性抽取 worker 可水平扩容，单 worker 挂掉不影响主链路
