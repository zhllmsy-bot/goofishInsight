# Xianyu 新品类 Onboarding 页面技术说明书

更新时间：2026-04-06 15:41:00 CST

## 1. 背景与目标

当前系统已经具备以下能力：

- 搜索采集阶段可保存 `xianyu_c_cat_id / xianyu_cat_id / xianyu_tb_cat_id`
- 可按 raw cate 汇总样本、生成 coverage report
- 可把 raw cate 同步成持久化 onboarding queue
- 可基于真实样本自动生成 `attribute + template + mapping` 草稿
- 可持久化 catalog 模板与 raw cate 映射
- `specs` 与 `catalog_backfill` 都已优先按 raw cate mapping 解析模板

但当前运营入口主要仍是 CLI，缺少一套可视化的人机协同页面来完成“发现新品类、审核属性、确认模板、正式上线”的完整闭环。

本说明书定义一个前端页面方案，用于把新品类 onboarding 过程收敛成标准化生产流程。

## 2. 关键产品原则

### 2.1 页面负责交互，后端负责执行

前端页面只负责：

- 输入关键词
- 选择 raw cate
- 展示模型候选属性
- 审核勾选与编辑
- 确认后触发正式持久化

真正的搜索、分析、模板生成、映射写入都由后端服务执行。

### 2.2 品类与模板是固定配置，不是自由动态生成

生产上应以固定模板为主：

- `raw cate -> template_id`
- `template_id -> template schema`
- `template_id -> prompt_profile`

运行时只做一层轻量渲染：

- 用固定 prompt 骨架
- 注入模板定义里的属性列表、枚举值、输出字段约束

不采用“每个模板存一整段自由 prompt 文本”的方式作为主路径。

### 2.3 中文展示，英文落库

模型和运营审核更适合看中文字段名；
系统内部需要稳定英文 `attributeCode`。

因此页面应同时管理：

- `name`：中文展示名
- `code`：英文系统名

英文 code 生成策略：

1. 先走内置字典/规则
2. 无命中时由模型推荐 `snake_case`
3. 页面允许人工修正
4. 一旦落库后固定复用

## 3. 标准工作流

完整工作流定义为：

`关键词输入 -> 小样本搜索 -> raw cate 分桶 -> queue/coverage -> 选择目标 raw cate -> 样本送模型抽属性 -> 页面审核属性 -> 确认创建 category/template/mapping -> 上线后 specs/backfill 自动消费`

拆成页面动作如下：

1. 输入关键词，触发 discovery collect 或读取已有 discovery 结果
2. 页面展示 raw cate 分组结果与覆盖率
3. 选择一个待开通 raw cate
4. 后端基于该 raw cate 的样本生成属性草稿
5. 页面展示候选属性：
   - 中文名
   - 英文 code
   - 数据类型
   - `SPU / SKU / SALE`
   - 是否多值
   - 命中率
   - 样例值
6. 运营勾选有效属性并修正：
   - 是否保留
   - 类型
   - 中文名
   - 英文 code
   - 枚举值
   - 是否必填
   - 是否销售属性
   - 是否筛选/搜索/展示
7. 确认后，后端创建：
   - `attribute_definition`
   - `category`
   - `category_attr_template`
   - `xianyu_category_mapping`
8. queue 项自动标记为 `RESOLVED`
9. 该 raw cate 的后续商品自动进入生产链路

## 4. 页面范围

## 4.1 已落地范围（Phase 1 + Phase 2）

当前页面已经覆盖：

- 页面内直接发起 discovery collect
- 页面入口
- coverage 概览
- onboarding queue 列表
- queue 的 `sync / list / status update`
- 选中 queue 项后可查看样本信息
- 页面内生成 onboarding draft
- 页面内编辑属性与模板草稿
- 页面内执行 persist dry-run
- 页面内正式创建 category / template / mapping

当前目标是把“待办发现 -> 属性审核 -> 模板创建”这段主流程从 CLI 提升到页面。

## 4.2 下一阶段范围（Phase 3）

- queue 自动完成从 discovery 到 persist 的整段闭环
- 中文属性名到英文 `attributeCode` 的候选生成与人工修订增强
- 枚举属性与候选 option 的页面化编辑

## 4.3 后续范围（Phase 4）

- `prompt_profile` 可视化配置
- 模板版本升级页面
- raw cate 合并/拆分治理
- onboarding 历史审计与操作日志页

## 5. 后端能力设计

### 5.1 已有能力

已有服务：

- `build_xianyu_raw_category_summary(...)`
- `build_xianyu_raw_category_coverage_report(...)`
- `sync_xianyu_category_onboarding_queue(...)`
- `list_xianyu_category_onboarding_queue(...)`
- `update_xianyu_category_onboarding_queue_status(...)`
- `build_xianyu_category_onboarding_draft(...)`
- `persist_xianyu_category_onboarding(...)`

### 5.2 当前 Web API

建议新增独立的 onboarding 页面与 API，而不是把逻辑塞进首页 dashboard sections。

建议路由：

- `GET /onboarding/xianyu`
  - 返回页面模板
- `GET /api/onboarding/xianyu/coverage`
  - 返回 raw cate coverage report
- `GET /api/onboarding/xianyu/queue`
  - 返回 onboarding queue 列表
- `POST /api/onboarding/xianyu/queue/sync`
  - 同步 queue
- `POST /api/onboarding/xianyu/queue/status`
  - 更新 queue 状态
- `POST /api/onboarding/xianyu/discovery`
  - 页面内直接发起 discovery collect，并回填后续 raw cate 汇总所需样本
- `POST /api/onboarding/xianyu/draft`
  - 基于选中 raw cate 的真实样本生成 onboarding 草稿
- `POST /api/onboarding/xianyu/persist`
  - 执行 dry-run 或正式创建 `category / template / mapping`

## 6. 页面结构设计

建议新增独立页面：`/onboarding/xianyu`

页面布局分为四块：

### 6.1 Hero / 控制区

展示：

- 页面目的
- 当前流程说明
- operator id 输入
- source keyword 输入
- `sync queue` 按钮
- `refresh` 按钮

### 6.2 Coverage 概览区

展示：

- 总 item 数
- 有 raw response 的 item 数
- 有 raw cate signal 的 item 数
- 完整 raw cate signal 的 item 数
- backfill candidate 数
- raw signal 覆盖率

### 6.3 Queue 列表区

表格字段：

- status
- raw cate
- item_count_snapshot
- source_keywords
- business_domains
- sample_titles
- owner_operator_id
- updated_at

支持动作：

- 标记 `IN_PROGRESS`
- 标记 `IGNORED`
- 恢复 `PENDING`

### 6.4 右侧详情区（本期可先做只读）

选中 queue 项后展示：

- raw cate ids
- candidate match keys
- sample item ids
- sample titles
- 当前 resolved mapping（如果有）
- 当前状态与备注

## 7. 数据模型约束

本期已新增持久化表：

- `xianyu_category_onboarding_queue`

状态机约束：

- `PENDING`
  - 新发现待处理
- `IN_PROGRESS`
  - 已认领，正在编辑/审核
- `RESOLVED`
  - 已建立 mapping
- `IGNORED`
  - 暂不处理

自动状态变更规则：

- queue sync 时若发现映射已存在，则自动变为 `RESOLVED`
- 持久化 onboarding 成功后，命中的 queue 必须自动变为 `RESOLVED`
- 若原先 `RESOLVED` 的 raw cate 失去映射，则可重新打开为 `PENDING`

## 8. Prompt 与模板策略

页面最终不是直接编辑 prompt 文本，而是编辑结构化模板。

生产使用如下映射关系：

- `raw cate -> template_id`
- `template_id -> prompt_profile`

模板中存储：

- 属性定义
- 模板项定义
- 显示/搜索/筛选/销售属性标记
- 枚举选项
- 可选的 `prompt_profile`

代码中存储：

- prompt builder 骨架
- prompt profile 版本
- 通用输出 JSON 外壳

运行时：

1. 根据 raw cate 找模板
2. 根据模板找 `prompt_profile`
3. 按模板渲染 prompt 中的属性列表与输出约束
4. 模型输出按 `attributeCode` 回填

## 9. 中文字段与英文 code 生成

### 9.1 页面展示

页面优先展示中文字段名，便于运营审核。

### 9.2 系统落库

系统必须保存稳定英文 code。

推荐流程：

1. 模型先产出中文字段候选
2. 后端对候选做 code 推荐
3. 页面允许人工改 code
4. 落库后 code 固定

### 9.3 code 规则

- 全小写
- `snake_case`
- 避免中文拼音作为默认主路径
- 优先复用已有 canonical code

示例：

- 品牌 -> `brand_name`
- 产品线 -> `product_line`
- 型号 -> `model_name`
- 芯片系列 -> `chip_family`
- 内存 -> `memory_gb`
- 存储 -> `storage_gb`
- 电池健康度 -> `battery_health`

## 10. 风险与防错

### 10.1 不按 raw cate 分桶直接抽属性

风险：

- 多类目混成一个模板

规避：

- 必须先按 raw cate 分桶，再选定单个桶做草稿

### 10.2 全自动上线新品类

风险：

- 模板错误会污染抽取与回填链路

规避：

- 维持“自动草拟 + 人工确认 + 正式持久化”

### 10.3 每个模板维护独立完整 prompt 文本

风险：

- 升级困难
- 模板漂移严重

规避：

- 改为 `template_id -> prompt_profile`
- prompt 文本由统一 builder 渲染

## 11. 实施 Todo

### Phase 1

- [ ] 新增 `/onboarding/xianyu` 页面
- [ ] 新增 onboarding queue HTTP API
- [ ] 页面展示 coverage + queue list
- [ ] 页面支持 queue sync
- [ ] 页面支持 queue 状态更新
- [ ] 补前端页面回归测试或最小 smoke 检查

### Phase 2

- [ ] 页面支持基于 raw cate 直接生成 onboarding draft
- [ ] 页面支持属性勾选与编辑
- [ ] 页面支持正式 persist onboarding
- [ ] 页面支持自动 resolve queue

### Phase 3

- [ ] 页面支持 `prompt_profile` 展示与配置
- [ ] 页面支持模板版本升级
- [ ] 页面支持 onboarding 操作审计

## 12. 当前执行结论

当前推荐执行顺序：

1. 先交付 Phase 1 的 queue 页面
2. 再接 draft 编辑器
3. 最后再把 persist 和 prompt_profile 配置挂进去

也就是说，本轮开发应先把“发现待办 + 推进待办”的前端入口做出来，不先做复杂模板编辑器。
