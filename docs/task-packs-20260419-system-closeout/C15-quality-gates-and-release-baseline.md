# C15 质量门禁与交付基线收口

Status: Active
Priority: P2

## 目标

为当前系统收口建立最小但明确的交付基线，避免以后"改了很多，但没有统一验收口径"。

## 范围

1. 明确本仓库最小交付验证矩阵。
2. 把 React、Nest、Python、Docker 的关键验证统一收口。
3. 明确哪些测试是 P0 必过，哪些是扩展项。

## 交付基线

### P0 必过（阻塞发版）

| # | 检查项 | 命令 | 说明 |
|---|--------|------|------|
| 1 | React typecheck | `npm run typecheck -w @goofish/dashboard-react` | TypeScript 编译检查 |
| 2 | React test | `npm run test -w @goofish/dashboard-react` | Vitest 单元测试 |
| 3 | Nest typecheck | `npm run typecheck -w @goofish/dashboard-nest` | TypeScript 编译检查 |
| 4 | Nest test | `npm run test:e2e -w @goofish/dashboard-nest -- --runInBand` | Jest E2E 合同测试 |
| 5 | Python compile | `python -m compileall apps/collector/src apps/analyzer/src -q` | 语法级编译检查 |
| 6 | Python selected tests | `PYTHONPATH=apps/collector/src:apps/analyzer/src:packages/schema/src python -m unittest <selected modules>` | 主链路 unittest 子集 |

### P1 扩展（建议通过）

| # | 检查项 | 命令 | 说明 |
|---|--------|------|------|
| 7 | React build | `npm run build -w @goofish/dashboard-react` | Vite 生产构建 |
| 8 | Nest build | `npm run build -w @goofish/dashboard-nest` | Nest 生产构建 |

### P2 可选（环境允许时通过）

| # | 检查项 | 命令 | 说明 |
|---|--------|------|------|
| 9 | Docker build | `docker build .` | 容器镜像构建 |
| 10 | React lint | `npm run lint -w @goofish/dashboard-react` | ESLint 检查 |
| 11 | Nest lint | `npm run lint -w @goofish/dashboard-nest` | ESLint 检查 |

### 统一入口

```bash
npm run verify-baseline
# 或直接
bash scripts/verify-baseline.sh
```

说明：`scripts/verify-baseline.sh` 会优先使用 `PYTHON_BIN`，否则依次回退到仓库 `.venv/bin/python`、系统 `python`、系统 `python3`，避免把交付基线绑定到单一本地虚拟环境路径。

### Python 主链路测试子集（当前 `verify-baseline` 实际执行列表）

```
apps.analyzer.tests.test_daily_metrics_job
apps.analyzer.tests.test_model_scores_job
apps.analyzer.tests.test_analysis_reports_job
apps.analyzer.tests.test_adapter_boundary_contract
apps.collector.tests.test_notification_delivery_service
apps.collector.tests.test_alert_dispatcher_service
apps.collector.tests.test_outreach_outcomes_service
apps.collector.tests.test_rule_alias_matcher
apps.collector.tests.test_normalizers
apps.collector.tests.test_pricing_filters
apps.collector.tests.test_catalog_backfill_service
apps.collector.tests.test_catalog_migration_checks
apps.collector.tests.test_catalog_admin_commands
apps.collector.tests.test_webapp_cors
apps.collector.tests.test_runtime_controls
apps.collector.tests.test_quality_metrics
apps.collector.tests.test_collect_runtime_queries
apps.collector.tests.test_catalog_models
apps.collector.tests.test_review_entrypoints
apps.collector.tests.test_buy_entrypoints
apps.collector.tests.test_buy_feedback_service
apps.collector.tests.test_pricing_entrypoints
apps.collector.tests.test_pricing_read_model
apps.collector.tests.test_config_entrypoints
apps.collector.tests.test_task_config_entrypoints
apps.collector.tests.test_template_config_entrypoints
```

## 已完成交付物

1. `scripts/verify-baseline.sh` - 统一基线验证脚本，分级执行 P0/P1/P2 检查
2. `scripts/ci/run_dashboard_checks.sh` - CI dashboard 检查脚本，已补齐 React typecheck、React test、Nest typecheck、Nest e2e
3. `package.json` - 新增 `lint` 和 `verify-baseline` 顶层脚本
4. `.github/workflows/quality-gates.yml` - CI workflow（通过子脚本间接获得补齐）

## 不做

1. 不引入重量级新平台。
2. 不把每个历史测试都纳入强门禁。
3. 不引入 Python lint/mypy（当前 Python 代码无 lint 配置，属于 C13 工具链统一范围）。

## 完成定义

1. ✅ 仓库存在统一的"发版前至少跑什么"：`npm run verify-baseline`
2. ✅ 之后每轮改动都能按同一基线汇报。
3. ✅ CI workflow 覆盖 P0 全部检查项。
