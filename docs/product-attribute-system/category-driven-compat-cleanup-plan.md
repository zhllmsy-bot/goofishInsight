# Category-Driven Compatibility Cleanup Plan

更新时间：2026-04-07 01:25:00 CST

## 目标

把运行主链从 `business_domain` 兼容字段彻底收敛到：

- `category_id`
- `resolved_category_id`
- `resolved_template_id`
- `model_catalog_id`

## 当前保留兼容的地方

- `crawl_tasks.business_domain`
- `items.business_domain`
- `item_spec_enrichments.business_domain`
- dashboard/pricing/review 中少量 `business_domain` 判断分支
- `monitor_tasks.json` 里的 `business_domain`

## 退场顺序

### Phase A

- 所有新逻辑继续优先写 `category_id / resolved_*`
- `business_domain` 只作为只读镜像
- 新 API 返回同时带 `categoryCode` 和旧 `business_domain`

### Phase B

- dashboard filter layout 改为 runtime profile 驱动
- 清掉 `if business_domain == "garmin"/"apple_m_series"` 分支
- review/pricing 改成 `category_code + prompt_profile` 判断

### Phase C

- `monitor_tasks.json` 只保留导入导出，不再要求人工维护 `business_domain`
- 配置页默认隐藏 `business_domain`
- CLI 帮助文案改成优先展示 `category_code`

### Phase D

- 当所有 runtime/query/dashboard/reporting 都稳定后：
  - 停止新增写入 `business_domain`
  - 评估是否保留字段仅作历史审计
  - 或迁移为 `legacy_business_domain`

## 判定标准

满足下面条件后才进入真正删兼容阶段：

- dashboard 和 pricing 已不再依赖 `business_domain`
- review/calibration 已不再依赖 `business_domain`
- collect/discovery/export/import 已以 `category_id` 为主
- 至少一轮生产数据验证 `resolved_category_id / resolved_template_id` 覆盖稳定
