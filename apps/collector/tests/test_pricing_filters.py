from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from goofish_insight.application.services.pricing_eligibility import (
    build_pricing_eligibility_snapshot,
    build_pricing_spec_source_snapshot,
    is_item_eligible_for_pricing,
    spec_confidence_passes_pricing_gate,
    usable_spec_for_pricing,
)
from goofish_insight.pricing import (
    filter_outlier_price_records,
    resolve_domain_redirect_scope,
    resolve_pricing_record,
    resolve_pricing_scope,
    summarize_pricing_gate,
    summarize_pricing_group,
    title_domain_mismatch_reason,
    title_matches_domain,
    title_is_non_comparable_listing,
)


class PricingFilterTests(unittest.TestCase):
    def test_resolve_pricing_scope_treats_category_code_as_primary_scope(self) -> None:
        category_scope = resolve_pricing_scope(category_code="apple_computer")
        legacy_scope = resolve_pricing_scope(business_domain="apple_m_series")

        self.assertEqual(category_scope.category_code, "apple_computer")
        self.assertEqual(legacy_scope.category_code, "apple_computer")
        self.assertEqual(set(category_scope.scope_keys), set(legacy_scope.scope_keys))
        self.assertIn("apple_m_series", category_scope.scope_keys)
        self.assertIn("apple_computer", category_scope.scope_keys)

    def test_title_matches_domain_supports_camera_scopes(self) -> None:
        self.assertTrue(
            title_matches_domain(
                "camera_interchangeable_lens",
                "尼康 Z 24-70mm f/2.8 S 镜头",
            )
        )
        self.assertTrue(
            title_matches_domain(
                "camera_body",
                "索尼 a7c2 全画幅机身",
            )
        )

    def test_title_matches_domain_requires_apple_context_for_m_series_alias(self) -> None:
        self.assertTrue(
            title_matches_domain(
                "apple_computer",
                "Mac Studio M4 Max 64G",
            )
        )
        self.assertFalse(
            title_matches_domain(
                "apple_computer",
                "外星人M17x第一代笔记本",
            )
        )
        self.assertFalse(
            title_matches_domain(
                "apple_computer",
                "16寸戴尔移动工作站 precision 7670 酷睿I7 12800hx rtx A3000 12G独显",
            )
        )
        self.assertFalse(
            title_matches_domain(
                "apple_computer",
                "Apple Watch Ultra 2 49mm 钛金属 GPS 蜂窝",
            )
        )
        self.assertFalse(
            title_matches_domain(
                "apple_computer",
                "14寸 16g 512g 轻薄本",
            )
        )
        self.assertTrue(
            title_matches_domain(
                "apple_computer",
                "m3pro 16寸 36g 1t",
            )
        )

    def test_title_matches_domain_distinguishes_camera_body_and_lens(self) -> None:
        self.assertFalse(
            title_matches_domain(
                "camera_body",
                "尼康 Z 24-70mm f/2.8 S 镜头 国行",
            )
        )
        self.assertTrue(
            title_matches_domain(
                "camera_body",
                "索尼 A7C2 全画幅微单机身 快门低",
            )
        )
        self.assertFalse(
            title_matches_domain(
                "camera_interchangeable_lens",
                "索尼 A7C2 全画幅微单机身 快门低",
            )
        )

    def test_title_matches_domain_keeps_camera_body_bundle_titles(self) -> None:
        self.assertTrue(
            title_matches_domain(
                "camera_body",
                "索尼A7C2 28-60套机",
            )
        )
        self.assertTrue(
            title_matches_domain(
                "camera_body",
                "佳能R8，自用，香港购入。镜头24-105银圈。50定",
            )
        )
        self.assertFalse(
            title_matches_domain(
                "camera_interchangeable_lens",
                "索尼A7C2 28-60套机",
            )
        )

    def test_title_matches_domain_accepts_compact_lens_titles(self) -> None:
        self.assertTrue(
            title_matches_domain(
                "camera_interchangeable_lens",
                "尼康24-70 f2.8 AF-S，尼康F卡口，成色还可以",
            )
        )
        self.assertTrue(
            title_matches_domain(
                "camera_interchangeable_lens",
                "唯卓仕135mm F1.8 LAB，索尼E口，全画幅大光圈定焦",
            )
        )
        self.assertTrue(
            title_matches_domain(
                "camera_interchangeable_lens",
                "尼康24-200 Z卡口 26年3月购入，成色99.99 新",
            )
        )
        self.assertTrue(
            title_matches_domain(
                "camera_interchangeable_lens",
                "尼康50-1.8S   99新就用一次",
            )
        )
        self.assertTrue(
            title_matches_domain(
                "camera_interchangeable_lens",
                "索尼50 1.4GM 国行已注册，很新，成色参考图片",
            )
        )

    def test_title_matches_domain_accepts_short_camera_body_titles(self) -> None:
        self.assertTrue(
            title_matches_domain(
                "camera_body",
                "富士XA20，功能正常，成色一般，有电池和充电器",
            )
        )
        self.assertTrue(
            title_matches_domain(
                "camera_body",
                "索尼A7S 功能一切正常，贴了膜，平时用得很少",
            )
        )

    def test_title_matches_domain_rejects_camera_body_parts_and_packaging(self) -> None:
        self.assertFalse(
            title_matches_domain(
                "camera_body",
                "佳能eos r5 盒说 注意只有盒说 没有其他东西 相机早卖了",
            )
        )
        self.assertFalse(
            title_matches_domain(
                "camera_body",
                "佳能 EOS R8顶盖 组件 整体 全新原装",
            )
        )
        self.assertFalse(
            title_matches_domain(
                "camera_body",
                "EOS R镜头后盖，佳能R机身盖，佳能R5 R6 RP等E EOS R机身盖",
            )
        )

    def test_title_matches_domain_rejects_body_bundle_in_lens_scope(self) -> None:
        self.assertFalse(
            title_matches_domain(
                "camera_interchangeable_lens",
                "几乎全新a7m4相机，带腾龙28-75g2镜头，机器功能一切正常",
            )
        )

    def test_resolve_domain_redirect_scope_identifies_camera_cross_domain_titles(self) -> None:
        self.assertEqual(
            resolve_domain_redirect_scope(
                "camera_body",
                "尼康 Z 24-70mm f/2.8 S 镜头 国行",
            ),
            "camera_interchangeable_lens",
        )
        self.assertEqual(
            resolve_domain_redirect_scope(
                "camera_interchangeable_lens",
                "索尼 A7C2 全画幅微单机身 快门低",
            ),
            "camera_body",
        )
        self.assertIsNone(
            resolve_domain_redirect_scope(
                "apple_computer",
                "Apple Watch Ultra 2 49mm",
            )
        )

    def test_title_domain_mismatch_reason_labels_apple_and_garmin_noise(self) -> None:
        self.assertEqual(
            title_domain_mismatch_reason(
                "apple_computer",
                "Apple Watch Ultra 2 49mm GPS 版",
            ),
            "apple_watch_like",
        )
        self.assertEqual(
            title_domain_mismatch_reason(
                "garmin_watch",
                "苹果 MacBook Pro M4 Max 16寸 36G 1TB",
            ),
            "computer_or_mobile_like",
        )

    def test_summarize_pricing_gate_breaks_out_review_gate_reasons(self) -> None:
        summary = summarize_pricing_gate(
            items=[
                SimpleNamespace(llm_reviewed=True, llm_review_status="valid", llm_review_needs_audit=False, llm_review_confidence=Decimal("0.9700")),
                SimpleNamespace(llm_reviewed=True, llm_review_status="valid", llm_review_needs_audit=False, llm_review_confidence=Decimal("0.9900")),
                SimpleNamespace(llm_reviewed=True, llm_review_status="valid", llm_review_needs_audit=False, llm_review_confidence=Decimal("0.9400")),
                SimpleNamespace(llm_reviewed=True, llm_review_status="pending_audit", llm_review_needs_audit=True, llm_review_confidence=None),
                SimpleNamespace(llm_reviewed=True, llm_review_status="invalid", llm_review_needs_audit=False, llm_review_confidence=Decimal("0.1000")),
                SimpleNamespace(llm_reviewed=False, llm_review_status="pending", llm_review_needs_audit=False, llm_review_confidence=None),
            ],
            pricing_pool_count=1,
        )

        self.assertEqual(summary["candidate_count"], 6)
        self.assertEqual(summary["review_gate_pass_count"], 2)
        self.assertEqual(summary["review_gate_filtered_count"], 4)
        self.assertEqual(summary["pricing_pool_count"], 1)
        self.assertEqual(summary["structural_drop_count"], 1)
        counts = {reason["key"]: reason["count"] for reason in summary["excluded_reasons"]}
        self.assertEqual(counts["low_confidence"], 1)
        self.assertEqual(counts["pending_audit"], 1)
        self.assertEqual(counts["invalid"], 1)
        self.assertEqual(counts["review_not_ready"], 1)

    def test_pricing_gate_requires_high_confidence_valid_review(self) -> None:
        self.assertTrue(
            is_item_eligible_for_pricing(
                SimpleNamespace(
                    llm_reviewed=True,
                    llm_review_status="valid",
                    llm_review_needs_audit=False,
                    llm_review_confidence=Decimal("0.9500"),
                )
            )
        )
        self.assertFalse(
            is_item_eligible_for_pricing(
                SimpleNamespace(
                    llm_reviewed=True,
                    llm_review_status="valid",
                    llm_review_needs_audit=False,
                    llm_review_confidence=Decimal("0.9400"),
                )
            )
        )
        self.assertFalse(
            is_item_eligible_for_pricing(
                SimpleNamespace(
                    llm_reviewed=True,
                    llm_review_status="pending_audit",
                    llm_review_needs_audit=True,
                    llm_review_confidence=None,
                )
            )
        )

    def test_spec_confidence_gate_requires_high_confidence(self) -> None:
        self.assertTrue(spec_confidence_passes_pricing_gate(0.75))
        self.assertTrue(spec_confidence_passes_pricing_gate(0.91))
        self.assertFalse(spec_confidence_passes_pricing_gate(0.74))
        self.assertFalse(spec_confidence_passes_pricing_gate(None))

    def test_usable_spec_for_pricing_ignores_llm_review_shadow_rows(self) -> None:
        self.assertIsNone(usable_spec_for_pricing(SimpleNamespace(extractor_type="llm_review")))
        real_spec = SimpleNamespace(extractor_type="hybrid")
        self.assertIs(real_spec, usable_spec_for_pricing(real_spec))

    def test_build_pricing_spec_source_snapshot_marks_shadow_rows(self) -> None:
        source = build_pricing_spec_source_snapshot(SimpleNamespace(extractor_type="llm_review"))

        self.assertEqual(source["extractorType"], "llm_review")
        self.assertEqual(source["isShadow"], True)
        self.assertEqual(source["pricingUsable"], False)

    def test_pricing_eligibility_can_pass_with_runtime_only_spec_signal(self) -> None:
        item = SimpleNamespace(
            llm_reviewed=True,
            llm_review_status="valid",
            llm_review_needs_audit=False,
            llm_review_confidence=Decimal("0.9900"),
        )

        snapshot = build_pricing_eligibility_snapshot(
            item=item,
            raw_spec=None,
            spec_status="complete",
            spec_confidence=0.91,
            exact_spec_ready=True,
        )

        self.assertEqual(snapshot["pricingReady"], True)
        self.assertEqual(snapshot["specSource"]["present"], False)
        self.assertEqual(snapshot["specGate"]["passed"], True)

    def test_pricing_eligibility_blocks_shadow_spec_even_with_confident_runtime_signal(self) -> None:
        item = SimpleNamespace(
            llm_reviewed=True,
            llm_review_status="valid",
            llm_review_needs_audit=False,
            llm_review_confidence=Decimal("0.9900"),
        )

        snapshot = build_pricing_eligibility_snapshot(
            item=item,
            raw_spec=SimpleNamespace(extractor_type="llm_review"),
            spec_status="complete",
            spec_confidence=0.91,
            exact_spec_ready=True,
        )

        self.assertEqual(snapshot["pricingReady"], False)
        self.assertEqual(snapshot["specGate"]["passed"], False)
        self.assertEqual(snapshot["specGate"]["reason"], "shadow_spec")

    def test_resolve_pricing_record_drops_low_spec_confidence(self) -> None:
        now = datetime.now(UTC)
        item = SimpleNamespace(
            id=1,
            item_id="pricing-low-spec",
            source_platform="xianyu",
            business_domain="camera_interchangeable_lens",
            resolved_category_id=None,
            target_category_id=None,
            resolved_template_id=None,
            seller_profile_id=None,
            title="尼康 镜头 自用出",
            region="Shanghai",
            listing_url="https://example.com/item",
            current_price=Decimal("9800"),
            last_seen_at=now,
            publish_time=now - timedelta(days=1),
            first_seen_at=now - timedelta(days=2),
            normalized_brand=None,
            normalized_model_family=None,
            normalized_model=None,
            normalized_chip=None,
            normalized_memory_gb=None,
            normalized_storage_gb=None,
            condition_tags=[],
            source_keyword=None,
            llm_reviewed=True,
            llm_review_status="valid",
            llm_review_needs_audit=False,
            llm_review_confidence=Decimal("0.9900"),
        )
        spec = SimpleNamespace(
            category_id=None,
            template_id=None,
            model_catalog_id="catalog-1",
            extractor_type="hybrid",
            confidence=Decimal("0.20"),
            status="partial",
            brand="尼康",
            product_line=None,
            model_family=None,
            model_name="NIKKOR Z 24-70mm f/2.8 S",
            display_type=None,
            case_size_mm=None,
            is_solar=None,
            screen_size_in=None,
            chip_family=None,
            cpu_cores=None,
            gpu_cores=None,
            memory_gb=None,
            storage_gb=None,
        )

        self.assertIsNone(resolve_pricing_record(item=item, spec=spec))

    def test_resolve_pricing_record_includes_contract_and_eligibility_explanations(self) -> None:
        now = datetime.now(UTC)
        item = SimpleNamespace(
            id=2,
            item_id="pricing-ok-spec",
            source_platform="xianyu",
            business_domain="camera_interchangeable_lens",
            resolved_category_id="cat-lens",
            target_category_id=None,
            resolved_template_id="tpl-lens",
            seller_profile_id=None,
            title="尼康 Z 24-70mm f/2.8 S 镜头 自用出",
            region="Shanghai",
            listing_url="https://example.com/item/2",
            current_price=Decimal("9800"),
            last_seen_at=now,
            publish_time=now - timedelta(days=1),
            first_seen_at=now - timedelta(days=2),
            normalized_brand=None,
            normalized_model_family=None,
            normalized_model=None,
            normalized_chip=None,
            normalized_memory_gb=None,
            normalized_storage_gb=None,
            condition_tags=[],
            source_keyword=None,
            llm_reviewed=True,
            llm_review_status="valid",
            llm_review_needs_audit=False,
            llm_review_confidence=Decimal("0.9900"),
        )
        spec = SimpleNamespace(
            category_id="cat-lens",
            template_id="tpl-lens",
            model_catalog_id="catalog-1",
            extractor_type="hybrid",
            confidence=Decimal("0.91"),
            status="complete",
            brand="尼康",
            product_line=None,
            model_family=None,
            model_name="NIKKOR Z 24-70mm f/2.8 S",
            display_type=None,
            case_size_mm=None,
            is_solar=None,
            screen_size_in=None,
            chip_family=None,
            cpu_cores=None,
            gpu_cores=None,
            memory_gb=None,
            storage_gb=None,
            extraction_payload={
                "contract": {
                    "source": "merge",
                    "requiredFields": ["brand_name", "model_name", "mount_system"],
                    "missingRequiredFields": [],
                    "identityFields": ["brand_name", "model_name"],
                    "status": "complete",
                    "needsReview": False,
                }
            },
        )

        record = resolve_pricing_record(item=item, spec=spec)

        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["pricing_eligibility"]["pricingReady"], True)
        self.assertEqual(record["pricing_eligibility"]["reviewGate"]["passed"], True)
        self.assertEqual(record["pricing_eligibility"]["specGate"]["passed"], True)
        self.assertEqual(record["spec_source"]["pricingUsable"], True)
        self.assertEqual(record["spec_contract"]["source"], "merge")
        self.assertEqual(record["spec_contract"]["status"], "complete")
        self.assertEqual(record["spec_contract"]["missingRequiredFields"], [])

    def test_avg_floor_prefilter_removes_extreme_low_prices_for_large_expensive_groups(self) -> None:
        records = [
            {"price": price, "seller_key": f"seller-{index}", "title": f"item-{index}"}
            for index, price in enumerate(
                [2, 3, 4, 5100, 5200, 5300, 5400, 5500, 5600, 5700, 5800],
                start=1,
            )
        ]

        cleaned, meta = filter_outlier_price_records(records)

        self.assertEqual([record["price"] for record in cleaned], [5100, 5200, 5300, 5400, 5500, 5600, 5700, 5800])
        self.assertEqual(meta["pre_filter_method"], "avg_floor_50pct")
        self.assertEqual(meta["pre_filter_removed_count"], 3)
        self.assertGreater(meta["pre_filter_average_price"], 1000)
        self.assertGreater(meta["pre_filter_floor"], 500)

    def test_avg_floor_prefilter_also_applies_at_ten_samples(self) -> None:
        records = [
            {"price": price, "seller_key": f"seller-{index}", "title": f"item-{index}"}
            for index, price in enumerate(
                [2, 2, 2, 2, 2, 2, 20500, 22000, 22400, 25100],
                start=1,
            )
        ]

        cleaned, meta = filter_outlier_price_records(records)

        self.assertEqual([record["price"] for record in cleaned], [20500, 22000, 22400, 25100])
        self.assertEqual(meta["pre_filter_method"], "avg_floor_50pct")
        self.assertEqual(meta["pre_filter_removed_count"], 6)
        self.assertGreater(meta["pre_filter_average_price"], 1000)
        self.assertGreater(meta["pre_filter_floor"], 4000)

    def test_title_filter_excludes_wanted_bundle_and_sold_posts(self) -> None:
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="apple_m_series",
                title="收！！收！！mac studio m1max 10核 cpu+32核 gpu版本 32G内存 512硬盘",
            )
        )
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="apple_m_series",
                title="【收】64g M1 MAX Mac Studio 仅收个人卖家",
            )
        )
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="apple_m_series",
                title="（已出）Mac studio m1 max 基础版 10+24核 32内存 512g固态",
            )
        )
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="apple_m_series",
                title="Mac Studio + Studio Display显示器 套装，M1 Max 32G+512G",
            )
        )
        self.assertFalse(
            title_is_non_comparable_listing(
                business_domain="apple_m_series",
                title="Mac Studio M1 Max 32G 1TB 国行自用，功能正常",
            )
        )

    def test_title_filter_excludes_commercial_variant_menu_posts(self) -> None:
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="garmin",
                title="国行佳明Tactix 8 /泰铁时8智能户外运动手表 支持闪送，当日达，详情咨询客服，47mm AMOLED炫彩版，51mm AMOLED炫彩版",
            )
        )
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="garmin",
                title="佳明tactix8 47mm Amoled、51mm Amoled、51mm Mip 活动来袭新颜色也可以预定哦",
            )
        )
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="garmin",
                title="全新未拆 佳明Tactix 8 47mm AMOLED屏 蓝宝石镜面 钛合金机身 国行正品 支持自提 顺丰包邮",
            )
        )
        self.assertFalse(
            title_is_non_comparable_listing(
                business_domain="garmin",
                title="佳明 tactix8 泰铁时8代 47mm AMOLED版 黑色钛金属 自用两个多月，保修到 2027 年 1 月",
            )
        )

    def test_title_filter_excludes_garmin_watchface_service_phrases(self) -> None:
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="garmin_watch",
                title="Garmin fenix 8 amoled 解锁佳明表盘 可以来图定制 安装需要用电脑 售出不退不换",
                price=10,
            )
        )

    def test_title_filter_excludes_low_price_garmin_accessory_posts(self) -> None:
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="garmin_watch",
                title="适用佳明265表带 快拆 22mm 表带接口 多色可选",
                price=35,
            )
        )
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="garmin_watch",
                title="Garmin佳明HRM-3心率带模块 支持ANT+协议",
                price=270,
            )
        )

    def test_title_filter_keeps_low_price_valid_garmin_watch_listing(self) -> None:
        self.assertFalse(
            title_is_non_comparable_listing(
                business_domain="garmin_watch",
                title="出一个佳明735xt 用了2个月左右 现在不需要了 换了表带 有原装数据线",
                price=270,
            )
        )

    def test_title_filter_excludes_garmin_placeholder_one_yuan_listing(self) -> None:
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="garmin_watch",
                title="【可置换】佳明garmin marq2 Adventurer 全新腕表 官方价19800 国行正品",
                price=1,
            )
        )

    def test_title_filter_excludes_camera_rentals_and_parts(self) -> None:
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="camera_body",
                title="佳能R5出租 上海市中心有实体店，可到店取或闪送或邮寄",
                price=140,
            )
        )
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="camera_body",
                title="佳能eos r5 盒说 注意只有盒说 没有其他东西 相机早卖了",
                price=99,
            )
        )
        self.assertTrue(
            title_is_non_comparable_listing(
                business_domain="camera_interchangeable_lens",
                title="佳能r5加ef24-70二代出租 押金全押",
                price=120,
            )
        )

    def test_low_margin_group_is_not_actionable_even_when_samples_are_stable(self) -> None:
        now = datetime.now(UTC)
        row = summarize_pricing_group(
            view="spec",
            key=("apple_m_series", "Apple", "MacBook Pro / M1 Pro", "MacBook Pro / M1 Pro / 16G / 512G"),
            group_records=[
                self._pricing_record("seller-1", 5181, now),
                self._pricing_record("seller-2", 5197, now - timedelta(hours=2)),
                self._pricing_record("seller-3", 5203, now - timedelta(hours=4)),
            ],
            min_sample_points=3,
        )

        assert row is not None
        self.assertTrue(row["sample_confident"])
        self.assertFalse(row["is_actionable"])
        self.assertEqual(row["opportunity_tier"], "low")
        self.assertLess(row["normal_margin_pct"], 1)

    def test_profitable_group_can_be_marked_actionable(self) -> None:
        now = datetime.now(UTC)
        row = summarize_pricing_group(
            view="spec",
            key=("apple_m_series", "Apple", "MacBook Pro / M1 Pro", "MacBook Pro / M1 Pro / 16G / 512G"),
            group_records=[
                self._pricing_record("seller-1", 3500, now),
                self._pricing_record("seller-2", 3600, now - timedelta(hours=2)),
                self._pricing_record("seller-3", 5000, now - timedelta(hours=4)),
                self._pricing_record("seller-4", 5200, now - timedelta(hours=6)),
            ],
            min_sample_points=3,
        )

        assert row is not None
        self.assertTrue(row["sample_confident"])
        self.assertTrue(row["is_actionable"])
        self.assertEqual(row["opportunity_tier"], "good")
        self.assertGreaterEqual(row["normal_margin_pct"], 10)

    def test_reliability_score_penalizes_wide_price_band_and_outliers(self) -> None:
        now = datetime.now(UTC)
        stable = summarize_pricing_group(
            view="spec",
            key=("apple_m_series", "Apple", "MacBook Pro / M1 Pro", "MacBook Pro / M1 Pro / 16G / 512G"),
            group_records=[
                self._pricing_record("seller-1", 5180, now, publish_time=now - timedelta(days=2)),
                self._pricing_record("seller-2", 5200, now - timedelta(hours=2), publish_time=now - timedelta(days=3)),
                self._pricing_record("seller-3", 5220, now - timedelta(hours=4), publish_time=now - timedelta(days=4)),
                self._pricing_record("seller-4", 5240, now - timedelta(hours=6), publish_time=now - timedelta(days=5)),
            ],
            min_sample_points=3,
        )
        volatile = summarize_pricing_group(
            view="spec",
            key=("apple_m_series", "Apple", "MacBook Pro / M1 Pro", "MacBook Pro / M1 Pro / 16G / 512G"),
            group_records=[
                self._pricing_record("seller-1", 3500, now, publish_time=now - timedelta(days=2)),
                self._pricing_record("seller-2", 4200, now - timedelta(hours=2), publish_time=now - timedelta(days=3)),
                self._pricing_record("seller-3", 5200, now - timedelta(hours=4), publish_time=now - timedelta(days=4)),
                self._pricing_record("seller-4", 6600, now - timedelta(hours=6), publish_time=now - timedelta(days=5)),
            ],
            min_sample_points=3,
        )

        assert stable is not None and volatile is not None
        self.assertGreater(stable["price_stability_score"], volatile["price_stability_score"])
        self.assertGreater(stable["reliability_score"], volatile["reliability_score"])

    def test_reliability_score_penalizes_extreme_listing_age_profile(self) -> None:
        now = datetime.now(UTC)
        balanced = summarize_pricing_group(
            view="spec",
            key=("apple_m_series", "Apple", "MacBook Pro / M1 Pro", "MacBook Pro / M1 Pro / 16G / 512G"),
            group_records=[
                self._pricing_record("seller-1", 5000, now, publish_time=now - timedelta(days=2)),
                self._pricing_record("seller-2", 5050, now - timedelta(hours=2), publish_time=now - timedelta(days=3)),
                self._pricing_record("seller-3", 5100, now - timedelta(hours=4), publish_time=now - timedelta(days=4)),
                self._pricing_record("seller-4", 5150, now - timedelta(hours=6), publish_time=now - timedelta(days=5)),
            ],
            min_sample_points=3,
        )
        extreme_age = summarize_pricing_group(
            view="spec",
            key=("apple_m_series", "Apple", "MacBook Pro / M1 Pro", "MacBook Pro / M1 Pro / 16G / 512G"),
            group_records=[
                self._pricing_record("seller-1", 5000, now, publish_time=now - timedelta(minutes=20)),
                self._pricing_record("seller-2", 5050, now - timedelta(hours=2), publish_time=now - timedelta(minutes=40)),
                self._pricing_record("seller-3", 5100, now - timedelta(hours=4), publish_time=now - timedelta(days=40)),
                self._pricing_record("seller-4", 5150, now - timedelta(hours=6), publish_time=now - timedelta(days=50)),
            ],
            min_sample_points=3,
        )

        assert balanced is not None and extreme_age is not None
        self.assertGreater(balanced["listing_age_score"], extreme_age["listing_age_score"])
        self.assertGreater(balanced["reliability_score"], extreme_age["reliability_score"])

    def _pricing_record(
        self,
        seller_key: str,
        price: float,
        last_seen_at: datetime,
        *,
        publish_time: datetime | None = None,
        first_seen_at: datetime | None = None,
    ) -> dict[str, object]:
        return {
            "seller_key": seller_key,
            "title": "MacBook Pro M1 Pro 16G 512G",
            "price": price,
            "last_seen_at": last_seen_at,
            "publish_time": publish_time,
            "first_seen_at": first_seen_at or publish_time or (last_seen_at - timedelta(days=1)),
            "exact_spec_ready": True,
            "spec_confidence": 0.94,
            "brand": "Apple",
            "product_label": "MacBook Pro / M1 Pro",
            "spec_label": "MacBook Pro / M1 Pro / 16G / 512G",
            "display_type": None,
            "case_size_mm": None,
            "is_solar": None,
            "screen_size_in": 14.2,
            "chip_family": "M1 Pro",
            "cpu_cores": 8,
            "gpu_cores": 14,
            "memory_gb": 16,
            "storage_gb": 512,
        }


if __name__ == "__main__":
    unittest.main()
