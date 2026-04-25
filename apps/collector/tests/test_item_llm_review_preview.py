from __future__ import annotations

import json
import unittest
from pathlib import Path

from goofish_insight.application.services.review_batches import (
    BatchReviewResult,
    build_preclassified_review_entries,
    build_review_system_prompt,
    build_review_user_prompt,
    extract_json_array,
    normalize_review_entries,
    sanitize_review_response,
)
from goofish_insight.application.services.review_output_artifacts import build_usage_sidecar_path, summarize_llm_usage
from goofish_insight.application.services.review_ingest import (
    build_intake_screening_user_prompt,
    contains_suspicious_listing_keyword,
    sanitize_intake_screening_response,
)
from goofish_insight.application.services.review_queries import serialize_review_row


class ItemLlmReviewPreviewTests(unittest.TestCase):
    def test_review_prompts_require_exact_item_ids(self) -> None:
        system_prompt = build_review_system_prompt()
        user_prompt = build_review_user_prompt(
            batch=[
                {
                    "item_id": "abc123",
                    "business_domain": "apple_m_series",
                    "title": "MacBook Pro",
                    "current_price": 9999,
                    "source_keyword": "macbook pro",
                    "condition_tags": [],
                    "region": "Shanghai",
                    "listing_description": None,
                    "listing_description_length": 0,
                    "current_values": {},
                    "rule_candidate": {},
                }
            ]
        )

        self.assertIn("item_id is a locked opaque string", system_prompt)
        self.assertIn("Copy each item_id exactly from the input", system_prompt)
        self.assertIn('invalid_reason must be ""', system_prompt)
        self.assertIn("probability that the listing is a real target-device sale listing", system_prompt)
        self.assertIn("\"item_id_rule\":\"item_id must be copied exactly from input", user_prompt)
        self.assertIn("\"input_item_ids\":[\"abc123\"]", user_prompt)

    def test_review_user_prompt_keeps_only_required_snapshot_fields(self) -> None:
        user_prompt = build_review_user_prompt(
            batch=[
                {
                    "item_id": "abc123",
                    "business_domain": "apple_m_series",
                    "title": "MacBook Pro M3 Pro 18G 512G",
                    "current_price": 9999,
                    "source_keyword": "macbook pro",
                    "condition_tags": ["95新"],
                    "region": "Shanghai",
                    "listing_description": "箱说全，轻微使用痕迹",
                    "listing_description_length": 11,
                    "current_values": {"spec.memory_gb": 18},
                    "rule_candidate": {"status": "partial"},
                }
            ]
        )

        payload = json.loads(user_prompt)

        self.assertEqual(payload["input_item_ids"], ["abc123"])
        self.assertEqual(
            payload["items"][0],
            {
                "item_id": "abc123",
                "d": "apple_m_series",
                "t": "MacBook Pro M3 Pro 18G 512G",
                "p": 9999,
                "k": "macbook pro",
                "tags": ["95新"],
                "desc": "箱说全，轻微使用痕迹",
                "cur": {"spec.memory_gb": 18},
            },
        )
        self.assertNotIn("r", payload["items"][0])
        self.assertNotIn("desc_len", payload["items"][0])
        self.assertNotIn("rule", payload["items"][0])

    def test_review_user_prompt_drops_oversized_current_value_text(self) -> None:
        user_prompt = build_review_user_prompt(
            batch=[
                {
                    "item_id": "garmin-1",
                    "business_domain": "garmin_watch",
                    "title": "Fenix 8 51mm",
                    "current_price": 5300,
                    "source_keyword": "fenix 8",
                    "condition_tags": [],
                    "region": "Shanghai",
                    "listing_description": None,
                    "listing_description_length": 0,
                    "current_values": {
                        "item.normalized_model": "飞耐时8，51，户外运动手表，支持GPS定位、心率监测，运动模式多，续航强，屏幕显示正常，功能都好用。包邮，可自提。带原厂皮带",
                        "item.normalized_brand": "Garmin",
                        "spec.memory_gb": None,
                    },
                    "rule_candidate": {},
                }
            ]
        )

        payload = json.loads(user_prompt)

        self.assertEqual(payload["items"][0]["cur"], {"item.normalized_brand": "Garmin"})
        self.assertNotIn("item.normalized_model", payload["items"][0]["cur"])

    def test_sanitize_review_response_repairs_single_item_id_drift(self) -> None:
        batch = [
            {
                "item_id": "1032946354057",
                "business_domain": "garmin",
                "title": "Garmin Fenix 8",
                "current_price": 5199,
                "source_keyword": "fenix 8",
                "condition_tags": [],
                "region": None,
                "current_values": {},
                "rule_candidate": {},
            }
        ]
        raw_items = [
            {
                "item_id": "9991032946354057",
                "review_status": "valid",
                "confidence": 0.95,
                "not_match_field": [],
            }
        ]

        sanitized, metrics = sanitize_review_response(raw_items=raw_items, batch=batch)

        self.assertEqual(metrics["low_confidence_filtered_count"], 0)
        self.assertEqual(len(sanitized), 1)
        self.assertEqual(sanitized[0]["item_id"], "1032946354057")
        self.assertEqual(sanitized[0]["review_status"], "valid")

    def test_sanitize_review_response_uses_request_item_id_when_single_item_has_no_model_id(self) -> None:
        batch = [
            {
                "item_id": "1032946354057",
                "business_domain": "garmin",
                "title": "Garmin Fenix 8",
                "current_price": 5199,
                "source_keyword": "fenix 8",
                "condition_tags": [],
                "region": None,
                "current_values": {},
                "rule_candidate": {},
            }
        ]
        raw_items = [
            {
                "review_status": "valid",
                "confidence": 0.95,
                "not_match_field": [],
            }
        ]

        sanitized, metrics = sanitize_review_response(raw_items=raw_items, batch=batch)

        self.assertEqual(metrics["low_confidence_filtered_count"], 0)
        self.assertEqual(len(sanitized), 1)
        self.assertEqual(sanitized[0]["item_id"], "1032946354057")

    def test_extract_json_array_accepts_fenced_payload(self) -> None:
        payload = """```json
        [{"item_id":"abc","not_match_field":[{"field_key":"spec.case_size_mm","true_value":47}]}]
        ```"""
        parsed = extract_json_array(payload)
        self.assertEqual(parsed[0]["item_id"], "abc")

    def test_sanitize_review_response_keeps_only_changed_allowed_fields(self) -> None:
        batch = [
            {
                "item_id": "abc",
                "business_domain": "garmin",
                "title": "Garmin Fenix 8",
                "current_price": 5199,
                "source_keyword": "fenix 8",
                "condition_tags": ["95新"],
                "region": "Shanghai",
                "current_values": {
                    "spec.case_size_mm": 51,
                    "spec.display_type": "MIP",
                    "item.normalized_model": "Forerunner 965",
                },
                "rule_candidate": {
                    "model_name": "Fenix 8",
                    "display_type": "MIP",
                },
            }
        ]
        raw_items = [
            {
                "item_id": "abc",
                "confidence": 0.96,
                "not_match_field": [
                    {"field_key": "spec.case_size_mm", "true_value": 47},
                    {"field_key": "spec.display_type", "true_value": "amoled"},
                    {"field_key": "item.normalized_model", "true_value": "Forerunner 965"},
                    {"field_key": "spec.unknown_field", "true_value": "x"},
                ],
            }
        ]

        sanitized, metrics = sanitize_review_response(raw_items=raw_items, batch=batch)

        self.assertEqual(len(sanitized), 1)
        self.assertEqual(metrics["garbage_hit_count"], 0)
        self.assertEqual(metrics["low_confidence_filtered_count"], 0)
        self.assertEqual(sanitized[0]["item_id"], "abc")
        self.assertEqual(sanitized[0]["review_status"], "valid")
        self.assertEqual(sanitized[0]["confidence"], 0.96)
        self.assertEqual(
            sanitized[0]["not_match_field"],
            [
                {"field_key": "spec.case_size_mm", "true_value": 47},
                {"field_key": "spec.display_type", "true_value": "AMOLED"},
            ],
        )
        self.assertEqual(sanitized[0]["review_input"]["item_id"], "abc")
        self.assertEqual(sanitized[0]["review_input"]["d"], "garmin")
        self.assertNotIn("t", sanitized[0]["review_input"])
        self.assertTrue(sanitized[0]["review_input_signature"])

    def test_sanitize_review_response_drops_low_confidence_entries(self) -> None:
        batch = [
            {
                "item_id": "abc",
                "business_domain": "garmin",
                "title": "Garmin Fenix 8",
                "current_price": 5199,
                "source_keyword": "fenix 8",
                "condition_tags": [],
                "region": None,
                "current_values": {
                    "spec.case_size_mm": 51,
                },
                "rule_candidate": {},
            }
        ]
        raw_items = [
            {
                "item_id": "abc",
                "confidence": 0.61,
                "not_match_field": [
                    {"field_key": "spec.case_size_mm", "true_value": 47},
                ],
            }
        ]

        sanitized, metrics = sanitize_review_response(raw_items=raw_items, batch=batch)

        self.assertEqual(sanitized, [])
        self.assertEqual(metrics["garbage_hit_count"], 0)
        self.assertEqual(metrics["low_confidence_filtered_count"], 1)

    def test_sanitize_review_response_accepts_strong_invalid_entries(self) -> None:
        batch = [
            {
                "item_id": "abc",
                "business_domain": "garmin",
                "title": "佳明 fenix 8 求购",
                "current_price": 5199,
                "source_keyword": "fenix 8",
                "condition_tags": [],
                "region": None,
                "current_values": {},
                "rule_candidate": {},
            }
        ]
        raw_items = [
            {
                "item_id": "abc",
                "confidence": 0.12,
                "review_status": "invalid",
                "invalid_reason": "recycling",
                "not_match_field": [],
            }
        ]

        sanitized, metrics = sanitize_review_response(raw_items=raw_items, batch=batch)

        self.assertEqual(metrics["garbage_hit_count"], 0)
        self.assertEqual(metrics["low_confidence_filtered_count"], 0)
        self.assertEqual(len(sanitized), 1)
        self.assertEqual(sanitized[0]["review_status"], "invalid")
        self.assertEqual(sanitized[0]["invalid_reason"], "recycling")
        self.assertEqual(sanitized[0]["confidence"], 0.12)

    def test_sanitize_review_response_counts_low_confidence_once_per_item(self) -> None:
        batch = [
            {
                "item_id": "abc",
                "business_domain": "garmin",
                "title": "Garmin Fenix 8",
                "current_price": 5199,
                "source_keyword": "fenix 8",
                "condition_tags": [],
                "region": None,
                "current_values": {},
                "rule_candidate": {},
            }
        ]
        raw_items = [
            {
                "item_id": "abc",
                "confidence": 0.41,
                "review_status": "valid",
                "not_match_field": [],
            },
            {
                "item_id": "abc",
                "confidence": 0.32,
                "review_status": "invalid",
                "invalid_reason": "other",
                "not_match_field": [],
            },
        ]

        sanitized, metrics = sanitize_review_response(raw_items=raw_items, batch=batch)

        self.assertEqual(sanitized, [])
        self.assertEqual(metrics["low_confidence_filtered_count"], 1)

    def test_build_preclassified_review_entries_invalidates_long_listing_description(self) -> None:
        batch = [
            {
                "item_id": "abc",
                "business_domain": "apple_m_series",
                "title": "MacBook Air M2 16GB 512GB",
                "current_price": 6200,
                "source_keyword": "macbook air m2",
                "condition_tags": [],
                "region": "Shanghai",
                "listing_description": "长描" * 201,
                "listing_description_length": 402,
                "current_values": {},
                "rule_candidate": {},
            }
        ]

        entries, remaining_batch = build_preclassified_review_entries(batch=batch)

        self.assertEqual(remaining_batch, [])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["item_id"], "abc")
        self.assertEqual(entries[0]["review_status"], "invalid")
        self.assertEqual(entries[0]["invalid_reason"], "garbage")
        self.assertEqual(entries[0]["confidence"], 1.0)
        self.assertEqual(entries[0]["review_input"]["item_id"], "abc")
        self.assertEqual(entries[0]["review_input"]["desc"], "长描" * 201)
        self.assertNotIn("t", entries[0]["review_input"])
        self.assertNotIn("desc_len", entries[0]["review_input"])
        self.assertTrue(entries[0]["review_input_signature"])

    def test_normalize_review_entries_strips_title_from_legacy_review_input(self) -> None:
        entries = normalize_review_entries(
            [
                {
                    "item_id": "abc",
                    "review_status": "valid",
                    "not_match_field": [],
                    "review_input": {
                        "item_id": "abc",
                        "d": "apple_m_series",
                        "t": "MacBook Air M2 16G 512G",
                        "r": "Shanghai",
                        "desc": "自用出售，M2，16G+512G，价格可聊",
                        "rule": {"status": "partial"},
                    },
                    "review_input_signature": "legacy-signature",
                }
            ]
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(
            entries[0]["review_input"],
            {
                "item_id": "abc",
                "d": "apple_m_series",
                "desc": "自用出售，M2，16G+512G，价格可聊",
            },
        )
        self.assertNotIn("t", entries[0]["review_input"])
        self.assertNotIn("r", entries[0]["review_input"])
        self.assertNotIn("rule", entries[0]["review_input"])
        self.assertNotEqual(entries[0]["review_input_signature"], "legacy-signature")
        self.assertEqual(len(entries[0]["review_input_signature"]), 64)

    def test_build_preclassified_review_entries_invalidates_buyback_style_listing(self) -> None:
        batch = [
            {
                "item_id": "buyback-1",
                "business_domain": "apple_m_series",
                "title": "macmini m4主机，M4芯片，16G+256G，300 0收个在保的，过保的也能聊聊，慢收，边收边等mac mini m5。支持上门服务~ 价格好说，诚心卖可以聊聊！有闲置的朋友欢迎骚扰。收收收",
                "current_price": 3000,
                "source_keyword": "mac mini m4",
                "condition_tags": [],
                "region": "Shanghai",
                "current_values": {},
                "rule_candidate": {},
            }
        ]

        entries, remaining_batch = build_preclassified_review_entries(batch=batch)

        self.assertEqual(remaining_batch, [])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["item_id"], "buyback-1")
        self.assertEqual(entries[0]["review_status"], "invalid")
        self.assertEqual(entries[0]["invalid_reason"], "recycling")
        self.assertEqual(entries[0]["confidence"], 1.0)

    def test_build_preclassified_review_entries_invalidates_subsidy_service_listing(self) -> None:
        batch = [
            {
                "item_id": "subsidy-1",
                "business_domain": "apple_m_series",
                "title": "MacBook Pro 国补资格 名额代申领，教育优惠员工价，不支持直接拍，先私聊",
                "current_price": 88,
                "source_keyword": "macbook pro",
                "condition_tags": [],
                "region": "Shanghai",
                "current_values": {},
                "rule_candidate": {},
            }
        ]

        entries, remaining_batch = build_preclassified_review_entries(batch=batch)

        self.assertEqual(remaining_batch, [])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["review_status"], "invalid")
        self.assertEqual(entries[0]["invalid_reason"], "service")

    def test_build_preclassified_review_entries_invalidates_non_device_listing(self) -> None:
        batch = [
            {
                "item_id": "non-device-1",
                "business_domain": "apple_m_series",
                "title": "Mac mini M4 空盒 包装盒 单出",
                "current_price": 66,
                "source_keyword": "mac mini m4",
                "condition_tags": [],
                "region": "Shanghai",
                "current_values": {},
                "rule_candidate": {},
            }
        ]

        entries, remaining_batch = build_preclassified_review_entries(batch=batch)

        self.assertEqual(remaining_batch, [])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["review_status"], "invalid")
        self.assertEqual(entries[0]["invalid_reason"], "garbage")

    def test_build_preclassified_review_entries_does_not_block_listing_without_box(self) -> None:
        batch = [
            {
                "item_id": "no-box-1",
                "business_domain": "apple_m_series",
                "title": "Mac mini M4 裸机无包装盒，机器正常出售",
                "current_price": 2999,
                "source_keyword": "mac mini m4",
                "condition_tags": [],
                "region": "Shanghai",
                "current_values": {},
                "rule_candidate": {},
            }
        ]

        entries, remaining_batch = build_preclassified_review_entries(batch=batch)

        self.assertEqual(entries, [])
        self.assertEqual(len(remaining_batch), 1)

    def test_build_preclassified_review_entries_does_not_block_normal_private_chat_sale(self) -> None:
        batch = [
            {
                "item_id": "private-chat-1",
                "business_domain": "garmin",
                "title": "Garmin Fenix 8 47mm 个人闲置，支持自提，价格可聊，细节私聊发图",
                "current_price": 4999,
                "source_keyword": "fenix 8",
                "condition_tags": [],
                "region": "Shanghai",
                "current_values": {"item.normalized_brand": "Garmin"},
                "rule_candidate": {},
            }
        ]

        entries, remaining_batch = build_preclassified_review_entries(batch=batch)

        self.assertEqual(entries, [])
        self.assertEqual(len(remaining_batch), 1)

    def test_build_preclassified_review_entries_invalidates_commercial_multi_variant_listing(self) -> None:
        batch = [
            {
                "item_id": "commercial-1",
                "business_domain": "garmin",
                "title": "【可置换】GARMIN佳明飞耐时 Fenix 7x Pro epix Pro 42 47 51MM 全新未拆封国行中文版原装正品，全国顺丰包邮到家，7 Pro 精英版 6480 7 Pro 旗舰版 6980",
                "current_price": 6480,
                "source_keyword": "fenix 7x pro",
                "condition_tags": [],
                "region": "Shanghai",
                "current_values": {},
                "rule_candidate": {},
            }
        ]

        entries, remaining_batch = build_preclassified_review_entries(batch=batch)

        self.assertEqual(remaining_batch, [])
        self.assertEqual(entries[0]["review_status"], "invalid")
        self.assertEqual(entries[0]["invalid_reason"], "ad")

    def test_build_preclassified_review_entries_invalidates_promo_bulk_listing(self) -> None:
        batch = [
            {
                "item_id": "promo-1",
                "business_domain": "garmin",
                "title": "佳明618活动来袭，超值特惠，速来选购，全系列全新现货发，顺丰包邮，全国联保，错过等一年",
                "current_price": 6180,
                "source_keyword": "garmin",
                "condition_tags": [],
                "region": "Shanghai",
                "current_values": {},
                "rule_candidate": {},
            }
        ]

        entries, remaining_batch = build_preclassified_review_entries(batch=batch)

        self.assertEqual(remaining_batch, [])
        self.assertEqual(entries[0]["review_status"], "invalid")
        self.assertEqual(entries[0]["invalid_reason"], "ad")

    def test_summarize_llm_usage_accumulates_per_batch_usage(self) -> None:
        results = [
            BatchReviewResult(
                batch_size=6,
                review_count=5,
                entries=[],
                llm_request_count=1,
                llm_usage={
                    "input_tokens": 1200,
                    "output_tokens": 100,
                    "total_tokens": 1300,
                    "cached_tokens": 300,
                },
                garbage_hit_count=2,
                low_confidence_filtered_count=4,
                high_confidence_kept_count=5,
            ),
            BatchReviewResult(
                batch_size=6,
                review_count=2,
                entries=[],
                llm_request_count=0,
                llm_usage=None,
                garbage_hit_count=0,
                low_confidence_filtered_count=1,
                high_confidence_kept_count=2,
            ),
        ]

        summary = summarize_llm_usage(
            results=results,
            requested_item_count=12,
            batch_size=6,
            concurrency=10,
        )

        self.assertEqual(summary["requested_item_count"], 12)
        self.assertEqual(summary["llm_request_count"], 1)
        self.assertEqual(
            summary["total_usage"],
            {
                "input_tokens": 1200,
                "output_tokens": 100,
                "total_tokens": 1300,
                "cached_tokens": 300,
                "garbage_hit_count": 2,
                "low_confidence_filtered_count": 5,
                "high_confidence_kept_count": 7,
            },
        )
        self.assertEqual(summary["batches"][0]["llm_usage"]["input_tokens"], 1200)
        self.assertIsNone(summary["batches"][1]["llm_usage"])

    def test_build_usage_sidecar_path_preserves_output_directory(self) -> None:
        path = build_usage_sidecar_path(Path("/tmp/review-ark-live.json"))
        self.assertEqual(str(path), "/tmp/review-ark-live.usage.json")

    def test_build_preclassified_review_entries_invalidates_service_listing(self) -> None:
        batch = [
            {
                "item_id": "svc",
                "business_domain": "apple_m_series",
                "title": "MacBook Pro 代下单服务 需要私聊",
                "current_price": 66,
                "source_keyword": "macbook pro",
                "condition_tags": [],
                "region": "Shanghai",
                "listing_description": None,
                "listing_description_length": 0,
                "current_values": {},
                "rule_candidate": {},
            }
        ]

        entries, remaining_batch = build_preclassified_review_entries(batch=batch)

        self.assertEqual(remaining_batch, [])
        self.assertEqual(entries[0]["review_status"], "invalid")
        self.assertEqual(entries[0]["invalid_reason"], "service")

    def test_build_preclassified_review_entries_invalidates_garbage_listing(self) -> None:
        batch = [
            {
                "item_id": "garbage",
                "business_domain": "garmin",
                "title": "!!!？？？！！！",
                "current_price": 1,
                "source_keyword": "fenix",
                "condition_tags": [],
                "region": "Shanghai",
                "listing_description": "哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈哈",
                "listing_description_length": 20,
                "current_values": {},
                "rule_candidate": {},
            }
        ]

        entries, remaining_batch = build_preclassified_review_entries(batch=batch)

        self.assertEqual(remaining_batch, [])
        self.assertEqual(entries[0]["review_status"], "invalid")
        self.assertEqual(entries[0]["invalid_reason"], "garbage")

    def test_build_preclassified_review_entries_keeps_real_listing_with_charger_mention(self) -> None:
        batch = [
            {
                "item_id": "real-item",
                "business_domain": "apple_m_series",
                "title": "苹果 MacBook Pro 14寸 M5 带原装充电器和盒子",
                "current_price": 9800,
                "source_keyword": "macbook pro 14",
                "condition_tags": [],
                "region": "Shanghai",
                "listing_description": None,
                "listing_description_length": 0,
                "current_values": {"item.normalized_brand": "Apple"},
                "rule_candidate": {},
            }
        ]

        entries, remaining_batch = build_preclassified_review_entries(batch=batch)

        self.assertEqual(entries, [])
        self.assertEqual(len(remaining_batch), 1)

    def test_normalize_review_entries_merges_duplicate_fields(self) -> None:
        raw_items = [
            {
                "item_id": "abc",
                "not_match_field": [
                    {"field_key": "spec.display_type", "true_value": "mip"},
                    {"field_key": "spec.display_type", "true_value": "amoled"},
                    {"field_key": "spec.unknown_field", "true_value": "x"},
                ],
            }
        ]

        normalized = normalize_review_entries(raw_items)

        self.assertEqual(
            normalized,
            [
                {
                    "item_id": "abc",
                    "review_status": "valid",
                    "invalid_reason": None,
                    "not_match_field": [
                        {"field_key": "spec.display_type", "true_value": "AMOLED"},
                    ],
                }
            ],
        )

    def test_normalize_review_entries_discards_invalid_typed_values(self) -> None:
        raw_items = [
            {
                "item_id": "abc",
                "not_match_field": [
                    {"field_key": "item.normalized_model", "true_value": 47},
                    {"field_key": "spec.case_size_mm", "true_value": "47mm"},
                    {"field_key": "spec.display_type", "true_value": "OLED"},
                    {"field_key": "spec.is_solar", "true_value": "maybe"},
                    {"field_key": "spec.case_size_mm", "true_value": 47},
                ],
            }
        ]

        normalized = normalize_review_entries(raw_items)

        self.assertEqual(
            normalized,
            [
                {
                    "item_id": "abc",
                    "review_status": "valid",
                    "invalid_reason": None,
                    "not_match_field": [
                        {"field_key": "spec.case_size_mm", "true_value": 47},
                    ],
                }
            ],
        )

    def test_normalize_review_entries_keeps_invalid_listing_classification(self) -> None:
        raw_items = [
            {
                "item_id": "abc",
                "review_status": "invalid",
                "invalid_reason": "electronic_parts",
                "not_match_field": [
                    {"field_key": "item.normalized_model", "true_value": "Mac Studio"},
                ],
            }
        ]

        normalized = normalize_review_entries(raw_items)

        self.assertEqual(
            normalized,
            [
                {
                    "item_id": "abc",
                    "review_status": "invalid",
                    "invalid_reason": "electronic_parts",
                    "not_match_field": [],
                }
            ],
        )

    def test_contains_suspicious_listing_keyword_checks_title(self) -> None:
        self.assertTrue(
            contains_suspicious_listing_keyword(
                title="高价回收 Mac Studio",
            )
        )
        self.assertTrue(
            contains_suspicious_listing_keyword(
                title="Mac Studio 抵押",
            )
        )
        self.assertFalse(
            contains_suspicious_listing_keyword(
                title="Mac Studio M1 Max",
            )
        )
        self.assertFalse(
            contains_suspicious_listing_keyword(
                title="佳明 Fenix 8 国行 带表带 支持置换回收",
            )
        )

    def test_intake_screening_prompt_does_not_include_title_tokens(self) -> None:
        prompt = build_intake_screening_user_prompt(
            batch=[
                {
                    "item_id": "abc",
                    "business_domain": "apple_computer",
                    "source_keyword": "mac m5",
                    "title": "高价回收 Mac Studio",
                    "current_price": 100,
                }
            ]
        )
        payload = json.loads(prompt)

        self.assertNotIn("title_tokens", prompt)
        self.assertIn("output_rule", prompt)
        self.assertNotIn("listing_url", prompt)
        self.assertNotIn("normalized_hints", prompt)
        self.assertEqual(
            payload["items"][0],
            {
                "item_id": "abc",
                "business_domain": "apple_computer",
                "source_keyword": "mac m5",
                "title": "高价回收 Mac Studio",
                "current_price": 100,
            },
        )

    def test_sanitize_intake_screening_response_accepts_only_high_confidence_valid(self) -> None:
        batch = [
            {"item_id": "valid-item"},
            {"item_id": "invalid-item"},
            {"item_id": "low-confidence-item"},
        ]
        raw_items = [
            {"item_id": "valid-item", "is_valid": True, "confidence": 0.96},
            {"item_id": "invalid-item", "review_status": "invalid", "invalid_reason": "pawn"},
            {"item_id": "low-confidence-item", "is_valid": True, "confidence": 0.61},
            {"item_id": "out-of-batch", "is_valid": True, "confidence": 0.99},
        ]

        sanitized = sanitize_intake_screening_response(raw_items=raw_items, batch=batch)

        self.assertEqual(
            sanitized,
            [
                {"item_id": "valid-item", "is_valid": True, "invalid_reason": None},
                {"item_id": "invalid-item", "is_valid": False, "invalid_reason": "pawn"},
                {"item_id": "low-confidence-item", "is_valid": False, "invalid_reason": "other"},
            ],
        )

    def test_serialize_review_row_extracts_listing_description_from_raw_response(self) -> None:
        item = type(
            "ItemStub",
            (),
            {
                "item_id": "abc",
                "business_domain": "apple_m_series",
                "source_platform": "xianyu",
                "source_keyword": "macbook air",
                "xianyu_cat_id": None,
                "xianyu_tb_cat_id": None,
                "xianyu_c_cat_id": None,
                "title": "MacBook Air M2",
                "current_price": 6200,
                "condition_tags": [],
                "region": "Shanghai",
                "normalized_brand": "Apple",
                "normalized_model_family": "MacBook Air",
                "normalized_model": "MacBook Air",
                "normalized_chip": "M2",
                "normalized_memory_gb": 16,
                "normalized_storage_gb": 512,
                "llm_reviewed": False,
                "llm_review_status": "pending",
                "llm_review_reason": None,
                "llm_review_confidence": None,
                "llm_review_needs_audit": False,
                "llm_review_audit_reason": None,
                "llm_review_input_signature": None,
                "llm_reviewed_at": None,
                "llm_review_input": {},
            },
        )()

        row = serialize_review_row(
            item=item,
            spec=None,
            raw_response_body={
                "data": {
                    "itemDO": {
                        "description": "这是一段足够长的商品描述。" * 8,
                    }
                }
            },
        )

        self.assertIn("商品描述", row["listing_description"])
        self.assertGreater(row["listing_description_length"], 40)


if __name__ == "__main__":
    unittest.main()
