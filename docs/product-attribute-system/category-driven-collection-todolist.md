# 大类驱动配置与采集 TodoList

更新时间：2026-04-12 21:45:00 CST

## 0. 总目标

- 把现有 `business_domain` 驱动链路迁移到“大类驱动”
- 让“配置页 -> 采集任务 -> specs -> 看板 -> 回填”全部围绕大类联动
- 把 `raw cate` 从主路由配置降级为辅助治理与漂移监控能力

## 1. Phase 1 基础设施

### 1.1 大类 runtime 配置

- [x] 新增 `category_runtime_profile` 表
- [x] `category` 增加 runtime profile 关系
- [x] `category_attr_template` 增加 active runtime profile 反向关系
- [x] 增加模型元数据测试
- [x] 增加 Alembic migration

### 1.2 大类型号库

- [x] 新增 `category_model_catalog` 表
- [x] 新增 `category_model_alias` 表
- [x] 增加模型元数据测试
- [x] 增加 Alembic migration

### 1.3 采集任务结构升级

- [x] `crawl_tasks` 增加 `category_id`
- [x] `crawl_tasks` 增加 `task_type`
- [x] `crawl_tasks` 增加 `profile_key`
- [x] `crawl_tasks` 增加 `parallel_tabs`
- [x] `crawl_tasks` 增加 `metadata_json`
- [x] 保留 `business_domain` 兼容镜像字段
- [x] 增加 Alembic migration

### 1.4 任务 query / lexicon 拆表

- [x] 新增 `crawl_task_query`
- [x] 新增 `crawl_task_lexicon`
- [x] 增加 Alembic migration
- [x] 增加基础 query/lexicon service

## 2. Phase 2 配置页

### 2.1 大类管理页

- [x] `/config/categories` 页面
- [x] 大类列表 API
- [x] 新建/编辑 API
- [x] 绑定 `active_template_id`
- [x] 绑定 `prompt_profile`

### 2.2 属性管理页

- [x] `/config/attributes` 页面
- [x] 属性列表/新增/编辑 API
- [x] 枚举值维护
- [x] 引用关系展示
- [x] 支持“通用属性（全类目自动注入 prompt）”开关，新增后立即生效

### 2.3 模板配置页

- [x] `/config/templates` 页面
- [x] 模板列表/详情 API
- [x] 模板编排 API
- [x] 模板发布 API
- [x] 模板差异预览
- [x] 模板页支持按 `categoryCode/status` 过滤
- [x] 模板详情展示 `items/options/runtime active` 摘要
- [x] 模板编排支持从属性池勾选属性并配置 `isRequired/isSale/isFilter/isSearch/isDisplay/sortNo`
- [x] 模板发布后可一键写回 `category_runtime_profile.active_template_id`
- [x] 模板差异预览输出 `added/removed/changed attributeCodes`

### 2.4 型号库页

- [x] `/config/models` 页面
- [x] 型号列表/新增/编辑 API
- [x] alias 维护 API
- [x] 批量导入导出
- [x] 型号页支持按 `categoryCode/status/brandName` 过滤
- [x] alias 正常化规则统一写入 `alias_normalized`
- [x] 导入导出优先走 JSON 文本，后续再补文件上传
- [x] 型号页显示被多少 alias 命中、最近更新时间

### 2.5 采集任务页

- [x] `/config/tasks` 页面
- [x] 任务列表/新增/编辑 API
- [x] query 列表维护 API
- [x] lexicon 维护 API
- [x] 任务绑定大类

### 2.6 raw cate policy 页

- [x] `/config/raw-cate-policy` 页面
- [x] policy 列表/新增/编辑 API
- [x] `BLOCK / FORCE_CATEGORY / FORCE_TEMPLATE / OBSERVE` 模式
- [x] `xianyu_category_mapping` 增加 `policy_mode`
- [x] `xianyu_category_mapping` 增加 `template_override_id`
- [x] raw cate policy 页支持样本标题、resolved category/template、candidate match keys 展示
- [x] raw cate policy 明确“默认走任务大类，raw cate 仅作 override/治理”

## 3. Phase 3 采集与解析切换

### 3.1 batch collect

- [x] batch collect 从数据库任务读 query 列表
- [x] batch collect 从数据库任务读 lexicon
- [x] `monitor_tasks.json` 降级为导入导出工具
- [x] discovery collect 改成复用任务配置
- [x] 风控命中后强制保留当前页面
- [x] `collect-batch` 优先读取 `crawl_task_query.pages/priority`
- [x] `collect-batch` 将命中的 query id 回写到 item/raw response 链路
- [x] 保留 `monitor_tasks.json` 兼容读取，但新增导入命令和导出命令
- [x] discovery collect 支持直接指定 `task_key`
- [x] 风控命中时停止自动切页/关页，只记录待人工解除状态

### 3.2 Item 入库

- [x] `items` 增加 `target_category_id`
- [x] `items` 增加 `resolved_category_id`
- [x] `items` 增加 `resolved_template_id`
- [x] `items` 增加 `task_query_id`
- [x] `items` 增加分类校验字段
- [x] 入库时按任务绑定的大类写入 `target_category_id`
- [x] item upsert 同步写 `resolved_template_id` 的初始默认值
- [x] raw response / item snapshot 链路带上 `task_query_id`
- [x] 为旧数据提供一次性 backfill 脚本
- [x] 为新字段补 SQLAlchemy 关系与测试

### 3.3 specs

- [x] `specs.py` 优先按 `resolved_category_id`
- [x] 按 `category_runtime_profile.prompt_profile` 选 prompt
- [x] 注入型号库 alias 词典
- [x] item-level 偏题校验输出 `category_validation_status`
- [x] `ItemSpecEnrichment` 增加 `category_id/template_id/model_catalog_id`
- [x] prompt builder 同时吃 `active_template + prompt_profile + model aliases`
- [x] item-level 偏题校验输出 `category_validation_reason/confidence`
- [x] 偏题时允许回退为 `needs_review`

### 3.4 raw cate policy

- [x] raw cate mapping 语义调整为 policy/override
- [x] 增加 `policy_mode`
- [x] 增加 `template_override_id`
- [x] specs/runtime 消费 override
- [x] `FORCE_CATEGORY` 优先覆盖 `resolved_category_id`
- [x] `FORCE_TEMPLATE` 优先覆盖 `resolved_template_id`
- [x] `BLOCK` 直接标记分类校验失败并跳过 specs
- [x] `OBSERVE` 仅记告警不改主路由

## 4. Phase 4 看板与分析切换

### 4.1 dashboard / filters

- [x] `dashboard_filters.py` 改按 `category.code`
- [x] 过滤布局从大类 runtime 配置读取
- [x] 清理 `if business_domain == "garmin"/"apple_m_series"` 分支
- [x] dashboard summary API 输出 `categoryCode/categoryName`
- [x] 前端筛选项支持大类和型号联动

### 4.2 pricing / metrics

- [x] `daily_metrics` 增加 `category_id / model_id`
- [x] `model_scores` 增加 `category_id / model_id`
- [x] pricing 聚合逻辑改按大类/型号
- [x] 旧唯一键升级为 `date + category_id + model_id`
- [x] 保留 `business_domain` 兼容只读字段一段过渡期

### 4.3 catalog backfill

- [x] backfill 主链改按 `resolved_category_id / resolved_template_id`
- [x] 移除对 legacy blueprint 的强依赖
- [x] backfill 对 runtime profile 缺失给出清晰错误
- [x] backfill 支持 raw cate override 模板

### 4.4 报告与触达

- [x] `analysis_reports` 增加 `category_id / template_id`
- [x] `outreach_records` 增加 `category_id / model_id`
- [x] 报告生成默认按 category 维度聚合
- [x] 外呼记录支持回写命中的 canonical model

## 5. Phase 5 收尾

- [x] 提供 `monitor_tasks.json -> 数据库任务` 导入命令
- [x] 提供旧 `business_domain -> category_id` 回填脚本
- [x] 提供兼容字段清理计划
- [x] 补全端到端回归
- [x] 更新 SOP / 使用文档
- [x] 增加 category-driven smoke checklist
- [x] 更新 resident collect/review 运行说明

## 6. 当前连续执行顺序

1. dashboard filter runtime profile 化
2. 移除剩余 legacy `business_domain` 分支
3. 报告 category 维度聚合
4. 兼容字段清理计划
5. 端到端回归

## 7. 已额外完成

- [x] 既有 Apple/Garmin 大类语义纠偏为 `apple_computer / garmin_watch`
- [x] 已为 `apple_computer / garmin_watch / camera_interchangeable_lens / phone` 回填 runtime profile
- [x] 已为历史 `crawl_tasks` 回填 `category_id`
- [x] 数据库已升级到 `20260407_0018`
- [x] dashboard 已热重启并加载 category-driven 改造
- [x] 已新增 `category-driven-smoke-checklist.md`
- [x] 已新增 `category-driven-ops-guide.md`
- [x] 已新增 `category-driven-compat-cleanup-plan.md`
- [x] review/progress 查询、导出、日志聚合统一按 canonical category 过滤与展示
- [x] catalog backfill 批量预览改为 `mapping/resolved_template` 优先，`business_domain` 仅作为兼容筛选范围
- [x] catalog backfill 新增 runtime profile active template 目标解析（legacy blueprint 仅保留兼容兜底与种子场景）
- [x] category-driven 回归集（配置/采集/specs/pricing/dashboard/review/backfill）105 项测试通过
- [x] seed-task / home-feed / mobile-market / price-backfill / review-calibration 关键入口统一采用 canonical category 兼容过滤（legacy business_domain 仅作兼容别名）
- [x] 代码主链已清理掉 `Item/CrawlTask.business_domain ==` 的硬编码等值过滤与 `if business_domain ==` 分支（保留兼容 alias in_ 过滤）

## 8. 2026-04-12 首页 Feed Category Entry 补强

- [x] 首页 feed 改为 `webpc.feed/1.0` 接口优先，DOM 仅作 fallback
- [x] feed 卡片透传 `categoryId/tbCatId/cCatId`
- [x] 首页 feed 先走 `xianyu_category_mapping -> internal category`
- [x] 新 item 仅在 raw cate 已映射到内部大类时进入首页 feed 局部 entry
- [x] 局部 entry 复用 item upsert，并在新 item 上同步落一份 `allow_llm=False` 的本地 specs enrichment
- [x] 首页私聊默认文案改为“你好，请问，价格还有空间吗？”
- [x] 首页私聊不再依赖 `safe_price`，但继续保留“仅非商家（private_like）可私聊”的门槛
- [x] 已存在 item 且未问过时，直接走详情页 + 页面私聊
- [x] 详情入口改为 `item_id + category_id` 直接拼 URL 开新 tab，不再依赖点击列表卡片
- [x] API-first 在 attached browser 首页已加载完成的情况下，补了自动 reload 一次再抓 response 的兜底
- [x] 新 item 在存在 mapped domain 时，只允许在 mapped domain 内做匹配与 entry，避免被其他 domain 的 lexicon fallback 抢走

## 9. 本轮 smoke 后的剩余观察

- [ ] `skipped_unmapped_category_count` 仍偏高，说明 raw cate 映射覆盖率还不够，后续需要补更多首页常见 cate 的 mapping
- [ ] `camera_body` 的本地 rule specs 仍未正式支持，当前新机身若只靠 `allow_llm=False` 局部 entry，结构化结果容易落到 `unresolved`
- [ ] 首页 feed 当前已能稳定做到 `api_card_count` 级别采集，但 `home_tab_switch.available` 偶发为空，说明首页 tab DOM 探测还可以再稳一刀
