from __future__ import annotations

import unittest

from goofish_insight.application.services.review_v3_profiles import (
    build_first_pass_batch_system_prompt,
    build_first_pass_batch_user_payload,
    build_first_pass_user_payload,
    build_first_pass_system_prompt,
    build_second_pass_user_payload,
    render_json_user_prompt,
    get_review_v3_profile,
)


class ReviewV3ProfilesTests(unittest.TestCase):
    def test_lens_first_pass_prompt_stays_flat(self) -> None:
        profile = get_review_v3_profile("camera_interchangeable_lens")
        assert profile is not None

        prompt = build_first_pass_system_prompt(profile)

        self.assertIn("is_main_product", prompt)
        self.assertIn("focal_length", prompt)
        self.assertIn("confidence_score", prompt)
        self.assertIn("spuAttributes", prompt)
        self.assertNotIn("model_catalog", prompt)
        self.assertIn("只提取原文明确支持的事实", prompt)

    def test_apple_first_pass_prompt_forbids_condition_hallucination(self) -> None:
        profile = get_review_v3_profile("apple_computer")
        assert profile is not None

        prompt = build_first_pass_system_prompt(profile)

        self.assertIn("不要复述标题或成色原文", prompt)
        self.assertIn("`is_flawless`", prompt)
        self.assertIn("如果容量、代际、尺寸、卡口等信息冲突，返回 null", prompt)

    def test_first_pass_user_payload_drops_nonessential_empty_fields(self) -> None:
        payload = build_first_pass_user_payload(
            item={
                "business_domain": "apple_computer",
                "item_id": "123",
                "title": "MacBook Pro M3 Pro 18G 512G",
                "condition_tags": [],
                "listing_description": None,
                "current_price": 9999,
                "source_keyword": "mac",
            }
        )

        self.assertEqual(payload["task"], "first_pass_feature_extraction")
        self.assertIn("title", payload)
        self.assertNotIn("current_price", payload)
        self.assertNotIn("source_keyword", payload)
        self.assertNotIn("listing_description", payload)
        self.assertNotIn("condition_tags", payload)

    def test_first_pass_user_payload_truncates_listing_description(self) -> None:
        payload = build_first_pass_user_payload(
            item={
                "business_domain": "phone",
                "item_id": "123",
                "title": "iPhone 16 256G",
                "condition_tags": ["几乎全新", "国行", "256GB", "蓝色"],
                "listing_description": "a" * 300,
            }
        )
        self.assertEqual(len(payload["listing_description"]), 160)
        self.assertEqual(payload["condition_tags"], ["几乎全新", "国行", "256GB"])

    def test_first_pass_batch_prompt_requires_items_array(self) -> None:
        profile = get_review_v3_profile("garmin_watch")
        assert profile is not None

        prompt = build_first_pass_batch_system_prompt(profile)

        self.assertIn('{"items":[...]}', prompt)
        self.assertIn("每个输入商品都必须输出一条结果", prompt)
        self.assertIn("item_id", prompt)

    def test_first_pass_batch_user_payload_serializes_multiple_items(self) -> None:
        payload = build_first_pass_batch_user_payload(
            business_domain="apple_computer",
            items=[
                {
                    "business_domain": "apple_computer",
                    "item_id": "1",
                    "title": "MacBook Pro M3 Pro 18G 512G",
                },
                {
                    "business_domain": "apple_computer",
                    "item_id": "2",
                    "title": "MacBook Air M5 24G 512G",
                    "listing_description": "个人自用闲置",
                },
            ],
        )

        self.assertEqual(payload["task"], "first_pass_feature_extraction_batch")
        self.assertEqual(payload["business_domain"], "apple_computer")
        self.assertEqual([entry["item_id"] for entry in payload["items"]], ["1", "2"])

    def test_render_json_user_prompt_is_compact(self) -> None:
        rendered = render_json_user_prompt({"a": 1, "b": {"c": 2}})
        self.assertEqual(rendered, '{"a":1,"b":{"c":2}}')

    def test_second_pass_payload_keeps_candidate_list(self) -> None:
        payload = build_second_pass_user_payload(
            item={"title": "尼康 z24-70s", "listing_description": "自用闲置", "condition_tags": ["几乎全新"]},
            first_pass_features={"brand": "尼康", "mount": "Z卡口"},
            catalog_candidates=[{"model_code": "nikon_z_24_70_f28_s"}],
        )

        self.assertEqual(payload["catalog_candidates"][0]["model_code"], "nikon_z_24_70_f28_s")
        self.assertEqual(payload["first_pass_extraction"]["brand"], "尼康")

    def test_phone_and_airpods_profiles_are_registered(self) -> None:
        self.assertIsNotNone(get_review_v3_profile("phone"))
        self.assertIsNotNone(get_review_v3_profile("apple_airpods"))
        self.assertIsNotNone(get_review_v3_profile("camera_body"))


if __name__ == "__main__":
    unittest.main()
