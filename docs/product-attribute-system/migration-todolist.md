# Catalog 迁移 TodoList

更新时间：2026-04-05

## 工作节奏

- 先列完整 todo，再逐项执行
- 每完成一项，立即跑对应自检
- 自检结果如果暴露新问题，先更新 todo，再继续
- 每个可复用阶段都要落文档、命令或测试
- 每轮里程碑总结同步推到 OpenViking

## A. 已完成

### A1. 基础模型与表结构

- [x] 设计 `category / template / attribute / spu / sku / value / outbox / audit`
- [x] 补齐 Alembic 迁移
- [x] 在 `.4` 开发库执行到 `20260405_0008`

### A2. 核心写链路

- [x] `persist`
- [x] `replace`
- [x] 模板初始化
- [x] 模板版本发布
- [x] `snapshot` 同步写入
- [x] `outbox_event` 写入
- [x] 审计日志写入

### A3. 查询与升级链路

- [x] SPU 详情
- [x] SKU 列表
- [x] 模板详情
- [x] 类目模板版本列表
- [x] SPU 分页
- [x] SKU 分页
- [x] 模板升级预检
- [x] 模板自动升级
- [x] replace-plan 预览与 apply

### A4. 运维与自检

- [x] outbox consumer
- [x] `check-catalog-migration`
- [x] `check-catalog-scoped-migration`
- [x] smoke SOP
- [x] `.4` 开发库真实链路验证

## B. 本轮推进记录

### B1. 目标模板 bootstrap 与单条 apply dry-run

- [x] 生成 `garmin` 目标类目/模板 payload
- [x] 生成 `apple_m_series` 目标类目/模板 payload
- [x] 将目标模板 apply 到 `.4` 开发库
- [x] 选一条 enriched item 做单条 persist dry-run
- [x] 明确首批 apply 的幂等与回滚策略

### B2. 当前正在推进

- [x] 按 `enriched-only + skip-existing` 制定首批 batch apply 列表
- [x] 对 Apple / Garmin 各跑一批真实 batch apply
- [x] 消费 outbox 并复核 SPU / SKU 列表
- [x] 形成首批 backfill 对账快照

### B3. 下一阶段

- [x] 扩大 batch apply 范围
- [x] 定义正式对账口径
- [x] 产出差异修复清单
- [x] 对 Apple / Garmin 完成域级 apply

## B.1 本轮刚完成

### B1.1 单条旧表映射与预览

- [x] 盘点旧源表 `items + item_spec_enrichments`
- [x] 定义 `garmin -> catalog` 映射
- [x] 定义 `apple_m_series -> catalog` 映射
- [x] 形成单条 backfill preview 输出
- [x] 选真实样本做 dry-run

### B1.2 批量 preview 与候选筛选

- [x] 按 `business_domain` 拉取候选 item
- [x] 输出批量 preview 列表
- [x] 汇总 warning 分布
- [x] 增加 `--enriched-only` 过滤
- [x] 为 apply 前筛出高质量候选集

## C. 本轮已收口

### C1. Backfill 工具链

- [x] 单条历史 item -> catalog payload draft
- [x] 批量 backfill preview
- [x] 批量 backfill dry-run
- [x] 批量 backfill apply
- [x] apply 后标准自检
- [x] backfill 失败重试与跳过策略

### C2. 新旧对账

- [x] 定义对账口径
- [x] 样本对账
- [x] 按 business_domain 对账
- [x] 差异分类与修复清单

### C3. 本轮迁移结项

- [x] `apple_m_series` enriched item 迁移完成
- [x] `garmin` enriched item 迁移完成
- [x] `.4` 开发库 reconciliation 覆盖率达到 `1.0`
- [x] `pendingOutboxTotal = 0`
- [x] 仓库文档、SOP、OV 总结同步收口

## D. 后续增强 Backlog

### D1. 搜索与消费链路

- [ ] catalog outbox 对接真实搜索索引
- [ ] 建立 consumer 幂等与补偿
- [ ] 重放与重建 SOP

### D2. 正式业务接入

- [ ] 正式 API 鉴权
- [ ] 统一错误码
- [ ] 幂等记录
- [ ] 接入业务入口而不只停留在 admin/tooling

### D3. 非 enriched 数据与生产切流

- [ ] 非 enriched 历史数据降级映射策略
- [ ] 阶段 A 影子写入验证
- [ ] 阶段 B 详情灰度读
- [ ] 阶段 C 新模型接管
- [ ] 回滚演练
- [ ] 生产值班 SOP

## E. 每轮执行模板

1. 从 TodoList 里只取一个最小闭环任务
2. 实现代码或文档
3. 运行最小自检
4. 根据结果更新 TodoList 和状态文档
5. 推送里程碑总结到 OpenViking
