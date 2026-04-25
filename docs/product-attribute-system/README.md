# 商品属性系统技术方案 v3

## 1. 文档定位

本方案用于指导商品属性系统从“单宽表 + 每加新品类就改表”演进为“通用主表 + 类目模板 + 属性值事实表”的可扩展模型。

本版结论：

- 可以作为生产详细设计基线推进研发
- 不能直接替代最终上线包
- 上线前仍需补齐 DDL 定稿、接口契约、迁移脚本和灰度演练记录

## 2. 目标与边界

### 目标

- 新增品类时原则上不改商品主表
- 支持不同品类拥有不同属性集合
- 支持 SPU / SKU 分层
- 支持模板版本演进
- 支持详情、编辑、搜索三类读路径

### 非目标

- 当前阶段不优先做数据库分片
- 当前阶段不处理跨区域多活
- 当前阶段不支持“多选销售属性”与“自由文本销售属性”

## 3. 总体设计

系统采用“元数据驱动”的商品模型：

- 通用高频字段保留在主表
- 品类专属字段沉到属性定义和属性值表
- 类目通过模板声明可用属性、必填规则和销售属性
- 商品保存时同步生成属性快照
- 搜索索引异步更新

## 4. 核心数据模型

### 4.1 类目与模板

- `category`
  - 类目树
- `attribute_definition`
  - 属性定义中心
- `attribute_option`
  - 枚举型属性可选项
- `category_attr_template`
  - 类目模板头，支持版本
- `category_attr_template_item`
  - 模板明细，定义属性是否必填、是否销售属性、是否筛选项

### 4.2 商品主体

- `product_spu`
  - 商品公共信息
- `product_sku`
  - 可售卖单元

### 4.3 属性值事实表

- `product_spu_attr_value`
  - SPU 级属性值
- `product_sku_attr_value`
  - SKU 级属性值

### 4.4 支撑表

- `outbox_event`
  - 异步一致性事件表
- `product_attr_audit_log`
  - 属性与模板操作审计

## 5. 关键设计约束

### 5.1 SKU 唯一性规范

- `v1` 仅允许单选枚举型销售属性
- 每个 `SPU` 创建时绑定一份模板
- 模板中 `is_sale = true` 的属性构成销售属性全集
- 每个 `SKU` 对每个销售属性必须恰好选择一个值
- `sales_signature` 生成规则：
  - 按模板 `sort_no` 升序
  - 再按 `attribute_id` 升序兜底
  - 拼接形如 `12:101|15:208|19:307`
- `product_sku` 用 `(spu_id, sales_signature_hash)` 做唯一约束
- 接口写入必须携带 `request_id` 保障幂等

### 5.2 模板版本绑定规则

- `SPU` 创建时必须绑定 `template_id`
- 历史 `SPU` 默认一直按创建时模板解释
- 类目发布新模板后，只影响新建商品
- 老商品升级模板必须走显式升级流程
- 新模板新增必填属性，不自动影响历史 `SPU`

### 5.3 属性值约束

- 单值属性只允许一行，`value_seq = 0`
- 多值属性允许多行，`value_seq` 递增
- 同一行只允许一个主值列非空
- 枚举属性只存 `option_id`
- 数值属性可同时存 `number_value` 和 `normalized_number_value`

## 6. 读写链路

### 6.1 写入链路

商品保存事务内必须同时完成：

1. 写入 `SPU`
2. 写入 `SPU` 属性值
3. 写入 `SKU`
4. 写入 `SKU` 属性值
5. 更新 `attr_snapshot_json`
6. 写入 `outbox_event`

### 6.2 一致性规则

- 数据库规范化表与 `snapshot` 强一致
- 搜索索引最终一致
- 搜索更新走 `outbox -> consumer`
- 消费端必须按 `event_id` 或 `(aggregate_id, event_version)` 幂等
- 必须支持按 `SPU`、类目、时间段重建索引

## 7. 双写迁移口径

### 阶段 A

- 旧宽表为唯一真相源
- 新模型做影子写入和校验

### 阶段 B

- 详情页灰度读新 `snapshot`
- 后台编辑和核心交易仍以旧表为准

### 阶段 C

- 新模型成为唯一真相源
- 旧宽表转兼容输出或只读备份

### 回滚原则

- 任一灰度阶段允许切回旧读路径
- 新模型正式接管前，不删除旧字段

## 8. 命名空间与多租户

如果未来需要支持平台级与商家级属性共存，`attribute_definition.code` 不建议做全局唯一，建议唯一约束采用：

- `(scope_type, scope_id, code)`

推荐预留：

- `scope_type`: `platform` / `merchant` / `channel`
- `scope_id`

当前单租户场景可统一写为 `platform`

## 9. 生命周期治理

### 属性定义状态

- `draft`
- `active`
- `deprecated`
- `disabled`

### 模板状态

- `draft`
- `published`
- `retired`

约束：

- 已发布模板不原地修改，只能发新版本
- 枚举选项只允许停用，不允许物理删除
- 历史商品引用已停用选项时允许展示，不允许新写入
- 所有模板、属性和值变更必须进审计日志

## 10. 上线前验收清单

- 新增品类、新增属性、新发模板不需要修改商品主表
- 同一 `SPU` 下重复销售属性组合无法创建第二个 `SKU`
- 模板升级后历史 `SPU` 仍可正常展示和编辑
- 商品保存后 `snapshot` 立即可读且与规范化表一致
- 搜索消费失败时可重试、补偿和重建
- 双写期间新旧数据对账达标后才允许切流
- 停用属性与停用选项不会破坏历史商品展示

## 11. 当前仓库落地方式

本仓库当前使用 Python/FastAPI/SQLAlchemy 栈，因此后续实现优先对齐当前工程结构：

- 方案主文档
- PostgreSQL DDL 草案
- 分阶段实施说明
- API 契约草案
- Python 参考实现与测试

## 12. 可执行参考实现

为避免只停留在纸面设计，当前已补充一层独立于框架的 Python 参考实现：

- `apps/collector/src/goofish_insight/domain/catalog/contracts.py`
  - 销售属性校验
  - `sales_signature` 生成与哈希
  - 商品属性快照构建
- `apps/collector/tests/test_catalog_contracts.py`
  - `unittest` 覆盖

## 13. 当前已落地入口

当前仓库内已经有一组“工具级” HTTP/CLI 入口，可用于先验证规则、再逐步接正式业务接口。

### 13.1 HTTP 工具入口

- `POST /api/catalog/tools/signature/preview`
  - 预览销售属性签名
- `POST /api/catalog/tools/snapshot/preview`
  - 预览商品快照
- `POST /api/catalog/tools/persist-plan/preview`
  - 预览未来写库计划
- `POST /api/catalog/tools/persist`
  - 调用真实持久化 service，默认支持 `dryRun`
- `POST /api/catalog/tools/replace`
  - 按同一个 `spu_id` 替换 SPU 属性和 SKU 集合，默认支持 `dryRun`
- `POST /api/catalog/tools/template/persist`
  - 初始化类目、属性、模板元数据，默认支持 `dryRun`
- `POST /api/catalog/tools/template-version/persist`
  - 为已有类目发布新模板版本，默认支持 `dryRun`

### 13.2 HTTP 读入口

- `GET /api/catalog/spus`
  - 按 `categoryId/templateId/merchantId/status/title` 分页查询 SPU
- `GET /api/catalog/skus`
  - 按 `spuId/categoryId/templateId/merchantId/status/skuCode/title` 分页查询 SKU
- `GET /api/catalog/templates/{template_id}`
  - 查询模板明细和属性选项
- `GET /api/catalog/categories/{category_id}/templates`
  - 查询类目下全部模板版本和当前最新模板
- `GET /api/catalog/spus/{spu_id}`
  - 查询 SPU、SPU 属性、SKU 和快照
- `GET /api/catalog/spus/{spu_id}/skus`
  - 查询某个 SPU 下的 SKU 列表
- `POST /api/catalog/spus/{spu_id}/template-upgrades/preview`
  - 预检目标模板是否需要补属性、是否必须重写 SKU
- `POST /api/catalog/spus/{spu_id}/template-upgrades/replace-plan/preview`
  - 为不兼容模板升级生成 replace 计划，尽量复用现有属性值
- `POST /api/catalog/spus/{spu_id}/template-upgrades/apply`
  - 仅当 `canAutoUpgrade = true` 时直接切模板并写出 outbox
- `POST /api/catalog/spus/{spu_id}/template-upgrades/replace-plan/apply`
  - 对 replace 计划直接走 `dryRun/apply`，适合 `canAutoUpgrade = false` 但 `readyForReplace = true` 的场景

### 13.3 CLI 工具入口

- `list-catalog-spus`
- `list-catalog-skus`
- `preview-catalog-signature`
- `preview-catalog-snapshot`
- `preview-catalog-persist-plan`
- `preview-catalog-backfill-item`
- `preview-catalog-backfill-batch`
- `preview-catalog-backfill-template`
- `persist-catalog-backfill-template`
- `persist-catalog-backfill-item`
- `persist-catalog-backfill-batch`
- `persist-catalog-payload`
- `replace-catalog-payload`
- `persist-catalog-template-payload`
- `persist-catalog-template-version`
- `list-catalog-templates`
- `show-catalog-template`
- `show-catalog-spu`
- `show-catalog-outbox`
- `process-catalog-outbox`
- `check-catalog-migration`
- `check-catalog-scoped-migration`
- `preview-catalog-template-upgrade`
- `preview-catalog-template-replace-plan`
- `apply-catalog-template-upgrade`
- `apply-catalog-template-replace-plan`

### 13.4 当前边界

- 已完成 domain 规则、持久化 service、FastAPI 工具路由、Typer admin 命令和单测
- 已完成 Alembic 迁移，并已对 `.4` 开发库执行到 `20260405_0008`
- 已完成 `apple_m_series` 与 `garmin` 两个业务域的 enriched item backfill，当前 reconciliation 覆盖率均为 `1.0`
- 当前写入链路仍定位为内部工具/实现入口，还没有接正式业务鉴权、幂等存储和真实搜索消费者
- 当前读链路已经支持分页查询，但仍未补统一鉴权和统一错误码封装

### 13.5 样例输入

为了方便直接跑通最小链路，仓库里已经放了两份样例 payload：

- `docs/product-attribute-system/examples/minimal-template-payload.json`
- `docs/product-attribute-system/examples/minimal-product-payload.json`
- `docs/product-attribute-system/examples/replace-product-payload.json`
- `docs/product-attribute-system/examples/template-version-v2-payload.json`
- `docs/product-attribute-system/examples/template-version-v3-payload.json`

### 13.6 最小操作顺序

完成真实数据库迁移后，可以按下面顺序做最小验证：

```bash
cd <repo-root>
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli db-upgrade
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli persist-catalog-template-payload docs/product-attribute-system/examples/minimal-template-payload.json --dry-run
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli persist-catalog-template-payload docs/product-attribute-system/examples/minimal-template-payload.json --apply
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli persist-catalog-payload docs/product-attribute-system/examples/minimal-product-payload.json --dry-run
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli persist-catalog-payload docs/product-attribute-system/examples/minimal-product-payload.json --apply
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli list-catalog-spus --category-id 11111111-1111-1111-1111-111111111101 --page 1 --page-size 20
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli list-catalog-skus --spu-id 8ba511b5-77db-4431-a905-4a4098ce09e8 --page 1 --page-size 20
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli process-catalog-outbox --apply
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli replace-catalog-payload docs/product-attribute-system/examples/replace-product-payload.json --dry-run
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli replace-catalog-payload docs/product-attribute-system/examples/replace-product-payload.json --apply
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli process-catalog-outbox --apply
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli persist-catalog-template-version docs/product-attribute-system/examples/template-version-v2-payload.json --apply
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli preview-catalog-template-upgrade 8ba511b5-77db-4431-a905-4a4098ce09e8 11111111-1111-1111-1111-111111111402
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli preview-catalog-template-replace-plan 8ba511b5-77db-4431-a905-4a4098ce09e8 11111111-1111-1111-1111-111111111402
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli apply-catalog-template-replace-plan 8ba511b5-77db-4431-a905-4a4098ce09e8 11111111-1111-1111-1111-111111111402 --dry-run
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli persist-catalog-template-version docs/product-attribute-system/examples/template-version-v3-payload.json --apply
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli apply-catalog-template-upgrade 8ba511b5-77db-4431-a905-4a4098ce09e8 11111111-1111-1111-1111-111111111403 --apply
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli process-catalog-outbox --apply
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli check-catalog-migration --category-id 11111111-1111-1111-1111-111111111101 --spu-id 8ba511b5-77db-4431-a905-4a4098ce09e8 --expected-template-id 11111111-1111-1111-1111-111111111403 --page-size 20
```

建议先 `dry-run`，确认输出里的 `categoryId/templateId/spuId/skuIds` 正常，再执行 `--apply`。如果已经写入真实数据，记得把 `outbox_event` 继续消费到 `DONE`。

补充说明：

- `template-version-v2-payload.json` 用于演示“模板升级预检能识别销售属性变化，必须重写 SKU”
- `template-version-v3-payload.json` 用于演示“销售属性不变时，可以直接自动升级模板”
- 当 `canAutoUpgrade = false` 但现有值足够构造新模板时，可以先跑 `preview-catalog-template-replace-plan`，再决定是否 `apply-catalog-template-replace-plan`

### 13.7 迁移自检

仓库里已经补了一份可重复执行的 smoke SOP：

- `docs/product-attribute-system/migration-smoke-check.md`
- `docs/product-attribute-system/migration-status.md`
- `docs/product-attribute-system/migration-todolist.md`
- `docs/product-attribute-system/working-method.md`
- `docs/product-attribute-system/backfill-reconciliation-snapshot.md`

对应 CLI：

- `check-catalog-migration`
- `check-catalog-scoped-migration`

其中：

- `check-catalog-migration` 适合检查单个类目 / 单个 SPU 的迁移状态
- `check-catalog-scoped-migration` 适合在结项时一次性检查 demo 类目状态加 scoped backfill 覆盖率

后者会把 Alembic revision、模板版本、SPU/SKU 查询、目标模板一致性、outbox 清理状态和各业务域 reconciliation 一起汇总出来，适合作为每轮迁移后的标准总检。

### 13.8 当前迁移方法

当前迁移默认遵循固定节奏：

- 先列完整 todo
- 每次推进一个最小闭环
- 每完成一步就自检
- 根据自检结果动态更新 todo
- 每轮结论写回文档并同步到 OV

### 13.9 旧表 backfill 与迁移执行

当前已经支持把旧表里的单条 `item` 映射成 catalog draft，并完成域级批量迁移与 reconciliation。

CLI：

```bash
cd <repo-root>
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli preview-catalog-backfill-item 1005799969595
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli preview-catalog-backfill-item 934912583995
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli preview-catalog-backfill-batch apple_m_series --limit 5
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli preview-catalog-backfill-batch apple_m_series --limit 5 --enriched-only
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli persist-catalog-backfill-template apple_m_series --dry-run
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli persist-catalog-backfill-item 983778933882 --dry-run
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli persist-catalog-backfill-batch apple_m_series --limit 2 --dry-run --enriched-only
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli run-catalog-backfill-migration apple_m_series --operator-id ops-bot --batch-size 500 --apply
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli run-catalog-backfill-migration apple_m_series --operator-id ops-bot --batch-size 500 --apply --allow-warnings
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli run-catalog-backfill-migration garmin --operator-id ops-bot --batch-size 500 --apply
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli run-catalog-backfill-migration garmin --operator-id ops-bot --batch-size 500 --apply --allow-warnings
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli report-catalog-backfill-reconciliation apple_m_series
PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli report-catalog-backfill-reconciliation garmin
```

说明：

- 当前支持 `apple_m_series` 与 `garmin`
- 目标模板已经可以直接 bootstrap 到 `.4` 开发库
- 批量 preview 可先看 warning 分布，再用 `--enriched-only` 筛第一批候选
- 域级迁移命令默认会结合 `skip-existing` 做幂等 apply
- 遇到 warning 可先跑严格模式，再视情况用 `--allow-warnings` 补跑
- 输出里同时包含：
  - 旧表摘要
  - catalog payload draft
  - `snapshot`
  - `persistPlan`
- 当前 `.4` 开发库里两个域的 enriched item 已全部迁移完成，非 enriched 历史数据和生产级切流仍属于后续范围

## 14. SQL / 迁移资产边界

所有以 `.sql` 结尾的文件只作为迁移与初始化资产维护，不承担产品行为、接口契约或运行时逻辑的归属。它们的所有权必须和业务实现明确隔离。

- 新增或修改 `.sql` 文件时，只能表达明确、可回放、可验证的数据库变更
- `.sql` 资产要与代码实现、测试和验收命令一起交付，不能单独算完成
- 任何会影响线上行为的 DDL 都必须先回到本 README 的设计约束下检查，再进入迁移脚本
- 迁移脚本应保持保守，不要把“临时修复”包装成长期架构结论
- 如果某个能力只能通过手工 SQL 维持，说明实现成熟度还不够，后续应优先补代码和测试，而不是继续加脚本
- `.sql` 文件的责任边界要单独隔离：它们只属于迁移 / 初始化资产，不自动代表数据模型、接口契约或运行时行为的归属权
- 如果一个变更主要落在 `.sql` 文件里，它仍然必须回到对应的代码、测试和验收材料里补齐归属说明，而不是把所有权默认归到 SQL 本身
- 任何涉及 `.sql` 的改动，都应以“可回放、可对账、可回滚”为准绳；如果这三项不能同时成立，说明方案仍停留在草案阶段
- 对外宣称完成度时，不能只看 DDL 是否存在，而要同时满足代码、测试、迁移记录和验收命令闭环

当前对这条工作流的保守判断是：

- `docs/product-attribute-system/postgres-ddl-draft.sql` 仍然是草案，不应被视为最终收口包
- 迁移资产应围绕“可回滚、可复现、可对账”组织，而不是围绕一次性执行成功组织
