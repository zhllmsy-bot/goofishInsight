import json
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from goofish_insight.application.services.dashboard_filters import (
    build_active_filter_summary,
    build_filter_catalog,
    sanitize_structured_filters,
)
from goofish_insight.application.services.dashboard_panels import format_profit_range_label, pricing_dimensions
from goofish_insight.application.services.dashboard_queries import (
    build_domain_trend_cards,
    build_domain_trend_chart,
    heartbeat_signal,
    heartbeat_state,
    load_available_domains,
    select_final_trend_cards,
    select_trend_focus_groups,
    summarize_trend_quality,
    summarize_daily_snapshots,
)
from goofish_insight.application.services.mobile_market_dashboard import (
    build_mobile_market_calibration_panel,
    merge_mobile_market_into_top_models,
)
from goofish_insight.application.services.llm_prompt_traces import (
    build_dashboard_llm_traces_section_data,
    load_dashboard_llm_trace_detail,
)
from goofish_insight.application.services.review_progress_page import (
    build_llm_review_overview,
    build_usage_summary,
    build_worker_run_cards,
    summarize_worker_event,
)


class WebServiceTests(unittest.TestCase):
    def test_build_dashboard_llm_traces_section_data_reads_latest_trace(self) -> None:
        with TemporaryDirectory() as temp_dir:
            trace_dir = Path(temp_dir)
            trace_dir.joinpath("2026-04-07T10-00-00-000000-first.json").write_text(
                json.dumps(
                    {
                        "generatedAt": "2026-04-07T10:00:00",
                        "provider": "ark_responses",
                        "model": "doubao-old",
                        "url": "https://example.com/v1/responses",
                        "method": "POST",
                        "messages": [
                            {"role": "system", "content": "Return JSON only."},
                            {"role": "user", "content": "Extract first payload."},
                        ],
                        "requestHeaders": {"Authorization": "[REDACTED]"},
                        "requestPayload": {"model": "doubao-old"},
                        "responsePayload": {"ok": True},
                        "error": None,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            trace_dir.joinpath("2026-04-07T10-05-00-000000-second.json").write_text(
                json.dumps(
                    {
                        "generatedAt": "2026-04-07T10:05:00",
                        "provider": "ark_responses",
                        "model": "doubao-new",
                        "url": "https://example.com/v1/responses",
                        "method": "POST",
                        "messages": [
                            {"role": "system", "content": "Use latest schema."},
                            {"role": "user", "content": "Extract newest payload."},
                        ],
                        "requestHeaders": {"Authorization": "[REDACTED]"},
                        "requestPayload": {"model": "doubao-new", "input": []},
                        "responsePayload": {"output": [{"type": "message"}]},
                        "error": None,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "goofish_insight.application.services.llm_prompt_traces.get_settings",
                return_value=SimpleNamespace(
                    ai_prompt_trace_enabled=True,
                    ai_prompt_trace_dir=trace_dir,
                ),
            ):
                payload = build_dashboard_llm_traces_section_data(limit=2)

        self.assertTrue(payload["trace_enabled"])
        self.assertEqual(payload["trace_count"], 2)
        self.assertEqual(payload["traces"][0]["trace_key"], "2026-04-07T10-05-00-000000-second")
        self.assertEqual(payload["latest_trace"]["model"], "doubao-new")
        self.assertIn("Extract newest payload.", payload["latest_trace"]["messages"][1]["content_text"])

    def test_load_dashboard_llm_trace_detail_rejects_path_traversal(self) -> None:
        with TemporaryDirectory() as temp_dir:
            detail = load_dashboard_llm_trace_detail("../secret", trace_dir=Path(temp_dir))
        self.assertIsNone(detail)

    def test_dashboard_llm_traces_skip_legacy_title_token_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            trace_dir = Path(temp_dir)
            trace_dir.joinpath("2026-04-08T10-00-00-legacy.json").write_text(
                json.dumps(
                    {
                        "generatedAt": "2026-04-08T10:00:00",
                        "provider": "ark_responses",
                        "model": "legacy-model",
                        "messages": [
                            {
                                "role": "user",
                                "content": "contains title_tokens and old prompt shape",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            trace_dir.joinpath("2026-04-08T10-05-00-clean.json").write_text(
                json.dumps(
                    {
                        "generatedAt": "2026-04-08T10:05:00",
                        "provider": "ark_responses",
                        "model": "clean-model",
                        "messages": [
                            {
                                "role": "user",
                                "content": "only current schema fields",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "goofish_insight.application.services.llm_prompt_traces.get_settings",
                return_value=SimpleNamespace(
                    ai_prompt_trace_enabled=True,
                    ai_prompt_trace_dir=trace_dir,
                ),
            ):
                payload = build_dashboard_llm_traces_section_data(limit=5)

        self.assertEqual(payload["trace_count"], 1)
        self.assertEqual(payload["traces"][0]["trace_key"], "2026-04-08T10-05-00-clean")
        self.assertEqual(payload["latest_trace"]["model"], "clean-model")

    def test_load_available_domains_excludes_onboarding_scope(self) -> None:
        class _ScalarResult:
            def __init__(self, rows) -> None:
                self._rows = rows

            def scalars(self):
                return self._rows

        class _Session:
            def execute(self, _stmt):
                return _ScalarResult(["apple_m_series", "garmin", "xianyu_onboarding"])

        self.assertEqual(
            load_available_domains(_Session()),
            ["apple_computer", "garmin_watch"],
        )

    def test_sanitize_structured_filters_respects_domain_layout(self) -> None:
        filters = {
            "product_label": "Mac Studio",
            "spec_label": "Mac Studio / M1 Max",
            "display_type": "AMOLED",
            "case_size_mm": 47,
            "is_solar": True,
            "chip_family": "M1 Max",
            "screen_size_in": None,
            "memory_gb": 64,
            "storage_gb": 1024,
        }

        result = sanitize_structured_filters(
            business_domain="apple_m_series",
            filters=filters,
        )

        self.assertEqual(result["product_label"], "Mac Studio")
        self.assertEqual(result["chip_family"], "M1 Max")
        self.assertIsNone(result["display_type"])
        self.assertIsNone(result["case_size_mm"])
        self.assertIsNone(result["is_solar"])

    def test_sanitize_structured_filters_supports_runtime_layout_override(self) -> None:
        class _Result:
            def __init__(self, row) -> None:
                self._row = row

            def scalar_one_or_none(self):
                return self._row

        class _Session:
            def __init__(self, row) -> None:
                self._row = row

            def execute(self, _stmt):
                return _Result(self._row)

        runtime_row = type(
            "RuntimeProfileStub",
            (),
            {"metadata_json": {"dashboardFilterFields": ["product_label", "display_type", "chip_family"]}},
        )()
        filters = {
            "product_label": "Mac Studio",
            "spec_label": "Mac Studio / M1 Max",
            "display_type": "AMOLED",
            "case_size_mm": 47,
            "is_solar": True,
            "chip_family": "M1 Max",
            "screen_size_in": None,
            "memory_gb": 64,
            "storage_gb": 1024,
        }

        result = sanitize_structured_filters(
            business_domain="apple_computer",
            filters=filters,
            session=_Session(runtime_row),
        )

        self.assertEqual(result["product_label"], "Mac Studio")
        self.assertEqual(result["display_type"], "AMOLED")
        self.assertEqual(result["chip_family"], "M1 Max")
        self.assertIsNone(result["spec_label"])
        self.assertIsNone(result["memory_gb"])

    def test_build_active_filter_summary_formats_values(self) -> None:
        summary = build_active_filter_summary(
            {
                "product_label": "Fenix 8",
                "spec_label": None,
                "display_type": "AMOLED",
                "case_size_mm": 47,
                "is_solar": True,
                "chip_family": None,
                "screen_size_in": None,
                "memory_gb": None,
                "storage_gb": None,
            }
        )

        self.assertEqual(
            summary,
            ["产品: Fenix 8", "屏幕类型: AMOLED", "表盘尺寸: 47mm", "太阳能: Solar"],
        )

    def test_build_filter_catalog_filters_dirty_apple_labels(self) -> None:
        filters = {
            "product_label": None,
            "spec_label": None,
            "display_type": None,
            "case_size_mm": None,
            "is_solar": None,
            "chip_family": None,
            "screen_size_in": None,
            "memory_gb": None,
            "storage_gb": None,
        }
        records = [
            {
                "product_label": "Mac mini / M4",
                "spec_label": "Mac mini / M4 / 16G / 256G",
                "product_line": "Mac mini",
                "chip_family": "M4",
                "memory_gb": 16,
                "storage_gb": 256,
                "price": 3999,
                "exact_spec_ready": True,
            },
            {
                "product_label": "Apple 苹果AI MacBook Air",
                "spec_label": "Apple 苹果AI MacBook Air / 16G / 512G",
                "product_line": "Apple 苹果AI MacBook Air",
                "chip_family": "M4",
                "memory_gb": 16,
                "storage_gb": 512,
                "price": 5999,
                "exact_spec_ready": True,
            },
            {
                "product_label": "M4 16GB 256GB 感兴趣的话点“我想要”和我私聊吧～",
                "spec_label": "M4 16GB 256GB 感兴趣的话点“我想要”和我私聊吧～ / 16G / 256G",
                "product_line": "M4 16GB 256GB 感兴趣的话点“我想要”和我私聊吧～",
                "chip_family": "M4",
                "memory_gb": 16,
                "storage_gb": 256,
                "price": 3799,
                "exact_spec_ready": True,
            },
        ]

        catalog = build_filter_catalog(
            records,
            filters,
            business_domain="apple_computer",
        )

        self.assertEqual(
            [option["value"] for option in catalog["product_options"]],
            ["Mac mini / M4"],
        )
        self.assertEqual(
            [option["value"] for option in catalog["spec_options"]],
            ["Mac mini / M4 / 16G / 256G"],
        )

    def test_build_filter_catalog_filters_listing_copy_apple_labels(self) -> None:
        filters = {
            "product_label": None,
            "spec_label": None,
            "display_type": None,
            "case_size_mm": None,
            "is_solar": None,
            "chip_family": None,
            "screen_size_in": None,
            "memory_gb": None,
            "storage_gb": None,
        }
        records = [
            {
                "product_label": "MacBook Pro / 14in",
                "spec_label": "MacBook Pro / 14in / M3 Pro / 18G / 512G",
                "product_line": "MacBook Pro",
                "chip_family": "M3 Pro",
                "screen_size_in": 14,
                "memory_gb": 18,
                "storage_gb": 512,
                "price": 8999,
                "exact_spec_ready": True,
            },
            {
                "product_label": "14寸macbookpro 23年末款 国行黑色 M3pro / M3 Pro",
                "spec_label": "2023年14寸m3Pro 18+512 有监管锁 已绕开 / M3 Pro / 18G / 512G",
                "product_line": "14寸macbookpro 23年末款 国行黑色 M3pro",
                "chip_family": "M3 Pro",
                "screen_size_in": 14,
                "memory_gb": 18,
                "storage_gb": 512,
                "price": 7999,
                "exact_spec_ready": True,
            },
        ]

        catalog = build_filter_catalog(
            records,
            filters,
            business_domain="apple_computer",
        )

        self.assertEqual(
            [option["value"] for option in catalog["product_options"]],
            ["MacBook Pro / 14in"],
        )
        self.assertEqual(
            [option["value"] for option in catalog["spec_options"]],
            ["MacBook Pro / 14in / M3 Pro / 18G / 512G"],
        )

    def test_build_llm_review_overview_aggregates_rows(self) -> None:
        now = datetime.now(UTC)
        overview = build_llm_review_overview(
            [
                {
                    "pending_review_count": 4,
                    "in_progress_count": 1,
                    "pending_audit_count": 2,
                    "reviewed_valid_count": 10,
                    "reviewed_invalid_count": 2,
                    "review_target_total": 19,
                    "last_reviewed_at": now,
                },
                {
                    "pending_review_count": 6,
                    "in_progress_count": 3,
                    "pending_audit_count": 1,
                    "reviewed_valid_count": 5,
                    "reviewed_invalid_count": 1,
                    "review_target_total": 16,
                    "last_reviewed_at": None,
                },
            ]
        )

        self.assertEqual(overview["domain_count"], 2)
        self.assertEqual(overview["pending_review_count"], 10)
        self.assertEqual(overview["pending_audit_count"], 3)
        self.assertEqual(overview["reviewed_total"], 18)
        self.assertEqual(overview["review_target_total"], 35)
        self.assertEqual(overview["completion_percent"], 51.4)
        self.assertEqual(overview["last_reviewed_at"], now)

    def test_summarize_worker_event_marks_failures(self) -> None:
        event = summarize_worker_event(
            {
                "event": "batch_failed",
                "worker_name": "worker-01",
                "batch_index": 7,
                "error": "HTTP 429",
            }
        )

        self.assertEqual(event["status_class"], "failed")
        self.assertIn("worker-01", event["summary"])
        self.assertIn("HTTP 429", event["summary"])

    def test_build_worker_run_cards_reads_recent_v3_watch_and_summary_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            reports_dir = Path(temp_dir)
            reports_dir.joinpath("review-second-pass-live-20260402-225620.json").write_text(
                '[{"item_id":"1","review_status":"valid","review_input":{"business_domain":"apple_m_series"}}]',
                encoding="utf-8",
            )
            reports_dir.joinpath("review-v3-full-active-watch-20260412-000644.log").write_text(
                "\n".join(
                    [
                        '{"event":"starting_full_backfill","limit":35460,"workers":4,"first_pass_batch_size":4,"prefix":"review-v3-full-active"}',
                        '{"event":"cohort_created","count":35460,"path":"reports/review-v3-full-active-20260412-000645.itemids.txt"}',
                        '{"event":"first_pass_batches_created","batch_count":8867,"path":"reports/review-v3-full-active-20260412-000645.first-pass.batches","batch_size":4}',
                        '{"event":"first_pass_batch_completed","business_domain":"camera_interchangeable_lens","batch_size":4,"completed_item_count":8,"failed_item_count":0}',
                    ]
                ),
                encoding="utf-8",
            )
            reports_dir.joinpath("review-v3-top1000-full-20260411-184042-20260411-230807.second-pass-summary.json").write_text(
                json.dumps(
                    {
                        "cohortCount": 1000,
                        "secondPassDoneCount": 290,
                        "secondPassFailedCount": 0,
                        "resolutionStatusCounts": {
                            "VALID_READY_FOR_PRICING": 694,
                            "MANUAL_AUDIT_REQUIRED": 193,
                            "REJECTED_ACCESSORY": 69,
                        },
                        "domainResolutionStatusCounts": {
                            "apple_computer": {"VALID_READY_FOR_PRICING": 373},
                            "garmin_watch": {"VALID_READY_FOR_PRICING": 204},
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "goofish_insight.application.services.review_progress_page.REPORTS_DIR",
                reports_dir,
            ):
                cards = build_worker_run_cards(business_domain=None)

        self.assertEqual(len(cards), 2)
        self.assertTrue(all(card["pipeline"].startswith("V3") for card in cards))
        self.assertEqual({card["run_type"] for card in cards}, {"worker_log", "result_file"})
        self.assertIn("V3 Full Backfill", {card["pipeline"] for card in cards})
        self.assertIn("V3 Summary", {card["pipeline"] for card in cards})

    def test_build_worker_run_cards_ignores_onboarding_scope_by_default(self) -> None:
        with TemporaryDirectory() as temp_dir:
            reports_dir = Path(temp_dir)
            reports_dir.joinpath("review-v3-sample.json").write_text(
                """
                {
                  "item_id": "1",
                  "business_domain": "xianyu_onboarding",
                  "resolution_status": "VALID_READY_FOR_PRICING",
                  "llm_request_count": 1,
                  "llm_usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
                }
                """.strip(),
                encoding="utf-8",
            )

            with patch(
                "goofish_insight.application.services.review_progress_page.REPORTS_DIR",
                reports_dir,
            ):
                cards = build_worker_run_cards(business_domain=None)

        self.assertEqual(cards, [])

    def test_build_usage_summary_reads_v3_result_files_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            reports_dir = Path(temp_dir)
            reports_dir.joinpath("review-second-pass-ark-doubao-smoke-20260409.json").write_text(
                """
                [
                  {
                    "item_id": "1",
                    "review_status": "valid",
                    "review_input": {"business_domain": "apple_m_series"}
                  }
                ]
                """.strip(),
                encoding="utf-8",
            )
            reports_dir.joinpath("review-second-pass-ark-doubao-smoke-20260409.usage.json").write_text(
                '{"llm_request_count": 999, "total_usage": {"input_tokens": 9999, "output_tokens": 9999, "total_tokens": 19998}}',
                encoding="utf-8",
            )
            reports_dir.joinpath("review-v3-first-pass-batch-lens-smoke-4-v2.json").write_text(
                json.dumps(
                    [
                        {
                            "item_id": "1",
                            "business_domain": "camera_interchangeable_lens",
                            "resolution_status": "VALID_READY_FOR_PRICING",
                            "llm_request_count": 1,
                            "llm_usage": {
                                "input_tokens": 100,
                                "output_tokens": 50,
                                "total_tokens": 150,
                                "cached_tokens": 5,
                            },
                        },
                        {
                            "item_id": "2",
                            "business_domain": "camera_interchangeable_lens",
                            "resolution_status": "PENDING_REVIEW",
                            "stage_status": "second_pass_complete",
                            "llm_request_count": 1,
                            "llm_usage": {
                                "input_tokens": 120,
                                "output_tokens": 60,
                                "total_tokens": 180,
                                "cached_tokens": 0,
                            },
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            with patch(
                "goofish_insight.application.services.review_progress_page.REPORTS_DIR",
                reports_dir,
            ):
                summary = build_usage_summary(business_domain=None)

        self.assertEqual(summary["file_count"], 1)
        self.assertEqual(summary["request_count"], 2)
        self.assertEqual(summary["total_tokens"], 330)
        self.assertEqual(summary["cached_tokens"], 5)
        self.assertEqual(summary["high_confidence_kept_count"], 1)
        self.assertEqual(summary["second_pass_requested_count"], 1)
        self.assertEqual(summary["second_pass_unresolved_count"], 1)
        self.assertEqual(summary["recent_usage_runs"][0]["pipeline"], "V3")
        self.assertEqual(summary["recent_usage_runs"][0]["business_domain"], "camera_interchangeable_lens")

    def test_pricing_dimensions_formats_mixed_specs(self) -> None:
        row = {
            "display_type": "AMOLED",
            "case_size_mm": 47,
            "is_solar": True,
            "screen_size_in": 14.2,
            "chip_family": "M4 Pro",
            "cpu_cores": 14,
            "gpu_cores": 20,
            "memory_gb": 48,
            "storage_gb": 1024,
        }

        self.assertEqual(
            pricing_dimensions(row),
            ["AMOLED", "47mm", "太阳能", "14.2英寸", "M4 Pro", "14核 CPU", "20核 GPU", "48G", "1TB"],
        )

    def test_format_profit_range_label_formats_single_and_range(self) -> None:
        self.assertEqual(
            format_profit_range_label({"estimated_profit_floor": 375, "estimated_profit_ceiling": 806}),
            "¥375 ~ ¥806",
        )
        self.assertEqual(
            format_profit_range_label({"estimated_profit_floor": 500, "estimated_profit_ceiling": 500}),
            "¥500",
        )

    def test_heartbeat_state_marks_stale_after_threshold(self) -> None:
        now = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)

        self.assertEqual(
            heartbeat_state(
                last_seen_at=now - timedelta(days=1),
                heartbeat_days=3,
                now=now,
            ),
            "active",
        )
        self.assertEqual(
            heartbeat_state(
                last_seen_at=now - timedelta(days=5),
                heartbeat_days=3,
                now=now,
            ),
            "stale",
        )

    def test_heartbeat_signal_raises_alert_when_recent_feed_cools(self) -> None:
        now = datetime(2026, 3, 31, 12, 0, tzinfo=UTC)
        signal = heartbeat_signal(
            active_count=4,
            stale_count=5,
            latest_seen_at=now - timedelta(hours=3),
            heartbeat_days=3,
            now=now,
        )

        self.assertEqual(signal["label"], "明显降温")
        self.assertEqual(signal["class_name"], "alert")
        self.assertAlmostEqual(signal["stale_ratio"], 55.6, places=1)

    def test_summarize_daily_snapshots_builds_daily_ohlc(self) -> None:
        candles = summarize_daily_snapshots(
            snapshots=[
                {
                    "item_id": "a",
                    "title": "a",
                    "snapshot_at": datetime(2026, 3, 28, 1, 0, tzinfo=UTC),
                    "price": 100.0,
                },
                {
                    "item_id": "b",
                    "title": "b",
                    "snapshot_at": datetime(2026, 3, 28, 3, 0, tzinfo=UTC),
                    "price": 120.0,
                },
                {
                    "item_id": "c",
                    "title": "c",
                    "snapshot_at": datetime(2026, 3, 28, 4, 0, tzinfo=UTC),
                    "price": 130.0,
                },
                {
                    "item_id": "d",
                    "title": "d",
                    "snapshot_at": datetime(2026, 3, 28, 5, 0, tzinfo=UTC),
                    "price": 140.0,
                },
                {
                    "item_id": "a",
                    "title": "a",
                    "snapshot_at": datetime(2026, 3, 28, 6, 0, tzinfo=UTC),
                    "price": 110.0,
                },
                {
                    "item_id": "e",
                    "title": "e",
                    "snapshot_at": datetime(2026, 3, 28, 7, 0, tzinfo=UTC),
                    "price": 2000.0,
                },
            ]
        )

        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0]["mid_price"], 125.0)
        self.assertEqual(candles[0]["open_price"], 125.0)
        self.assertEqual(candles[0]["close_price"], 125.0)
        self.assertEqual(candles[0]["high_price"], 132.5)
        self.assertEqual(candles[0]["low_price"], 116.25)
        self.assertEqual(candles[0]["sample_count"], 4)

    def test_build_domain_trend_chart_returns_renderable_line_chart(self) -> None:
        chart = build_domain_trend_chart(
            domain_name="Garmin手表",
            candles=[
                {
                    "date_label": "03-28",
                    "open_price": 100.0,
                    "close_price": 120.0,
                    "high_price": 135.0,
                    "low_price": 96.0,
                    "mid_price": 120.0,
                    "band_low_price": 108.0,
                    "band_high_price": 132.0,
                    "sample_count": 3,
                },
                {
                    "date_label": "03-29",
                    "open_price": 118.0,
                    "close_price": 112.0,
                    "high_price": 140.0,
                    "low_price": 108.0,
                    "mid_price": 112.0,
                    "band_low_price": 110.0,
                    "band_high_price": 124.0,
                    "sample_count": 4,
                },
            ],
        )

        self.assertIsNotNone(chart)
        assert chart is not None
        self.assertEqual(chart["day_count"], 2)
        self.assertEqual(chart["latest_sample_count"], 4)
        self.assertEqual(len(chart["trend_points"]), 2)
        self.assertTrue(chart["trend_line_path"].startswith("M "))
        self.assertTrue(chart["trend_upper_path"].startswith("M "))
        self.assertTrue(chart["trend_lower_path"].startswith("M "))
        self.assertEqual(chart["trend_points"][0]["date_label"], "03-28")
        self.assertEqual(chart["trend_points"][1]["date_label"], "03-29")
        self.assertEqual(len(chart["price_ticks"]), 4)
        self.assertIn("价带宽度", chart["volatility_label"])
        self.assertIn("虚线", chart["disclaimer"])

    def test_build_domain_trend_cards_uses_full_history_for_selected_groups(self) -> None:
        item_one = SimpleNamespace(item_id="item-1")
        item_two = SimpleNamespace(item_id="item-2")
        snapshot_rows = [
            SimpleNamespace(
                item_id="item-1",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 3, 1, tzinfo=UTC),
                price=1000.0,
            ),
            SimpleNamespace(
                item_id="item-2",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 3, 10, tzinfo=UTC),
                price=1100.0,
            ),
            SimpleNamespace(
                item_id="item-1",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 4, 5, tzinfo=UTC),
                price=1200.0,
            ),
            SimpleNamespace(
                item_id="item-2",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 4, 8, tzinfo=UTC),
                price=1180.0,
            ),
        ]

        class _Result:
            def __init__(self, rows) -> None:
                self._rows = rows

            def all(self):
                return self._rows

        class _Session:
            def __init__(self) -> None:
                self._calls = 0

            def execute(self, _stmt):
                self._calls += 1
                if self._calls == 1:
                    return _Result([(item_one, None), (item_two, None)])
                if self._calls == 2:
                    return _Result(snapshot_rows)
                raise AssertionError("unexpected execute call")

        with patch(
            "goofish_insight.application.services.dashboard_queries.resolve_pricing_record",
            side_effect=[
                {
                    "item_id": "item-1",
                    "business_domain": "apple_computer",
                    "product_label": "MacBook Pro",
                    "product_line": "MacBook Pro",
                    "title": "item one",
                },
                {
                    "item_id": "item-2",
                    "business_domain": "apple_computer",
                    "product_label": "MacBook Pro",
                    "product_line": "MacBook Pro",
                    "title": "item two",
                },
            ],
        ), patch(
            "goofish_insight.application.services.dashboard_queries.select_trend_focus_groups",
            return_value=[
                {
                    "business_domain": "apple_computer",
                    "product_label": "MacBook Pro",
                    "listing_count": 8,
                    "seller_sample_count": 8,
                    "unique_seller_count": 4,
                    "exact_spec_ratio": 0.92,
                    "reliability_score": 90,
                    "latest_seen_at": datetime(2026, 4, 8, tzinfo=UTC),
                }
            ],
        ):
            cards = build_domain_trend_cards(
                _Session(),
                business_domain="apple_computer",
                window_days=30,
                heartbeat_days=7,
                pricing_records=[{"item_id": "fresh-a"}],
                pricing_contract={"templateCompleteness": {"isComplete": True}},
            )

        self.assertEqual(len(cards), 1)
        self.assertGreaterEqual(cards[0]["window_days"], 39)
        self.assertEqual(cards[0]["trend_points"][0]["date_label"], "03-01")
        self.assertEqual(cards[0]["trend_points"][-1]["date_label"], "04-08")
        self.assertEqual(cards[0]["pricingAvailabilitySummary"]["readinessSummary"], "可直接按价格指导口径使用")

    def test_build_domain_trend_cards_respects_filtered_item_ids(self) -> None:
        item_one = SimpleNamespace(item_id="item-1")
        item_two = SimpleNamespace(item_id="item-2")
        snapshot_rows = [
            SimpleNamespace(
                item_id="item-1",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 3, 1, tzinfo=UTC),
                price=1000.0,
            ),
            SimpleNamespace(
                item_id="item-2",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 3, 10, tzinfo=UTC),
                price=1100.0,
            ),
            SimpleNamespace(
                item_id="item-1",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 4, 5, tzinfo=UTC),
                price=1200.0,
            ),
            SimpleNamespace(
                item_id="item-2",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 4, 8, tzinfo=UTC),
                price=1180.0,
            ),
        ]

        class _Result:
            def __init__(self, rows) -> None:
                self._rows = rows

            def all(self):
                return self._rows

        class _Session:
            def __init__(self) -> None:
                self._calls = 0

            def execute(self, _stmt):
                self._calls += 1
                if self._calls == 1:
                    return _Result([(item_one, None), (item_two, None)])
                if self._calls == 2:
                    return _Result(snapshot_rows)
                raise AssertionError("unexpected execute call")

        with patch(
            "goofish_insight.application.services.dashboard_queries.resolve_pricing_record",
            side_effect=[
                {
                    "item_id": "item-1",
                    "business_domain": "apple_computer",
                    "product_label": "MacBook Pro",
                    "product_line": "MacBook Pro",
                    "title": "item one",
                },
                {
                    "item_id": "item-2",
                    "business_domain": "apple_computer",
                    "product_label": "MacBook Pro",
                    "product_line": "MacBook Pro",
                    "title": "item two",
                },
            ],
        ), patch(
            "goofish_insight.application.services.dashboard_queries.select_trend_focus_groups",
            return_value=[
                {
                    "business_domain": "apple_computer",
                    "product_label": "MacBook Pro",
                    "listing_count": 8,
                    "seller_sample_count": 8,
                    "unique_seller_count": 4,
                    "exact_spec_ratio": 0.92,
                    "reliability_score": 90,
                    "latest_seen_at": datetime(2026, 4, 8, tzinfo=UTC),
                }
            ],
        ):
            cards = build_domain_trend_cards(
                _Session(),
                business_domain="apple_computer",
                window_days=30,
                heartbeat_days=7,
                pricing_records=[{"item_id": "item-1"}],
                pricing_contract={"templateCompleteness": {"isComplete": True}},
                filtered_item_ids={"item-1"},
            )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["trend_points"][0]["date_label"], "03-01")
        self.assertEqual(cards[0]["trend_points"][-1]["date_label"], "04-05")

    def test_build_domain_trend_cards_respects_template_key_preview(self) -> None:
        item_one = SimpleNamespace(item_id="item-1")
        item_two = SimpleNamespace(item_id="item-2")
        snapshot_rows = [
            SimpleNamespace(
                item_id="item-1",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 3, 1, tzinfo=UTC),
                price=3840.0,
            ),
            SimpleNamespace(
                item_id="item-2",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 3, 10, tzinfo=UTC),
                price=5120.0,
            ),
            SimpleNamespace(
                item_id="item-1",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 4, 5, tzinfo=UTC),
                price=3920.0,
            ),
            SimpleNamespace(
                item_id="item-2",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 4, 8, tzinfo=UTC),
                price=5240.0,
            ),
        ]

        class _Result:
            def __init__(self, rows) -> None:
                self._rows = rows

            def all(self):
                return self._rows

        class _Session:
            def __init__(self) -> None:
                self._calls = 0

            def execute(self, _stmt):
                self._calls += 1
                if self._calls == 1:
                    return _Result([(item_one, None), (item_two, None)])
                if self._calls == 2:
                    return _Result(snapshot_rows)
                raise AssertionError("unexpected execute call")

        template_key = (
            "apple_computer|model_name=Mac mini / M4|chip_family=M4|memory_gb=16|storage_gb=256"
        )
        with patch(
            "goofish_insight.application.services.dashboard_queries.resolve_pricing_record",
            side_effect=[
                {
                    "item_id": "item-1",
                    "business_domain": "apple_computer",
                    "product_label": "Mac mini / M4",
                    "product_line": "Mac mini",
                    "title": "item one",
                    "chip_family": "M4",
                    "memory_gb": 16,
                    "storage_gb": 256,
                },
                {
                    "item_id": "item-2",
                    "business_domain": "apple_computer",
                    "product_label": "Mac mini / M4",
                    "product_line": "Mac mini",
                    "title": "item two",
                    "chip_family": "M4",
                    "memory_gb": 32,
                    "storage_gb": 512,
                },
            ],
        ), patch(
            "goofish_insight.application.services.dashboard_queries.select_trend_focus_groups",
            return_value=[
                {
                    "business_domain": "apple_computer",
                    "product_label": "Mac mini / M4",
                    "listing_count": 8,
                    "seller_sample_count": 8,
                    "unique_seller_count": 4,
                    "exact_spec_ratio": 0.92,
                    "reliability_score": 90,
                    "latest_seen_at": datetime(2026, 4, 8, tzinfo=UTC),
                }
            ],
        ):
            cards = build_domain_trend_cards(
                _Session(),
                business_domain="apple_computer",
                window_days=30,
                heartbeat_days=7,
                pricing_records=[{"item_id": "item-1"}],
                pricing_contract={
                    "templateCompleteness": {"isComplete": True},
                    "templateKeyPreview": template_key,
                },
            )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["templateKey"], template_key)
        self.assertEqual(cards[0]["trend_points"][0]["date_label"], "03-01")
        self.assertEqual(cards[0]["trend_points"][-1]["date_label"], "04-05")
        self.assertEqual(cards[0]["templateSnapshotCoverageMode"], "fallback_item_template")
        self.assertEqual(cards[0]["pricingAvailability"]["availabilityTier"], "reference_only")
        self.assertEqual(
            cards[0]["pricingAvailabilitySummary"]["readinessSummary"],
            "仅参考：历史快照缺少模板归属，趋势暂不提供指导级口径",
        )

    def test_build_domain_trend_cards_uses_tagged_snapshot_template_key_for_guidance(self) -> None:
        item_one = SimpleNamespace(item_id="item-1")
        item_two = SimpleNamespace(item_id="item-2")
        template_key = (
            "apple_computer|model_name=Mac mini / M4|chip_family=M4|memory_gb=16|storage_gb=256"
        )
        snapshot_rows = [
            SimpleNamespace(
                item_id="item-1",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 3, 1, tzinfo=UTC),
                price=3840.0,
                extra_json={"template_key": template_key},
            ),
            SimpleNamespace(
                item_id="item-2",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 3, 10, tzinfo=UTC),
                price=5120.0,
                extra_json={
                    "template_key": "apple_computer|model_name=Mac mini / M4|chip_family=M4|memory_gb=32|storage_gb=512"
                },
            ),
            SimpleNamespace(
                item_id="item-1",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 4, 5, tzinfo=UTC),
                price=3920.0,
                extra_json={"template_key": template_key},
            ),
        ]

        class _Result:
            def __init__(self, rows) -> None:
                self._rows = rows

            def all(self):
                return self._rows

        class _Session:
            def __init__(self) -> None:
                self._calls = 0

            def execute(self, _stmt):
                self._calls += 1
                if self._calls == 1:
                    return _Result([(item_one, None), (item_two, None)])
                if self._calls == 2:
                    return _Result(snapshot_rows)
                raise AssertionError("unexpected execute call")

        with patch(
            "goofish_insight.application.services.dashboard_queries.resolve_pricing_record",
            side_effect=[
                {
                    "item_id": "item-1",
                    "business_domain": "apple_computer",
                    "product_label": "Mac mini / M4",
                    "product_line": "Mac mini",
                    "title": "item one",
                    "chip_family": "M4",
                    "memory_gb": 16,
                    "storage_gb": 256,
                },
                {
                    "item_id": "item-2",
                    "business_domain": "apple_computer",
                    "product_label": "Mac mini / M4",
                    "product_line": "Mac mini",
                    "title": "item two",
                    "chip_family": "M4",
                    "memory_gb": 32,
                    "storage_gb": 512,
                },
            ],
        ), patch(
            "goofish_insight.application.services.dashboard_queries.select_trend_focus_groups",
            return_value=[
                {
                    "business_domain": "apple_computer",
                    "product_label": "Mac mini / M4",
                    "listing_count": 8,
                    "seller_sample_count": 8,
                    "unique_seller_count": 4,
                    "exact_spec_ratio": 0.92,
                    "reliability_score": 90,
                    "latest_seen_at": datetime(2026, 4, 8, tzinfo=UTC),
                }
            ],
        ):
            cards = build_domain_trend_cards(
                _Session(),
                business_domain="apple_computer",
                window_days=30,
                heartbeat_days=7,
                pricing_records=[{"item_id": "item-1"}],
                pricing_contract={
                    "templateCompleteness": {"isComplete": True},
                    "templateKeyPreview": template_key,
                },
            )

        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["templateSnapshotCoverageMode"], "full_tagged")
        self.assertEqual(cards[0]["templateSnapshotTaggedCount"], 2)
        self.assertEqual(cards[0]["templateSnapshotFallbackCount"], 0)
        self.assertEqual(cards[0]["pricingAvailability"]["availabilityTier"], "guidance_ready")
        self.assertEqual(cards[0]["trend_points"][0]["date_label"], "03-01")

    def test_build_domain_trend_cards_reuses_pricing_records_without_history_scan(self) -> None:
        snapshot_rows = [
            SimpleNamespace(
                item_id="item-1",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 3, 1, tzinfo=UTC),
                price=3840.0,
                extra_json={"template_key": "apple_computer|model_name=Mac mini / M4|chip_family=M4|memory_gb=16|storage_gb=256"},
            ),
            SimpleNamespace(
                item_id="item-1",
                business_domain="apple_computer",
                snapshot_at=datetime(2026, 4, 5, tzinfo=UTC),
                price=3920.0,
                extra_json={"template_key": "apple_computer|model_name=Mac mini / M4|chip_family=M4|memory_gb=16|storage_gb=256"},
            ),
        ]

        class _Result:
            def __init__(self, rows) -> None:
                self._rows = rows

            def all(self):
                return self._rows

        class _Session:
            def __init__(self) -> None:
                self._calls = 0

            def execute(self, _stmt):
                self._calls += 1
                if self._calls == 1:
                    return _Result(snapshot_rows)
                raise AssertionError("unexpected execute call")

        pricing_records = [
            {
                "item_id": "item-1",
                "business_domain": "apple_computer",
                "product_label": "Mac mini / M4",
                "product_line": "Mac mini",
                "title": "item one",
                "chip_family": "M4",
                "memory_gb": 16,
                "storage_gb": 256,
            }
        ]
        template_key = "apple_computer|model_name=Mac mini / M4|chip_family=M4|memory_gb=16|storage_gb=256"

        with patch(
            "goofish_insight.application.services.dashboard_queries.select_trend_focus_groups",
            return_value=[
                {
                    "business_domain": "apple_computer",
                    "product_label": "Mac mini / M4",
                    "listing_count": 8,
                    "seller_sample_count": 8,
                    "unique_seller_count": 4,
                    "exact_spec_ratio": 0.92,
                    "reliability_score": 90,
                    "latest_seen_at": datetime(2026, 4, 8, tzinfo=UTC),
                }
            ],
        ), patch(
            "goofish_insight.application.services.dashboard_queries.resolve_pricing_record",
        ) as resolve_record_mock:
            cards = build_domain_trend_cards(
                _Session(),
                business_domain="apple_computer",
                window_days=30,
                heartbeat_days=7,
                pricing_records=pricing_records,
                pricing_contract={
                    "templateCompleteness": {"isComplete": True},
                    "templateKeyPreview": template_key,
                },
            )

        resolve_record_mock.assert_not_called()
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["trend_points"][0]["date_label"], "03-01")
        self.assertEqual(cards[0]["trend_points"][-1]["date_label"], "04-05")

    def test_summarize_trend_quality_rejects_sparse_recent_samples(self) -> None:
        quality = summarize_trend_quality(
            [
                {"sample_count": 10},
                {"sample_count": 9},
                {"sample_count": 8},
                {"sample_count": 1},
            ]
        )

        self.assertEqual(quality["latest_sample_count"], 1)
        self.assertFalse(quality["trend_quality_ok"])

    def test_select_final_trend_cards_prefers_quality_cards(self) -> None:
        cards = select_final_trend_cards(
            cards=[
                {
                    "business_domain": "garmin",
                    "label": "Forerunner 265",
                    "trend_quality_ok": False,
                    "recent_average_sample_count": 1.3,
                    "latest_sample_count": 1,
                    "seller_sample_count": 200,
                    "reliability_score": 88.0,
                    "day_count": 6,
                },
                {
                    "business_domain": "garmin",
                    "label": "Fenix 8",
                    "trend_quality_ok": True,
                    "recent_average_sample_count": 47.0,
                    "latest_sample_count": 15,
                    "seller_sample_count": 214,
                    "reliability_score": 89.0,
                    "day_count": 6,
                },
                {
                    "business_domain": "garmin",
                    "label": "Instinct",
                    "trend_quality_ok": True,
                    "recent_average_sample_count": 36.0,
                    "latest_sample_count": 18,
                    "seller_sample_count": 382,
                    "reliability_score": 90.0,
                    "day_count": 6,
                },
            ],
            business_domain=None,
        )

        self.assertEqual([card["label"] for card in cards], ["Fenix 8", "Instinct"])

    def test_select_trend_focus_groups_limits_each_domain_when_showing_all(self) -> None:
        rows = select_trend_focus_groups(
            pricing_records=[
                {
                    "business_domain": "apple_m_series",
                    "brand": "Apple",
                    "product_label": "Mac mini / M4",
                    "title": "a",
                    "item_id": "a1",
                    "price": 3999,
                    "seller_key": "s1",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "Mac mini",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
                {
                    "business_domain": "apple_m_series",
                    "brand": "Apple",
                    "product_label": "Mac mini / M4",
                    "title": "b",
                    "item_id": "a2",
                    "price": 4099,
                    "seller_key": "s2",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "Mac mini",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
                {
                    "business_domain": "apple_m_series",
                    "brand": "Apple",
                    "product_label": "MacBook Pro / 14in / M3",
                    "title": "c",
                    "item_id": "a3",
                    "price": 8999,
                    "seller_key": "s3",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "MacBook Pro",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
                {
                    "business_domain": "apple_m_series",
                    "brand": "Apple",
                    "product_label": "MacBook Pro / 14in / M3",
                    "title": "d",
                    "item_id": "a4",
                    "price": 9199,
                    "seller_key": "s4",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "MacBook Pro",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
                {
                    "business_domain": "apple_m_series",
                    "brand": "Apple",
                    "product_label": "MacBook Air / 13in / M2",
                    "title": "e",
                    "item_id": "a5",
                    "price": 4999,
                    "seller_key": "s5",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "MacBook Air",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
                {
                    "business_domain": "apple_m_series",
                    "brand": "Apple",
                    "product_label": "MacBook Air / 13in / M2",
                    "title": "f",
                    "item_id": "a6",
                    "price": 5199,
                    "seller_key": "s6",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "MacBook Air",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
                {
                    "business_domain": "garmin",
                    "brand": "Garmin",
                    "product_label": "Fenix 8",
                    "title": "g",
                    "item_id": "g1",
                    "price": 3200,
                    "seller_key": "g1",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "Fenix",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
                {
                    "business_domain": "garmin",
                    "brand": "Garmin",
                    "product_label": "Fenix 8",
                    "title": "h",
                    "item_id": "g2",
                    "price": 3300,
                    "seller_key": "g2",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "Fenix",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
                {
                    "business_domain": "garmin",
                    "brand": "Garmin",
                    "product_label": "Instinct 2",
                    "title": "i",
                    "item_id": "g3",
                    "price": 1500,
                    "seller_key": "g3",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "Instinct",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
                {
                    "business_domain": "garmin",
                    "brand": "Garmin",
                    "product_label": "Instinct 2",
                    "title": "j",
                    "item_id": "g4",
                    "price": 1550,
                    "seller_key": "g4",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "Instinct",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
                {
                    "business_domain": "garmin",
                    "brand": "Garmin",
                    "product_label": "Tactix 8",
                    "title": "k",
                    "item_id": "g5",
                    "price": 6200,
                    "seller_key": "g5",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "Tactix",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
                {
                    "business_domain": "garmin",
                    "brand": "Garmin",
                    "product_label": "Tactix 8",
                    "title": "l",
                    "item_id": "g6",
                    "price": 6250,
                    "seller_key": "g6",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "Tactix",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                },
            ],
            business_domain=None,
        )

        self.assertEqual(len(rows), 6)
        self.assertEqual(sum(1 for row in rows if row["business_domain"] == "apple_computer"), 3)
        self.assertEqual(sum(1 for row in rows if row["business_domain"] == "garmin_watch"), 3)
        self.assertTrue(
            {row["product_label"] for row in rows}.issubset(
                {
                    "Mac mini / M4",
                    "MacBook Pro / 14in / M3",
                    "MacBook Air / 13in / M2",
                    "Fenix 8",
                    "Instinct 2",
                    "Tactix 8",
                }
            )
        )

    def test_select_trend_focus_groups_expands_within_selected_domain(self) -> None:
        pricing_records = []
        for index in range(10):
            pricing_records.append(
                {
                    "business_domain": "apple_m_series",
                    "brand": "Apple",
                    "product_label": f"Group {index}",
                    "title": f"title {index}",
                    "item_id": f"item-{index}",
                    "price": 1000 + index * 50,
                    "seller_key": f"seller-{index}",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "MacBook Air",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                }
            )
            pricing_records.append(
                {
                    "business_domain": "apple_m_series",
                    "brand": "Apple",
                    "product_label": f"Group {index}",
                    "title": f"title {index}-2",
                    "item_id": f"item-{index}-2",
                    "price": 1100 + index * 50,
                    "seller_key": f"seller-{index}-2",
                    "last_seen_at": datetime(2026, 3, 31, 0, 0, tzinfo=UTC),
                    "first_seen_at": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "publish_time": datetime(2026, 3, 28, 0, 0, tzinfo=UTC),
                    "product_line": "MacBook Air",
                    "exact_spec_ready": True,
                    "spec_confidence": 0.9,
                }
            )

        rows = select_trend_focus_groups(
            pricing_records=pricing_records,
            business_domain="apple_m_series",
        )

        self.assertEqual(len(rows), 10)

    def test_build_mobile_market_calibration_panel_reads_latest_queue_and_compares_prices(self) -> None:
        with TemporaryDirectory() as temp_dir:
            bulk_dir = Path(temp_dir) / "mobile-market-bulk"
            bulk_dir.mkdir(parents=True, exist_ok=True)

            report_path = bulk_dir / "garmin:forerunner-265-test.json"
            report_path.write_text(
                """
                {
                  "captured_at": "2026-04-02T00:59:40+00:00",
                  "query": "forerunner265",
                  "recent_avg_price_7d": null,
                  "sold_price_range_low": 1380,
                  "sold_price_range_high": 1380,
                  "visible_records": [
                    {
                      "title": "99新 Garmin 佳明 Forerunner 265",
                      "sold_price": 1380
                    }
                  ]
                }
                """.strip(),
                encoding="utf-8",
            )
            (bulk_dir / "queue-state-all.json").write_text(
                json.dumps(
                    {
                        "tasks": [
                            {
                                "task_id": "garmin:forerunner-265",
                                "business_domain": "garmin",
                                "model_name": "Forerunner 265",
                                "status": "done",
                                "last_output_path": str(report_path),
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            top_models = [
                {
                    "business_domain": "garmin",
                    "domain_label": "Garmin手表",
                    "model_name": "Forerunner 265",
                    "listing_count": 415,
                    "seller_count": 321,
                    "avg_price": 1600.0,
                    "last_seen_at": datetime(2026, 4, 2, 0, 0, tzinfo=UTC),
                }
            ]

            with patch(
                "goofish_insight.application.services.mobile_market_dashboard.MOBILE_MARKET_REPORTS_DIR",
                bulk_dir,
            ):
                panel = build_mobile_market_calibration_panel(
                    business_domain=None,
                    top_models=top_models,
                )

        self.assertTrue(panel["available"])
        self.assertEqual(panel["captured_model_count"], 1)
        self.assertEqual(panel["comparison_ready_count"], 1)
        self.assertEqual(panel["visible_record_total"], 1)
        self.assertEqual(panel["rows"][0]["sold_anchor_price"], 1380)
        self.assertEqual(panel["rows"][0]["calibration_label"], "挂牌略高")
        self.assertEqual(panel["rows"][0]["calibration_class"], "warm")
        self.assertEqual(panel["rows"][0]["calibration_detail"], "较真实成交 +15.9% / +¥220")

    def test_merge_mobile_market_into_top_models_attaches_matching_rows(self) -> None:
        top_models = [
            {
                "business_domain": "garmin",
                "model_name": "Forerunner 265",
                "listing_count": 415,
                "seller_count": 321,
                "avg_price": 1600.0,
                "last_seen_at": datetime(2026, 4, 2, 0, 0, tzinfo=UTC),
            },
            {
                "business_domain": "apple_m_series",
                "model_name": "Mac mini M4",
                "listing_count": 100,
                "seller_count": 80,
                "avg_price": 3999.0,
                "last_seen_at": datetime(2026, 4, 2, 0, 0, tzinfo=UTC),
            },
        ]
        mobile_rows = [
            {
                "business_domain": "garmin",
                "model_name": "Forerunner 265",
                "sold_anchor_price": 1380,
                "calibration_label": "挂牌略高",
            }
        ]

        merged = merge_mobile_market_into_top_models(top_models, mobile_rows)

        self.assertEqual(merged[0]["mobile_calibration"]["sold_anchor_price"], 1380)
        self.assertIsNone(merged[1]["mobile_calibration"])


if __name__ == "__main__":
    unittest.main()
