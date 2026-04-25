# Raw 类目 Onboarding TodoList

更新时间：2026-04-06

## 工作目标

- 把“关键词 -> 搜索结果 -> raw 类目识别 -> 属性模板创建 -> raw cate 映射 -> 动态抽取生效”做成正式链路
- 不再把 `business_domain` 当成真实商品品类
- 新增品类时，优先沉淀可复用的 SOP、命令和测试

## 执行节奏

- 先补 raw 类目信号落库，再做映射，不反过来
- 每做完一个闭环就补最小自检
- 运营动作要沉淀为 CLI 或文档，不留口头流程
- 设计上优先支持 Xianyu，但命名和分层尽量为后续平台扩展留空间

## A. 本轮主线

- [x] 输出“大类驱动配置与采集”总技术说明书

### A1. 数据基础

- [x] `Item` 落库 `xianyu_cat_id / xianyu_tb_cat_id / xianyu_c_cat_id`
- [x] Alembic migration 补齐新增列
- [x] 历史数据信号补录策略写入 backlog

### A2. 类目映射层

- [x] 新增 `xianyu_category_mapping` 表
- [x] 定义 `CAT / TB_CAT / CAT_TB / C_CAT` 匹配规则与优先级
- [x] 实现 `match_key` 生成与解析
- [x] 实现 `raw cate -> category/template` 的 upsert 服务
- [x] 补审计日志

### A3. Onboarding 工具链

- [x] 提供 raw 类目汇总命令
- [x] 输出每个 raw 类目的样本数、样本标题、映射状态
- [x] 提供 onboarding draft 自动生成命令
- [x] 提供 onboarding payload 持久化命令
- [x] 支持“新建 catalog 模板 + 建映射”一次完成
- [x] 提供 unmapped raw cate 持久化工作队列
- [x] 提供 queue sync / list / status update 命令

### A4. 抽取接入

- [x] specs 优先按 raw 类目映射加载模板
- [x] 未命中映射时回退既有 `business_domain` 蓝图
- [x] LLM prompt 注入 resolved template 元数据
- [x] 新增映射命中测试

### A5. 文档与验证

- [x] 更新 catalog / onboarding 文档
- [x] 补模型测试
- [x] 补服务测试
- [x] 补 CLI 测试
- [x] 跑最小回归测试集

### A6. 前端 Onboarding 页面

- [x] 落地 Xianyu onboarding 页面技术说明书
- [x] 新增 `/onboarding/xianyu` 页面入口
- [x] 暴露 coverage / queue 的 HTTP API
- [x] 页面支持 queue sync / status update
- [x] 页面展示 queue 详情与样本快照
- [x] 页面内接入 onboarding draft / persist 编辑器

## B. 本轮推进记录

### B1. 已完成

- [x] 明确生产主链从 `business_domain` 切回 `raw category`
- [x] 确认现有搜索结果已能拿到 `catId / tbCatId`
- [x] 确认 catalog 属性/模板持久化入口可复用
- [x] 新建本地 TodoList，作为本轮推进基线

### B2. 正在推进

- [x] `Item` 与 `xianyu_category_mapping` 的 schema 改造
- [x] raw 类目映射服务与 CLI
- [x] raw 类目样本 -> onboarding payload draft 自动生成
- [x] specs 模板解析改造
- [x] 历史 raw 类目信号补录
- [x] catalog backfill 对 raw 类目映射的正式接入
- [x] unmapped raw cate 工作队列落地
- [x] onboarding 页面最小闭环

## C. 历史数据 Backlog

- [x] 从 `RawResponse.response_body` 回填旧 `Item` 的类目信号
- [x] 基于真实类目覆盖率输出缺失报告
- [x] 为未命中映射的 raw 类目建立待办清单
- [x] 将 onboarding queue 暴露到 dashboard/admin 页面
- [x] 将 draft / persist 流程暴露到 onboarding 页面
- [x] 页面内支持 discovery collect，形成“关键词 -> 样本 -> draft -> persist”的完整闭环
- [x] 页面内增强枚举属性、候选 option 与英文 `attributeCode` 的人工修订体验（AI 草案默认摘要视图 + 可展开高级编辑，降低新增品类操作复杂度）
- [x] draft 支持识别 canonical family，并优先建议复用已有 `category/template`
- [x] 页面支持“复用现有大类模板”模式，落库时只创建 raw cate 映射

## D. 每轮执行模板

1. 从 TodoList 里取一个最小闭环
2. 改代码
3. 跑最小自检
4. 回写 TodoList 状态
5. 再进入下一个闭环
