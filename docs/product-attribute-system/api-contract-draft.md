# 商品属性系统接口契约草案

## 1. 目标

本文件用于把商品属性系统的关键写链路和读链路收敛成一套可实现的接口口径，减少后续服务开发阶段的反复返工。

当前定义为 HTTP JSON 风格草案，正式接入当前仓库的 FastAPI 路由时可再细化鉴权、中间件和错误码规范。

## 2. 通用约定

- 所有写接口建议携带 `request_id`
- 所有更新时间字段统一返回 ISO 8601
- 所有列表接口支持 `page`、`page_size`
- 响应结构建议统一为：

```json
{
  "code": "OK",
  "message": "success",
  "data": {}
}
```

## 3. 类目与属性模板

### 3.1 创建类目

`POST /api/v1/catalog/categories`

### 3.2 新增属性定义

`POST /api/v1/catalog/attributes`

### 3.3 创建模板草稿

`POST /api/v1/catalog/categories/{category_id}/templates`

### 3.4 发布模板

`POST /api/v1/catalog/templates/{template_id}/publish`

约束：

- 已发布模板不能原地编辑
- 再次修改必须创建新版本

## 4. 商品写链路

### 4.1 创建 SPU

`POST /api/v1/catalog/spus`

行为要求：

- 按模板校验必填属性
- 同步生成 `attr_snapshot_json`
- 同步写 `outbox_event`

### 4.2 批量创建 SKU

`POST /api/v1/catalog/spus/{spu_id}/skus/batch`

行为要求：

- 服务端按模板顺序生成 `sales_signature_raw`
- 服务端计算 `sales_signature_hash`
- `(spu_id, sales_signature_hash)` 冲突时报重复 SKU 错误

### 4.3 更新 SPU 属性

`PATCH /api/v1/catalog/spus/{spu_id}`

### 4.4 更新 SKU

`PATCH /api/v1/catalog/skus/{sku_id}`

## 5. 模板升级链路

### 5.1 发起 SPU 模板升级预检

`POST /api/v1/catalog/spus/{spu_id}/template-upgrades/preview`

### 5.2 生成 SPU 模板 replace 计划

`POST /api/v1/catalog/spus/{spu_id}/template-upgrades/replace-plan/preview`

行为要求：

- 当 `canAutoUpgrade = false` 时，尝试复用现有 SPU/SKU 属性生成 replace payload
- 明确返回：
  - `readyForReplace`
  - `missingRequiredSpuAttributeCodes`
  - `missingRequiredSkuAttributeCodes`
  - `ambiguousScopeChangeAttributeCodes`

### 5.3 执行 SPU 模板升级

`POST /api/v1/catalog/spus/{spu_id}/template-upgrades`

行为要求：

- 校验新模板
- 补齐新增必填属性
- 重算 `snapshot`
- 写入 `outbox_event`

### 5.4 执行 SPU 模板 replace 计划

`POST /api/v1/catalog/spus/{spu_id}/template-upgrades/replace-plan/apply`

行为要求：

- 仅在 `readyForReplace = true` 时允许执行
- 内部复用 `replace` 链路
- 重算 `snapshot`
- 写入 `outbox_event`

## 6. 读链路

### 6.1 分页查询 SPU

`GET /api/v1/catalog/spus`

建议支持：

- `category_id`
- `template_id`
- `merchant_id`
- `status`
- `title`
- `page`
- `page_size`

### 6.2 分页查询 SKU

`GET /api/v1/catalog/skus`

建议支持：

- `spu_id`
- `category_id`
- `template_id`
- `merchant_id`
- `status`
- `sku_code`
- `title`
- `page`
- `page_size`

### 6.3 查询 SPU 详情

`GET /api/v1/catalog/spus/{spu_id}`

### 6.4 查询 SKU 列表

`GET /api/v1/catalog/spus/{spu_id}/skus`

### 6.5 按类目筛选商品

`POST /api/v1/catalog/search`

约束：

- 该接口默认走搜索索引，不直接扫属性事实表

## 7. 错误码建议

- `CATALOG_TEMPLATE_REQUIRED_ATTR_MISSING`
- `CATALOG_SKU_DUPLICATE_SIGNATURE`
- `CATALOG_TEMPLATE_ALREADY_PUBLISHED`
- `CATALOG_TEMPLATE_UPGRADE_INCOMPATIBLE`
- `CATALOG_ATTRIBUTE_OPTION_DISABLED`
- `CATALOG_REQUEST_ID_CONFLICT`

## 8. 当前仓库已实现的内部工具接口

以下接口已经在当前仓库里作为内部工具入口落地，主要用于验证规则和打通实现链路：

### 8.1 预览接口

- `POST /api/catalog/tools/signature/preview`
- `POST /api/catalog/tools/snapshot/preview`
- `POST /api/catalog/tools/persist-plan/preview`

### 8.2 持久化工具接口

- `POST /api/catalog/tools/persist`
  - 请求体包含 `operatorId`、`dryRun`、`spu`、`spuAttributes`、`skus`
  - 当前默认建议走 `dryRun=true`
- `POST /api/catalog/tools/replace`
  - 请求体与 `/api/catalog/tools/persist` 相同
  - 但 `spu.id` 必填，用于原地替换同一个 `SPU`
- `POST /api/catalog/tools/template/persist`
  - 请求体包含 `operatorId`、`dryRun`、`category`、`attributes`、`template`
  - 主要用于初始化类目模板元数据
- `POST /api/catalog/tools/template-version/persist`
  - 请求体包含 `operatorId`、`dryRun`、`categoryId`、`template`
  - 主要用于给现有类目追加新模板版本

### 8.3 已实现的最小正式读接口

- `GET /api/catalog/spus`
- `GET /api/catalog/skus`
- `GET /api/catalog/templates/{template_id}`
- `GET /api/catalog/categories/{category_id}/templates`
- `GET /api/catalog/spus/{spu_id}`
- `GET /api/catalog/spus/{spu_id}/skus`
- `POST /api/catalog/spus/{spu_id}/template-upgrades/preview`
- `POST /api/catalog/spus/{spu_id}/template-upgrades/replace-plan/preview`
- `POST /api/catalog/spus/{spu_id}/template-upgrades/apply`
- `POST /api/catalog/spus/{spu_id}/template-upgrades/replace-plan/apply`

### 8.4 当前限制

- 当前是内部工具接口，不代表最终对外 API 形态
- 尚未补鉴权、中间件统一错误码封装和正式幂等表
- 商品持久化当前已支持 `create` 和 `replace`
- 模板持久化当前已支持初始化 `create` 和后续 `version create`
- 模板升级 `apply` 当前只支持 `preview.canAutoUpgrade = true` 的安全场景
- 如预检返回销售属性变化，可优先尝试 `replace-plan`
- 如 `replace-plan` 仍提示缺值或 scope 歧义，才需要手工补数据后再升级
