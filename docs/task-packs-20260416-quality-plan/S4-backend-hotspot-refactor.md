# S4 Backend 热点文件拆分收口

Status: Proposed
Priority: P0
Source: `cli.py`、`specs.py`、`pricing.py` 仍是后台侧最主要的并发冲突源与理解成本来源

## 启动条件

- `S2` 已完成
- 第一批并发任务已合并，避免热点文件拆分过程中再吸收横向噪音

## 目标

在已有 entrypoint/service 迁移基础上，继续把超大文件按职责域拆开，形成更可维护的 backend 边界。

## 独占文件

- [cli.py](<repo-root>/apps/collector/src/goofish_insight/cli.py)
- [specs.py](<repo-root>/apps/collector/src/goofish_insight/specs.py)
- [pricing.py](<repo-root>/apps/collector/src/goofish_insight/pricing.py)
- [30-entrypoint-and-legacy-spec-audit-20260414.md](<repo-root>/docs/30-entrypoint-and-legacy-spec-audit-20260414.md)
- `apps/collector/src/goofish_insight/application/services/pricing_domain.py`（new，可选）
- `apps/collector/src/goofish_insight/application/services/spec_normalization.py`（new，可选）
- `apps/collector/src/goofish_insight/entrypoints/cli/search.py`（new，可选）

## 范围

- `cli.py` 继续把搜索/收集/导出等子域下沉到 entrypoint 或 service。
- `pricing.py` 继续拆成规则判断、聚合计算、展示整形三个层次。
- `specs.py` 继续拆出规格归一化、模型映射、外部请求适配层。
- 同步更新审计文档，记录哪些遗留逻辑仍保留在旧文件中。

## 不做

- 不改数据库 schema
- 不引入新的后端框架
- 不在本任务里完成“全仓 except Exception 清零”

## 交付物

- 三个热点文件进一步瘦身
- 关键职责域拥有单独模块
- 后续开发不再默认把新逻辑继续堆回热点文件

## 验证

```bash
cd <repo-root> && ./scripts/ci/run_selected_integration.sh
```

## 完成定义

- `cli.py`、`specs.py`、`pricing.py` 至少各剥离出一个稳定职责模块
- 审计文档明确剩余遗留范围
- 选中集成测试通过
