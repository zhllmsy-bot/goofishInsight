# 靠谱二手价格指导助手首批品类 `pricingKeyFields` 设计表

Status: Draft v1  
Updated: 2026-04-10  
Scope: Phase 0 首批四个业务域  
Related:

- [18-reliable-price-assistant-prd.md](<repo-root>/docs/18-reliable-price-assistant-prd.md)
- [19-reliable-price-assistant-technical-spec.md](<repo-root>/docs/19-reliable-price-assistant-technical-spec.md)
- [20-reliable-price-assistant-production-implementation.md](<repo-root>/docs/20-reliable-price-assistant-production-implementation.md)
- [21-reliable-price-assistant-production-todolist.md](<repo-root>/docs/21-reliable-price-assistant-production-todolist.md)

## 1. 文档目的

这份文档用于冻结首批四个业务域的：

- `pricingKeyFields`
- 必填字段
- 模板完整度规则
- `templateKey` 字段顺序
- 挂牌修正因素

这里的设计既参考产品目标，也参考当前现网 active template 的真实字段。

## 2. 总体规则

### 2.1 模板字段分层

每个品类的字段分成三层：

1. `pricingKeyFields`
   - 决定主价格模板
2. `supportingFields`
   - 帮助展示或解释，但不定义主价格模板
3. `listingAdjustmentFactors`
   - 只修正单条挂牌，不进入主价格模板

### 2.2 模板完整度规则

模板完整度按以下规则判断：

- `complete`
  - 所有 `requiredPricingFields` 都已解析
- `partial`
  - 至少命中型号，但关键字段未选满
- `missing`
  - 连模板主对象都无法确定

只有 `complete` 才可能进入 `guidance_ready / reference_only`。

### 2.3 `templateKey` 生成原则

`templateKey` 一律按：

`category_code + ordered pricingKeyFields`

稳定拼接。

字段顺序必须固定，不能让页面、job、baseline 自己随意换顺序。

## 3. Apple 电脑

### 3.1 当前 active template 现状

现网 active template 字段：

- `product_line`
- `model_name`
- `chip_family`
- `screen_size_in`
- `cpu_cores`
- `gpu_cores`
- `memory_gb`
- `storage_gb`

当前问题：

- 这些字段都被当成筛选字段，但还没有正式区分谁是价格字段、谁只是辅助字段
- `Mac mini / M4` 这种未选完整内存和硬盘的结果很容易混价

### 3.2 目标 `pricingKeyFields`

统一主字段：

- `model_name`
- `chip_family`
- `memory_gb`
- `storage_gb`

条件字段：

- `screen_size_in`
  - 当 `product_line in {MacBook Air, MacBook Pro, iMac}` 时纳入模板 key
- `cpu_cores`
- `gpu_cores`
  - 当同一 `model_name + chip_family + memory_gb + storage_gb` 下仍存在稳定多版本售价差时纳入模板 key

### 3.3 `requiredPricingFields`

默认必填：

- `model_name`
- `chip_family`
- `memory_gb`
- `storage_gb`

条件必填：

- `screen_size_in`
  - 对 `MacBook Air / MacBook Pro / iMac`

### 3.4 `templateKey` 顺序

默认顺序：

1. `model_name`
2. `screen_size_in`（如适用）
3. `chip_family`
4. `cpu_cores`（如适用）
5. `gpu_cores`（如适用）
6. `memory_gb`
7. `storage_gb`

### 3.5 `supportingFields`

- `product_line`
- `screen_size_in`（在不参与 key 的机型里作为展示字段）

### 3.6 `listingAdjustmentFactors`

- 成色
- 电池循环与健康
- 箱说票
- 保修状态
- 颜色
- 是否带键鼠/显示器/扩展配件
- 面交 / 异地邮寄

## 4. Garmin 手表

### 4.1 当前 active template 现状

现网 active template 字段：

- `product_line`
- `model_name`
- `generation`
- `display_type`
- `case_size_mm`
- `is_solar`
- `edition_tags`

当前问题：

- `edition_tags` 里混了 `Pro / Sapphire / Titanium / AMOLED` 等信息，语义过宽
- `model_name` 与 `generation` 之间存在信息重叠

### 4.2 目标 `pricingKeyFields`

统一主字段：

- `model_name`
- `case_size_mm`
- `is_solar`
- `display_type`

条件字段：

- `generation`
  - 当 `model_name` 不能稳定区分代际时纳入模板 key
- `edition_tags`
  - 只保留会显著影响价格的标准化 tag：
    - `Pro`
    - `Sapphire`
    - `Titanium`

### 4.3 `requiredPricingFields`

默认必填：

- `model_name`
- `case_size_mm`

条件必填：

- `display_type`
  - 当同型号存在 AMOLED / MIP 长期并存
- `is_solar`
  - 当同型号存在 Solar / Non-solar 长期并存

### 4.4 `templateKey` 顺序

1. `model_name`
2. `generation`（如适用）
3. `case_size_mm`
4. `display_type`（如适用）
5. `is_solar`（如适用）
6. `edition_tags`（仅保留价格敏感 tag）

### 4.5 `supportingFields`

- `product_line`
- `generation`
- 非价格敏感 `edition_tags`

### 4.6 `listingAdjustmentFactors`

- 成色
- 表带材质与原装性
- 蓝宝石玻璃/镜面状态
- 电池衰减
- 箱说票
- 国行 / 海外版
- 配件是否齐全

## 5. 相机机身

### 5.1 当前 active template 现状

现网 active template 字段：

- `brand_name`
- `model_name`
- `mount_system`
- `sensor_format`
- `pixel_resolution`
- `camera_type`
- `generation`

当前状态：

- 这套模板已经明显比 Apple / Garmin 更接近价格模板
- 主要问题在于 `generation` 与 `model_name` 可能重复表达

### 5.2 目标 `pricingKeyFields`

统一主字段：

- `brand_name`
- `model_name`
- `mount_system`
- `sensor_format`

条件字段：

- `generation`
  - 当市场上确实存在同名代际表达不稳定时纳入 key

### 5.3 `requiredPricingFields`

- `brand_name`
- `model_name`
- `mount_system`
- `sensor_format`

### 5.4 `templateKey` 顺序

1. `brand_name`
2. `model_name`
3. `generation`（如适用）
4. `mount_system`
5. `sensor_format`

### 5.5 `supportingFields`

- `pixel_resolution`
- `camera_type`

### 5.6 `listingAdjustmentFactors`

- 快门数
- 机身成色
- 维修史
- 包装与配件
- 电池数量
- 国行 / 保修
- 是否带套机镜头

## 6. 可换镜头

### 6.1 当前 active template 现状

现网 active template 字段：

- `brand_name`
- `model_name`
- `mount_system`
- `focal_length_type`
- `focal_length_range`
- `max_aperture`

当前状态：

- 这套模板已经可以直接作为价格模板 v1 使用
- `focal_length_type` 更适合作为辅助或条件字段

### 6.2 目标 `pricingKeyFields`

统一主字段：

- `brand_name`
- `model_name`
- `mount_system`
- `focal_length_range`
- `max_aperture`

条件字段：

- `focal_length_type`
  - 当变焦 / 定焦在表达层面不能从 `model_name + focal_length_range` 稳定推断时纳入 key

### 6.3 `requiredPricingFields`

- `brand_name`
- `model_name`
- `mount_system`
- `focal_length_range`
- `max_aperture`

### 6.4 `templateKey` 顺序

1. `brand_name`
2. `model_name`
3. `mount_system`
4. `focal_length_type`（如适用）
5. `focal_length_range`
6. `max_aperture`

### 6.5 `supportingFields`

- `focal_length_type`

### 6.6 `listingAdjustmentFactors`

- 镜片霉雾灰
- 对焦环 / 变焦环阻尼
- 遮光罩 / 箱说 / 包装
- 是否原厂三码合一
- 磨损痕迹
- 国行 / 店保

## 7. 首批落地建议

为了尽快把系统从“混价”拉回“模板价”，建议按以下顺序落实：

1. Apple 电脑
   - 先解决最明显的 `memory_gb / storage_gb` 混价问题
2. Garmin 手表
   - 先解决 `case_size_mm / is_solar / display_type` 混价问题
3. 相机机身
   - 以现网模板为主，少改字段，多补合同
4. 可换镜头
   - 以现网模板为主，补 `templateKey` 与趋势链路

## 8. 对当前代码的直接含义

这份设计表直接要求后续代码满足：

1. `dashboard_filters` 不再把所有 filter field 等同于 pricing field
2. `dashboard` 首页只有在 `requiredPricingFields` 选满后才显示价格指导
3. `buy_price_baselines` 不再只依赖 `view:label`
4. `buy_opportunities` 不再把 product fallback 冒充模板命中
5. 模板级趋势必须按当前设计表中的 `templateKey` 聚合

## 9. 待下一轮补充

这份设计表已足够支撑 Phase 1 和 Phase 2 的第一轮开发。

下一轮需要继续补：

- 每个字段的标准化值域
- `edition_tags` 价格敏感 tag 白名单
- Apple 条件字段何时纳入 `cpu_cores / gpu_cores`
- Garmin `generation` 与 `model_name` 的归一化规则
