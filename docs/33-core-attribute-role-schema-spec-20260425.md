# 核心属性标记与规格 Schema 快照技术方案

Status: Draft v1
Updated: 2026-04-25
Workspace: `<repo-root>`

Related:

- [23-best-practice-architecture-implementation-spec.md](<repo-root>/docs/23-best-practice-architecture-implementation-spec.md)
- [16-buy-side-implementation-spec.md](<repo-root>/docs/16-buy-side-implementation-spec.md)
- [19-reliable-price-assistant-technical-spec.md](<repo-root>/docs/19-reliable-price-assistant-technical-spec.md)
- [34-core-attribute-role-schema-todolist-20260425.md](<repo-root>/docs/34-core-attribute-role-schema-todolist-20260425.md)

## 1. 目标

把“哪些规格字段决定价格”从硬编码规则升级为可审计、可版本化的数据合同。

本方案采用双层设计：

- 声明层：`category_attr_template_item` 标记每个模板属性的定价角色、权重、枚举与规范化规则。
- 生效层：`sku_spec_schema_snapshots` 固化某个类目、某个模板版本的可定价 schema。

这对应项目当前架构中的配置主轴：

`category -> active template -> runtime profile -> pricing records -> buy_price_baseline`

## 2. 当前代码适配判断

用户草案中的 `category_attribute_templates` 在当前仓库里对应两张表：

- `category_attr_template`：模板版本头表，表达类目和版本。
- `category_attr_template_item`：模板属性明细，表达属性在该模板版本里的语义。

因此 `role / weight / normalization / enum_values` 应落在 `category_attr_template_item`，而不是落在模板头表。`required` 已由现有字段 `is_required` 表达，API 继续保留 `isRequired`，并在新 schema 输出里同时给出 `required` 语义。

## 3. 声明层合同

`category_attr_template_item` 新增字段：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `role` | `TEXT` | `descriptive` | `locking / variant / condition / descriptive` |
| `weight` | `NUMERIC(4,2)` | `0` | `0-1`，仅 `locking` 用于后续回归先验 |
| `normalization` | `JSONB` | `NULL` | 同义词、单位换算、枚举闭合等规范化规则 |
| `enum_values` | `JSONB` | `NULL` | 合法枚举值快照 |

角色语义：

| role | 语义 | 入价格指纹 | 参与回归 | 当前实现 |
|---|---|---|---|---|
| `locking` | 决定硬件或规格价值的核心属性 | 是 | 是 | 进入 schema `lockingAttrs` |
| `variant` | 颜色、地区等子变体 | 分桶保留 | 否 | 进入 schema `variantAttrs` |
| `condition` | 成色、保修、配件等状态修正因子 | 否 | 否 | 进入 schema `conditionAttrs` |
| `descriptive` | 展示或检索辅助字段 | 否 | 否 | 默认不参与定价 |

硬规则：

- `role=locking` 且 `is_required=true` 的字段缺失时，样本不得进入 baseline 聚合。
- `weight` 必须在 `0..1`。
- 角色值必须属于四种枚举之一。
- `normalization` 和 `enum_values` 只作为配置声明，不直接覆盖历史 schema。

## 4. 生效层合同

新增 `sku_spec_schema_snapshots`。

核心字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `schema_id` | `BIGSERIAL` | 不可变 schema 主键 |
| `category_code` | `TEXT` | 类目代码 |
| `category_id` | `UUID` | 当前类目 FK，便于 join |
| `template_id` | `UUID` | 生成该 schema 的模板版本 |
| `template_version` | `INT` | 模板版本号 |
| `locking_attrs` | `TEXT[]` | 该版本进入定价指纹的属性 |
| `required_attrs` | `TEXT[]` | 缺失即不入 baseline 的 locking 属性 |
| `variant_attrs` | `TEXT[]` | 子变体属性 |
| `condition_attrs` | `TEXT[]` | 成色/状态修正属性 |
| `weights` | `JSONB` | `{attr_code: weight}` |
| `normalization` | `JSONB` | `{attr_code: rules}` |
| `enum_values` | `JSONB` | `{attr_code: values}` |
| `valid_from / valid_to` | `TIMESTAMPTZ` | 生效窗口，`valid_to IS NULL` 为当前 |
| `created_by` | `TEXT` | 操作人或迁移来源 |

约束：

- `UNIQUE(category_code, template_version)`
- 同一个 `category_code` 同时最多一个 `valid_to IS NULL` 的当前 schema，由服务层关闭旧版本。
- `buy_price_baseline.schema_id` 指向该表，用于保证价格基线可回放。

## 5. 写入流程

### 5.1 模板配置写入

1. 管理端提交模板 items，包含 `role / weight / normalization / enumValues`。
2. 服务层校验 role 与 weight。
3. 写入 `category_attr_template_item`。
4. 当模板为 `PUBLISHED` 或被绑定为 active template 时，生成或更新当前 `sku_spec_schema_snapshots`：
   - 关闭同类目旧 active snapshot。
   - 插入新 snapshot，或更新同版本 snapshot。
   - `valid_from` 优先使用模板 `effective_at`，否则使用当前时间。

### 5.2 Baseline 写入

1. `load_pricing_records` 按类目加载当前 active schema。
2. `required_attrs` 缺失的记录直接排除在 baseline 聚合之外。
3. `build_buy_price_baselines` 写入 `buy_price_baseline.schema_id`。
4. 序列化 baseline 时返回 `schemaId` 和 `schemaSummary`，前端可展示版本来源。

当前仓库尚无持久化的 `item_samples` 与 `sku_fingerprints` 表；本轮按现有架构把 `baseline_key + schema_id` 作为可回放价格指纹合同。后续若引入显式 `sku_fingerprints`，必须复用同一个 `schema_id`。

## 6. API

新增：

`GET /api/categories/{code}/spec-schema`

返回：

```json
{
  "schemaId": 12,
  "categoryCode": "apple_computer",
  "templateVersion": 3,
  "lockingAttrs": ["model_name", "chip_family", "memory_gb", "storage_gb"],
  "requiredAttrs": ["model_name", "chip_family", "memory_gb", "storage_gb"],
  "variantAttrs": ["color"],
  "conditionAttrs": ["condition_grade"],
  "weights": {"chip_family": 0.25},
  "validFrom": "2026-04-25T10:00:00+08:00",
  "summary": {
    "lockingAttrCount": 4,
    "requiredAttrCount": 4,
    "isCurrent": true
  },
  "items": [
    {
      "attributeCode": "memory_gb",
      "role": "locking",
      "required": true,
      "weight": 0.15
    }
  ]
}
```

用途：

- 前端筛选器只允许 `role=locking` 的字段做等值筛选。
- 基线卡显示 `Schema vN · M locking attrs · valid_from 生效`。
- 详情页按 `locking / variant / condition / descriptive` 分组展示规格。

## 7. 高可用与降级

当前阶段不新增 Redis / RabbitMQ / Celery 基础设施，遵循最佳实践文档中“模块化单体优先”的原则。

本轮落地：

- active schema 从数据库读取。
- 读 API 可在无快照时从 active template 派生只读 fallback，避免旧数据阻塞页面。
- schema 不一致时 baseline 不静默换 schema；写入行必须携带 `schema_id`。
- 旧 baseline 通过迁移回填到对应类目的当前 v1/latest snapshot。

后续阶段：

- Redis baseline cache：5 分钟 TTL。
- enrichment queue：规格抽取和 baseline 重算异步解耦。
- baseline compute queue：按 `schema_id + fingerprint` 去重，10 分钟 debounce。
- 模式 B 回灌：近 90 天样本按新 schema 异步重建。

## 8. 验收标准

- 模板明细可声明 `role / weight / normalization / enumValues`。
- active schema 可通过 API 查询。
- `role=locking & is_required=true` 缺失的样本不进入 baseline 聚合。
- `buy_price_baseline` 持久化 `schema_id`。
- baseline 响应返回 schema 版本摘要。
- 模板发布或激活时生成 schema snapshot。
- 迁移能为已有类目和已有 baseline 回填 schema。
- 队列、Redis 和前端按钮作为后续 todo 明确排期，不伪装成本轮完成项。
