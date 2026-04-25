# cli.py / specs.py / pricing.py 依赖图与 Phase 1 迁移批次

Status: Active
Updated: 2026-04-13
Related Todo: [28-goofish-insight-upgrade-implementation-todolist-20260413.md](<repo-root>/docs/28-goofish-insight-upgrade-implementation-todolist-20260413.md)

## 目标

这份文档不做抽象架构讨论，只回答三个问题：

1. `cli.py` 现在到底堆了哪些能力。
2. `specs.py` / `pricing.py` 的高耦合区块在哪里。
3. Phase 1 应该按什么批次拆，才能避免边拆边撞线。

## 一、当前文件规模

| 文件 | `def/class` 数量 | 当前角色 |
|---|---:|---|
| `apps/collector/src/goofish_insight/cli.py` | 153 | 命令入口 + 采集执行 + 风控检测 + ingest + 首页 feed + browser session |
| `apps/collector/src/goofish_insight/specs.py` | 111 | 规则抽取 + catalog 属性映射 + LLM 请求拼装 + provider 适配 |
| `apps/collector/src/goofish_insight/pricing.py` | 40 | pricing view 聚合 + 机会分计算 + record label/contract |

## 二、`cli.py` 功能分区

### A. 任务与运行元数据

关键函数：
- `ensure_task`
- `get_task_or_raise`
- `create_run`
- `finalize_run`
- `capture_run_progress`
- `reconcile_stale_running_runs_with_session`
- `reconcile_stale_running_runs`

建议目标模块：
- `application/services/collector_runs.py`

### B. Search Browser / 风控 / 分页执行

关键函数：
- `run_live_search_batch`
- `run_parallel_search_batch`
- `run_search_plan_in_attached_tab`
- `execute_search_capture_on_page`
- `resolve_target_pages`
- `paginate_captured_search_results`
- `wait_for_capture_progress`
- `detect_page_risk_control_signal`
- `detect_page_risk_control_signal_from_page`
- `is_browser_disconnect_error`
- `infer_auth_state_from_error_message`
- `resolve_cdp_url`
- `discover_attached_browsers`

建议目标模块：
- `application/services/collector_browser.py`

### C. Search Payload 持久化 / ingest 落库

关键函数：
- `prepare_listings_for_persistence`
- `filter_suspicious_prepared_listings_for_ingest`
- `filter_title_length_prepared_listings_for_ingest`
- `filter_category_profile_prepared_listings_for_ingest`
- `persist_new_capture_pages`
- `persist_captured_payloads`
- `_persist_captured_payloads_once`
- `upsert_seller`
- `upsert_item`
- `should_insert_snapshot`
- `mark_item_snapshot_timestamp`
- `load_ingest_rejection_item_ids`
- `touch_item_ingest_rejections`
- `upsert_item_ingest_rejection`
- `upsert_item_ingest_rejections`

建议目标模块：
- `application/services/collector_ingest.py`

### D. Browser Session / 登录态

关键函数：
- `upsert_browser_session_state`
- `build_search_capture_failure_message`
- `build_manual_verification_transport_message`
- `extract_payload_error`
- `classify_payload_status`

建议目标模块：
- `application/services/collector_browser.py`

### E. 首页 Feed 工作台

关键函数：
- `run_home_feed_refresh`
- `prepare_home_feed_page`
- `switch_home_feed_primary_tab`
- `extract_home_feed_cards`
- `extract_home_feed_cards_from_api_payloads`
- `extract_home_feed_cards_from_dom`
- `process_home_feed_cards`
- `match_home_feed_target`
- `send_home_feed_message`
- `send_message_in_chat`
- `upsert_outreach_record`

建议目标模块：
- `application/services/feed_runtime.py`
- 本轮不拆，只做依赖图记录。

## 三、`specs.py` 功能分区

### A. runtime context / template / catalog 映射

关键函数：
- `load_runtime_context_for_item`
- `load_template_detail_for_item`
- `enrich_candidate_with_catalog_attributes`
- `build_candidate_catalog_attributes`
- `_match_model_catalog_id`
- `apply_runtime_context_to_candidate`

拆分建议：
- `application/services/spec_template_runtime.py`

### B. 规则抽取（Garmin / Apple / Lens）

关键函数：
- `extract_rule_specs`
- `extract_garmin_rule`
- `extract_apple_rule`
- `extract_lens_rule`
- `pick_garmin_*`
- `pick_apple_*`
- `_score_lens_signature_match`

拆分建议：
- `application/services/spec_rule_engine.py`
- Phase 1 先做依赖图，不强拆。

### C. LLM provider / 请求构造 / trace

关键函数：
- `extract_llm_specs`
- `call_openai_compatible_chat`
- `build_openai_request`
- `build_anthropic_request`
- `build_ark_responses_request`
- `write_llm_trace`
- `extract_usage_stats`

拆分建议：
- `application/services/spec_llm_client.py`

## 四、`pricing.py` 功能分区

### A. view 装配与 record 加载

关键函数：
- `build_pricing_views`
- `load_pricing_records`
- `_build_pricing_candidate_stmt`
- `_load_pricing_candidate_rows_from_session`
- `_load_pricing_records_from_session`
- `resolve_pricing_record`

拆分建议：
- `application/services/pricing_queries.py`

### B. 聚合与分组

关键函数：
- `aggregate_pricing_view`
- `pricing_group_key`
- `summarize_pricing_group`
- `collapse_records_by_seller`
- `filter_outlier_price_records`
- `percentile`

拆分建议：
- `application/services/pricing_aggregates.py`

### C. 买方评分 / tier / 机会判断

关键函数：
- `compute_reliability_score`
- `compute_price_stability_score`
- `compute_listing_age_metrics`
- `compute_profit_margin_pct`
- `compute_opportunity_score`
- `classify_opportunity_tier`

拆分建议：
- `application/services/pricing_scores.py`

## 五、Phase 1 迁移批次

### Batch A：先拆 `cli.py` 搜索采集执行流

目标：把 W1/W11 最容易互撞的一段先移出主文件。

范围：
- `create_run`
- `finalize_run`
- `capture_run_progress`
- `run_live_search_batch`
- `run_parallel_search_batch`
- `run_search_plan_in_attached_tab`
- `execute_search_capture_on_page`
- `persist_new_capture_pages`
- `persist_captured_payloads`
- `_persist_captured_payloads_once`
- `upsert_browser_session_state`
- 风控/分页辅助函数

落点：
- `collector_runs.py`
- `collector_browser.py`
- `collector_ingest.py`

### Batch B：再拆 ingest gate 与 rejection 链路

范围：
- `prepare_listings_for_persistence`
- `filter_*_prepared_listings_for_ingest`
- `classify_*_ingest_block_reason`
- `load_ingest_rejection_item_ids*`
- `touch_item_ingest_rejections`
- `upsert_item_ingest_rejection*`
- `should_insert_snapshot`
- `mark_item_snapshot_timestamp`
- `upsert_seller`
- `upsert_item`

落点：
- `collector_ingest.py`

### Batch C：最后处理 feed runtime 与 outreach

范围：
- 首页 feed 抓取
- target 匹配
- detail seller snapshot
- outreach 发送与记录

原因：
- 这块和当前 P0/P1 的 checkpoint、analyzer、runtime 底座不是同一关键路径，后拆风险更低。

## 六、实施顺序建议

1. 先保持命令入口不动，只迁业务函数。
2. 每一批迁移后都要求：
   - `goofish_insight.cli` 命令名不变
   - 现有 smoke 命令不变
   - 相关单测与 py_compile 通过
3. `specs.py` 和 `pricing.py` 在 Phase 1 先产出分层边界，不强做大搬迁。
4. `feed runtime` 不和 `search collect` 同时重构，避免两个高状态模块一起动。

## 七、本轮已完成的前置动作

- `collect-batch` 已经从“靠日志猜状态”升级为写 `collector_job_run` / `collector_job_checkpoint`。
- 风控后的 transport error 已经保留上下文，不再误归类普通失败。
- `collect-batch` 已增加宿主机级互斥锁，手工 smoke 和 resident 不会再同时争抢同一浏览器。
- `daily_metrics_job` MVP 已经独立到 `apps/analyzer`，可手动运行并可被 runtime control 看见。
