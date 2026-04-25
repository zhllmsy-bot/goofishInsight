from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from goofish_insight.cli import (
    FeedCardCandidate,
    FeedDetailSellerSnapshot,
    build_transient_item,
    load_active_tasks_by_domain,
    _task_preference_score,
    build_feed_detail_url,
    feed_pre_ingest_template_rejection_reason,
    build_feed_card_candidate_from_api_row,
    build_feed_outreach_message_text,
    classify_feed_detail_seller_snapshot,
    compute_feed_expected_profit_margin_pct,
    determine_feed_candidate_domains,
    match_feed_title_to_task_lexicon,
    parse_home_feed_api_payload,
    resolve_feed_collection_scope_domain,
    resolve_feed_seller_type,
    should_open_feed_detail_for_match,
    should_open_feed_detail_for_task,
    should_message_feed_target,
    infer_scope_from_feed_title,
)
from goofish_insight.application.services.category_resolution import ResolvedItemCategoryContext
from goofish_insight.entrypoints.cli.feed import (
    DEFAULT_MESSAGE_TEXT,
)


class FeedRulesTests(unittest.TestCase):
    def make_card(self, *, raw_text: str = "Mac Studio M1 Max") -> FeedCardCandidate:
        return FeedCardCandidate(
            item_id="abc",
            category_id="126856775",
            tb_cat_id="50008351",
            c_cat_id="126856265",
            listing_url="https://example.com/item/abc",
            title="Mac Studio M1 Max",
            raw_text=raw_text,
            price=Decimal("9000.00"),
            position=1,
        )

    def test_build_feed_card_candidate_from_api_row_parses_raw_cate_fields(self) -> None:
        card = build_feed_card_candidate_from_api_row(
            {
                "cardData": {
                    "categoryId": 126856775,
                    "detailParams": {
                        "itemId": "1038118535306",
                        "title": "全新未拆封 Mac Studio M3 Ultra",
                        "soldPrice": "41500",
                    },
                    "attributeMap": {
                        "tbCatId": "50008351",
                        "cCatId": "126856265",
                    },
                    "fishTags": {
                        "r3": {
                            "tagList": [
                                {
                                    "data": {"content": "7人想要"},
                                }
                            ]
                        }
                    },
                }
            },
            position=3,
        )

        self.assertIsNotNone(card)
        assert card is not None
        self.assertEqual(card.item_id, "1038118535306")
        self.assertEqual(card.category_id, "126856775")
        self.assertEqual(card.tb_cat_id, "50008351")
        self.assertEqual(card.c_cat_id, "126856265")
        self.assertEqual(card.listing_url, "https://www.goofish.com/item?id=1038118535306&categoryId=126856775")
        self.assertEqual(card.price, Decimal("41500.00"))
        self.assertEqual(card.position, 3)

    def test_parse_home_feed_api_payload_returns_cards_in_order(self) -> None:
        cards = parse_home_feed_api_payload(
            {
                "data": {
                    "cardList": [
                        {
                            "cardData": {
                                "categoryId": 1,
                                "detailParams": {
                                    "itemId": "a1",
                                    "title": "A1",
                                    "soldPrice": "100",
                                },
                                "attributeMap": {},
                            }
                        },
                        {
                            "cardData": {
                                "categoryId": 2,
                                "detailParams": {
                                    "itemId": "a2",
                                    "title": "A2",
                                    "soldPrice": "200",
                                },
                                "attributeMap": {},
                            }
                        },
                    ]
                }
            }
        )

        self.assertEqual([card.item_id for card in cards], ["a1", "a2"])
        self.assertEqual([card.position for card in cards], [1, 2])

    def test_build_feed_detail_url_prefers_existing_listing_url(self) -> None:
        self.assertEqual(
            build_feed_detail_url(
                item_id="1038118535306",
                category_id="126856775",
                listing_url="https://www.goofish.com/item?spm=a21ybx.home.feedsCnxh.2.4c053da6RqjBIH&id=1038118535306&categoryId=126856775",
            ),
            "https://www.goofish.com/item?spm=a21ybx.home.feedsCnxh.2.4c053da6RqjBIH&id=1038118535306&categoryId=126856775",
        )

    def test_build_feed_detail_url_falls_back_to_item_id_and_category_id(self) -> None:
        self.assertEqual(
            build_feed_detail_url(item_id="1038118535306", category_id="126856775", listing_url=None),
            "https://www.goofish.com/item?id=1038118535306&categoryId=126856775",
        )

    def test_match_feed_title_to_task_lexicon_compacts_spaces_and_symbols(self) -> None:
        task = SimpleNamespace(
            brand_lexicon=["佳能"],
            model_lexicon=["佳能R5二代"],
            keywords=["佳能 EOS R5 Mark II"],
        )

        self.assertEqual(
            match_feed_title_to_task_lexicon("佳能 EOS R5 二代 机身", task),
            "佳能R5二代",
        )

    def test_task_preference_score_prefers_richer_non_smoke_xianyu_task(self) -> None:
        preferred = SimpleNamespace(
            business_domain="apple_computer",
            category_id="cat-1",
            keywords=["Mac Studio M3 Ultra"],
            brand_lexicon=["Apple"],
            model_lexicon=["Mac Studio", "Mac Studio M3 Ultra"],
            config_lexicon=[],
            task_key="apple-m-series",
            display_name="Apple M-Series Hot and Premium Discovery",
            task_type="PRODUCTION",
            source_platform="xianyu",
            id=2,
        )
        smoke_task = SimpleNamespace(
            business_domain="apple_computer",
            category_id="cat-1",
            keywords=[],
            brand_lexicon=["Apple"],
            model_lexicon=["MacBook Pro"],
            config_lexicon=[],
            task_key="smoke-batch-apple-one",
            display_name="Smoke Batch Apple One",
            task_type="PRODUCTION",
            source_platform="xianyu",
            id=5,
        )

        self.assertGreater(_task_preference_score(preferred), _task_preference_score(smoke_task))

    def test_determine_feed_candidate_domains_prefers_mapped_domain_for_new_item(self) -> None:
        domains = determine_feed_candidate_domains(
            card=self.make_card(raw_text="尼康 z50 1.8s"),
            existing_item=None,
            tasks_by_domain={
                "camera_interchangeable_lens": SimpleNamespace(),
                "camera_body": SimpleNamespace(),
            },
            business_domain=None,
            mapped_domain="camera_interchangeable_lens",
        )

        self.assertEqual(domains, ["camera_interchangeable_lens"])

    def test_infer_scope_from_feed_title_detects_airpods_before_apple_computer(self) -> None:
        self.assertEqual(
            infer_scope_from_feed_title("AirPods Pro 2 右耳 单耳"),
            "apple_airpods",
        )

    def test_build_transient_item_uses_category_context_override(self) -> None:
        item = build_transient_item(
            task=SimpleNamespace(
                id=1,
                source_platform="xianyu",
                business_domain="apple_computer",
                category_id="cat-apple",
            ),
            extracted=SimpleNamespace(
                item_id="abc",
                title="AirPods Pro 2",
                normalized_brand="Apple",
                normalized_model_family="AirPods",
                normalized_model="AirPods Pro 2",
                normalized_chip=None,
                normalized_memory_gb=None,
                normalized_storage_gb=None,
                tags=[],
                area=None,
                listing_url="https://example.com/item/abc",
                pic_url=None,
                is_auction=False,
                is_ad=False,
                has_video=False,
                price=Decimal("899"),
                publish_time=None,
            ),
            category_context_override=ResolvedItemCategoryContext(
                target_category_id="cat-airpods",
                resolved_category_id="cat-airpods",
                resolved_template_id="tpl-airpods",
                category_validation_status="FEED_TARGET_POOL_SINGLE_CANDIDATE",
                category_validation_reason="feed_target_pool_single_candidate:apple_airpods",
                category_validation_confidence=Decimal("1.0000"),
                resolved_business_domain="apple_airpods",
            ),
        )

        self.assertEqual(item.business_domain, "apple_airpods")
        self.assertEqual(item.target_category_id, "cat-airpods")
        self.assertEqual(item.resolved_category_id, "cat-airpods")
        self.assertEqual(item.resolved_template_id, "tpl-airpods")

    def test_infer_scope_from_feed_title_keeps_mac_and_airpods_separate(self) -> None:
        self.assertEqual(
            infer_scope_from_feed_title("MacBook Pro M3 Pro 18G 512G"),
            "apple_computer",
        )

    def test_load_active_tasks_by_domain_keeps_airpods_scope(self) -> None:
        tasks = [
            SimpleNamespace(
                id=1,
                business_domain="apple_airpods",
                status="active",
                source_platform="xianyu",
                category_id="cat-airpods",
                keywords=[],
                brand_lexicon=[],
                model_lexicon=["AirPods Pro 2"],
                config_lexicon=[],
                task_key="airpods-core",
                display_name="AirPods Core",
                task_type="PRODUCTION",
            ),
            SimpleNamespace(
                id=2,
                business_domain="apple_computer",
                status="active",
                source_platform="xianyu",
                category_id="cat-apple",
                keywords=[],
                brand_lexicon=[],
                model_lexicon=["MacBook Pro"],
                config_lexicon=[],
                task_key="apple-core",
                display_name="Apple Core",
                task_type="PRODUCTION",
            ),
        ]

        class _FakeExecuteResult:
            def scalars(self_inner):
                return list(tasks)

        class _FakeSession:
            def execute(self_inner, stmt):
                del stmt
                return _FakeExecuteResult()

        class _SessionScope:
            def __enter__(self_inner):
                return _FakeSession()

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        with patch("goofish_insight.cli.session_scope", return_value=_SessionScope()):
            loaded = load_active_tasks_by_domain(business_domain=None)

        self.assertIn("apple_airpods", loaded)
        self.assertIn("apple_computer", loaded)

    def test_resolve_feed_collection_scope_domain_only_allows_domains_in_active_tasks(self) -> None:
        self.assertEqual(
            resolve_feed_collection_scope_domain(
                mapped_domain="apple_computer",
                tasks_by_domain={"apple_computer": SimpleNamespace()},
            ),
            "apple_computer",
        )
        self.assertIsNone(
            resolve_feed_collection_scope_domain(
                mapped_domain="garmin_watch",
                tasks_by_domain={"apple_computer": SimpleNamespace()},
            )
        )

    def test_should_open_feed_detail_for_task_requires_collection_scope_membership(self) -> None:
        self.assertTrue(
            should_open_feed_detail_for_task(
                mapped_domain="apple_computer",
                task=SimpleNamespace(business_domain="apple_computer"),
                tasks_by_domain={"apple_computer": SimpleNamespace()},
            )
        )
        self.assertFalse(
            should_open_feed_detail_for_task(
                mapped_domain="garmin_watch",
                task=SimpleNamespace(business_domain="apple_computer"),
                tasks_by_domain={"apple_computer": SimpleNamespace()},
            )
        )
        self.assertFalse(
            should_open_feed_detail_for_task(
                mapped_domain=None,
                task=SimpleNamespace(business_domain="apple_computer"),
                tasks_by_domain={"apple_computer": SimpleNamespace()},
            )
        )

    def test_should_open_feed_detail_for_match_requires_target_match(self) -> None:
        self.assertFalse(
            should_open_feed_detail_for_match(
                mapped_domain="apple_computer",
                task=SimpleNamespace(business_domain="apple_computer"),
                match=None,
                tasks_by_domain={"apple_computer": SimpleNamespace()},
            )
        )
        self.assertTrue(
            should_open_feed_detail_for_match(
                mapped_domain="apple_computer",
                task=SimpleNamespace(business_domain="apple_computer"),
                match=SimpleNamespace(),
                tasks_by_domain={"apple_computer": SimpleNamespace()},
            )
        )

    def test_feed_pre_ingest_template_rejection_blocks_non_target_candidate(self) -> None:
        candidate = SimpleNamespace(
            evidence={"reason": "non_target_apple_watch"},
            extraction_payload={},
            status="unresolved",
        )

        self.assertEqual(
            feed_pre_ingest_template_rejection_reason(candidate=candidate),
            "non_target_apple_watch",
        )

    def test_feed_pre_ingest_template_rejection_allows_partial_candidate(self) -> None:
        candidate = SimpleNamespace(
            evidence={},
            extraction_payload={},
            status="partial",
        )

        self.assertIsNone(feed_pre_ingest_template_rejection_reason(candidate=candidate))

    def test_compute_feed_expected_profit_margin_pct_uses_current_card_price(self) -> None:
        card = self.make_card()
        match = SimpleNamespace(
            fair_price=Decimal("9900.00"),
        )

        margin_pct = compute_feed_expected_profit_margin_pct(card=card, match=match)

        self.assertEqual(margin_pct, Decimal("10.00"))

    def test_should_message_feed_target_blocks_commercial_seller_in_generic_mode(self) -> None:
        should_send, reason = should_message_feed_target(
            card=self.make_card(),
            match=None,
            seller_type="commercial_like",
            max_messages=1,
            sent_count=0,
            require_actionable_band=False,
            only_within_target_price=False,
            min_profit_margin_pct=Decimal("10.00"),
        )

        self.assertFalse(should_send)
        self.assertEqual(reason, "seller_commercial_like")

    def test_should_message_feed_target_allows_generic_outreach_for_private_seller(self) -> None:
        should_send, reason = should_message_feed_target(
            card=self.make_card(),
            match=None,
            seller_type="private_like",
            max_messages=1,
            sent_count=0,
            require_actionable_band=False,
            only_within_target_price=False,
            min_profit_margin_pct=Decimal("10.00"),
        )

        self.assertTrue(should_send)
        self.assertEqual(reason, "eligible")

    def test_should_message_feed_target_blocks_commercial_seller_in_actionable_mode(self) -> None:
        should_send, reason = should_message_feed_target(
            card=self.make_card(),
            match=SimpleNamespace(
                is_actionable=True,
                target_buy_ceiling=Decimal("8800.00"),
                fair_price=Decimal("9800.00"),
            ),
            seller_type="commercial_like",
            max_messages=1,
            sent_count=0,
            require_actionable_band=True,
            only_within_target_price=False,
            min_profit_margin_pct=Decimal("10.00"),
        )

        self.assertFalse(should_send)
        self.assertEqual(reason, "seller_commercial_like")

    def test_should_message_feed_target_blocks_unknown_seller_in_actionable_mode(self) -> None:
        should_send, reason = should_message_feed_target(
            card=self.make_card(),
            match=SimpleNamespace(
                is_actionable=True,
                target_buy_ceiling=Decimal("8800.00"),
                fair_price=Decimal("9800.00"),
            ),
            seller_type="unknown",
            max_messages=1,
            sent_count=0,
            require_actionable_band=True,
            only_within_target_price=False,
            min_profit_margin_pct=Decimal("10.00"),
        )

        self.assertFalse(should_send)
        self.assertEqual(reason, "seller_type_unknown")

    def test_should_message_feed_target_allows_private_seller_with_safe_price(self) -> None:
        should_send, reason = should_message_feed_target(
            card=self.make_card(),
            match=SimpleNamespace(
                is_actionable=True,
                target_buy_ceiling=Decimal("8800.00"),
                fair_price=Decimal("9800.00"),
            ),
            seller_type="private_like",
            max_messages=1,
            sent_count=0,
            require_actionable_band=True,
            only_within_target_price=False,
            min_profit_margin_pct=Decimal("10.00"),
        )

        self.assertTrue(should_send)
        self.assertEqual(reason, "eligible")

    def test_should_message_feed_target_blocks_when_message_cap_reached(self) -> None:
        should_send, reason = should_message_feed_target(
            card=self.make_card(),
            match=None,
            seller_type="unknown",
            max_messages=1,
            sent_count=1,
            require_actionable_band=False,
            only_within_target_price=False,
            min_profit_margin_pct=Decimal("10.00"),
        )

        self.assertFalse(should_send)
        self.assertEqual(reason, "message_cap_reached")

    def test_build_feed_outreach_message_text_renders_safe_price_template(self) -> None:
        message = build_feed_outreach_message_text(
            card=self.make_card(),
            match=SimpleNamespace(
                business_domain="apple_computer",
                label="Mac Studio / M1 Max",
                target_buy_ceiling=Decimal("8800.00"),
                fair_price=Decimal("9800.00"),
            ),
            message_template="你好，{category_name} 这边我们安全价在{safe_price}左右，请问{safe_price}能出吗？",
        )

        self.assertEqual(
            message,
            "你好，Apple电脑 这边我们安全价在¥8800左右，请问¥8800能出吗？",
        )

    def test_default_feed_message_text_is_short_safe_price_prompt(self) -> None:
        message = build_feed_outreach_message_text(
            card=self.make_card(),
            match=SimpleNamespace(
                business_domain="apple_computer",
                label="Mac Studio / M1 Max",
                target_buy_ceiling=Decimal("8800.00"),
                fair_price=Decimal("9800.00"),
            ),
            message_template=DEFAULT_MESSAGE_TEXT,
        )

        self.assertEqual(message, "你好，请问，价格还有空间吗？")

    def test_classify_feed_detail_seller_snapshot_marks_two_level_tokens_as_commercial(self) -> None:
        seller_type, signals = classify_feed_detail_seller_snapshot(
            snapshot=FeedDetailSellerSnapshot(
                seller_id="1",
                seller_name="Apple折扣店",
                region="上海",
                last_active_label="41分钟前来过",
                sold_count=48,
                years_on_platform=9,
                review_rate_pct=63,
                level_token_count=2,
                level_texts=("鱼小铺", "L7"),
                badge_texts=(),
                profile_url="https://www.goofish.com/personal?userId=1",
            )
        )

        self.assertEqual(seller_type, "commercial_like")
        self.assertEqual(signals, ["detail_level_token_count=2"])

    def test_classify_feed_detail_seller_snapshot_marks_one_level_token_as_private(self) -> None:
        seller_type, signals = classify_feed_detail_seller_snapshot(
            snapshot=FeedDetailSellerSnapshot(
                seller_id="2",
                seller_name="h***9",
                region="上海",
                last_active_label="41分钟前来过",
                sold_count=48,
                years_on_platform=9,
                review_rate_pct=63,
                level_token_count=1,
                level_texts=("闲鱼号",),
                badge_texts=(),
                profile_url="https://www.goofish.com/personal?userId=2",
            )
        )

        self.assertEqual(seller_type, "private_like")
        self.assertEqual(signals, ["detail_level_token_count=1"])

    def test_resolve_feed_seller_type_uses_existing_profile_metadata(self) -> None:
        seller_profiles = {
            7: SimpleNamespace(
                id=7,
                metadata_json={
                    "sellerType": "private_like",
                },
            )
        }
        seller_type = resolve_feed_seller_type(
            card=self.make_card(raw_text="Mac Studio M1 Max"),
            existing_item=SimpleNamespace(seller_profile_id=7),
            seller_profiles=seller_profiles,
        )

        self.assertEqual(seller_type, "private_like")

    def test_resolve_feed_seller_type_marks_yuxiaopu_as_commercial(self) -> None:
        seller_type = resolve_feed_seller_type(
            card=self.make_card(raw_text="Mac Studio M1 Max 鱼小铺 L7"),
            existing_item=None,
            seller_profiles={},
        )

        self.assertEqual(seller_type, "commercial_like")


if __name__ == "__main__":
    unittest.main()
