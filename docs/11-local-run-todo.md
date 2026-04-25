# Local Run Todo

更新时间：2026-04-01
项目目录：`<repo-root>`

## 项目结论

- 当前要跑的主链路是 3 条：
  - 批收集：`collect-batch`
  - 首页 feed：`watch-home-feed`
  - 二次清洗：`review-v3-second-pass`
- 任务配置文件：`apps/collector/configs/monitor_tasks.json`
- feed 默认依赖附着浏览器 profile：`chrome-attached` / `chrome-attached-mac`
- 本次要求：二次清洗只能使用本机 `http://127.0.0.1:8000/v1`

## 执行 Todo

- [x] 识别目标项目并确认关键命令入口
- [x] 写入本地完整 todo
- [x] 修复运行环境
  - [x] 重建可用的 `.venv`
  - [x] 验证 `.venv` 与 CLI
  - [x] 验证数据库连通性
  - [x] 验证 CDP 浏览器连通性
  - [x] 验证本机 `8000` AI API 连通性
- [x] 锁定二次清洗只走本机 `8000`
  - [x] 修正默认脚本中的远端 AI 地址
  - [x] 验证运行日志中显示 `127.0.0.1:8000`
- [x] 跑起批收集脚本
  - 启动验证命令：`PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli collect-batch --profile-key chrome-attached-mac --only-task garmin-fenix --parallel-tabs 1`
  - 结果：成功进入真实搜索页 `佳明 forerunner 265`，验证附着浏览器采集链路可启动；该 run 已人工中止并标记为 `failed`，避免占住同一浏览器
  - 完整 smoke 命令：`PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli collect-batch --config-path reports/smoke-collect-batch-config.json --profile-key chrome-attached`
  - 结果：`run_id=42fc9b7d-7af2-49f7-8f75-4d76c6017481`，`pages_succeeded=1`
  - 更正：`pages: 0` 是有意保留的“持续翻页直到没有下一页”语义，不应回退到 `paging_limit`
  - 实际问题：原始包默认会在入库后裁掉，不能用 `raw_requests/raw_responses` 判断是否落库；同时 4 并发批收集会在 `seller_profiles` upsert 上偶发死锁
  - 已修复：保留 `pages: 0` 原语义，同时在批收集持久化阶段补充 seller 顺序稳定化、单事务 seller 缓存、死锁自动重试
  - 并发修复验证 smoke：`PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli collect-batch --config-path reports/collect-batch-parallel-smoke.json --profile-key chrome-attached-mac --parallel-tabs 4`
  - 并发修复验证结果：`run_id=d7d1ca40-2050-48ab-84f5-838a202b136c`、`465efe00-43d8-4e23-96a7-64d87e04f43a`、`1a30f597-e334-4887-a050-d38071a6de89`、`89863cf8-73a8-451f-bf4a-5378a782f274` 均 `completed`
  - 当前全量批收集将按修复后逻辑重新拉起：`collect-batch --config-path apps/collector/configs/monitor_tasks.json --profile-key chrome-attached-mac --parallel-tabs 8`
- [x] 跑起首页 feed 脚本
  - 实际命令：`PYTHONPATH=apps/collector/src ./.venv/bin/python -m goofish_insight.cli watch-home-feed --profile-key chrome-attached-mac --max-cycles 1 --dry-run`
  - 结果：成功输出 1 轮 feed JSON，`visible_card_count=6`，`target_match_count=0`
- [x] 跑起二次清洗脚本
  - 实际命令：`LIMIT=10 OUTPUT_PATH=reports/review-v3-second-pass-local-20260401.json PHASE=second_pass ./scripts/start-review-v3.sh`
  - 结果：成功生成 `reports/review-second-pass-local-20260401.json`、`.usage.json`、`.low-confidence.json`
- [x] 每完成一个 todo 即回写本文件状态与结果

## 已确认现状

- `<repo-root>/.env` 已切到本地浏览器 profile 目录 `data/browser-profile`
- 本机 `8000` 已有服务在运行
- 原 `.venv` 已备份为 `.venv.py312-broken-20260401`
- 当前 `.venv` 解释器为 `Python 3.11.15`
- 默认二次清洗入口已经切到 `scripts/start-review-v3.sh` / `scripts/start-review-v3-resident.sh`
- `show-attached-browsers` 已支持非 Windows 环境
