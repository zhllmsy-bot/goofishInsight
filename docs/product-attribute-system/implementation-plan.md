# 商品属性系统实施计划

## 1. 当前落点

本轮修正后，商品属性系统相关文档和参考实现已经回到 `goofish-insight` 仓库内。

当前“开始实施”的含义是：

- 在仓库内固定方案文档
- 输出 PostgreSQL DDL 草案
- 输出可执行的分阶段实施计划
- 输出 Python 参考实现和测试

## 2. 分阶段实施

### Phase 0：设计定稿

- 评审本方案文档
- 评审 DDL 草案
- 评审 Python 参考实现中的 SKU 签名与快照规则
- 明确承载商品域的真实模块和边界
- 明确 API 契约与权限模型

### Phase 1：数据库模型

- 落正式迁移脚本
- 建立类目、属性定义、模板、SPU、SKU、属性值表
- 建立审计表和 outbox 表
- 补数据库约束与索引

### Phase 2：商品写链路

- 将参考实现中的签名规则迁入正式服务
- 新增类目模板发布能力
- 新增商品创建与编辑能力
- 同步生成 `snapshot`
- 同步写入 `outbox_event`

### Phase 3：搜索与读链路

- 构建详情页读 `snapshot` 路径
- 构建搜索索引消费者
- 增加失败重试和重建能力

### Phase 4：迁移旧宽表

- 梳理旧字段映射
- 回填新模型
- 建立新旧对账任务
- 灰度切读
- 正式切流

## 3. 当前建议的下一步

1. 在开发数据库执行 catalog Alembic 迁移并验证 `db-current`
2. 先用 `persist-catalog-template-payload --dry-run/--apply` 建立一份最小模板元数据
3. 再用 `persist-catalog-payload --dry-run/--apply` 跑通一条最小 SPU/SKU 写链路
4. 接正式业务鉴权、请求幂等和 outbox consumer
5. 补正式读接口和搜索索引同步
