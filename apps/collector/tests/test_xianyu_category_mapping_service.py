from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from goofish_insight.application.services.xianyu_category_mapping import (
    _scope_keys_for_filter,
    backfill_xianyu_raw_category_signals_with_session,
    build_xianyu_category_onboarding_draft_with_session,
    build_xianyu_category_match_candidates,
    build_xianyu_category_match_key,
    build_xianyu_raw_category_coverage_report_with_session,
    list_xianyu_category_onboarding_queue_with_session,
    persist_xianyu_category_onboarding_with_session,
    resolve_xianyu_category_mapping_with_session,
    serialize_xianyu_category_onboarding_queue,
    sync_xianyu_category_onboarding_queue_with_session,
    update_xianyu_category_onboarding_queue_status_with_session,
)
from goofish_insight.compat import UTC
from goofish_insight.models import (
    Item,
    ItemSpecEnrichment,
    XianyuCategoryMapping,
    XianyuCategoryMatchScope,
    XianyuCategoryOnboardingQueue,
)


class _FakeScalarRows:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeExecuteResult:
    def __init__(self, *, scalar=None, rows=None) -> None:
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return _FakeScalarRows(self._rows)

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, *, execute_results=None, categories=None, templates=None) -> None:
        self.execute_results = list(execute_results or [])
        self.categories = categories or {}
        self.templates = templates or {}
        self.added = []
        self.flush_count = 0

    def execute(self, stmt):
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeExecuteResult(rows=[])

    def get(self, model, key):
        if getattr(model, "__name__", "") == "Category":
            return self.categories.get(key)
        if getattr(model, "__name__", "") == "CategoryAttrTemplate":
            return self.templates.get(key)
        return None

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flush_count += 1


class XianyuCategoryMappingServiceTests(unittest.TestCase):
    def test_scope_keys_for_filter_includes_legacy_aliases(self) -> None:
        self.assertEqual(
            _scope_keys_for_filter("apple_computer"),
            ("apple_computer", "apple_m_series"),
        )
        self.assertEqual(
            _scope_keys_for_filter("garmin_watch"),
            ("garmin_watch", "garmin"),
        )

    def test_build_xianyu_category_match_candidates_orders_by_specificity(self) -> None:
        candidates = build_xianyu_category_match_candidates(
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="50014945",
            xianyu_c_cat_id="126854525",
        )

        self.assertEqual(
            [candidate["matchScope"] for candidate in candidates],
            ["C_CAT", "CAT_TB", "TB_CAT", "CAT"],
        )
        self.assertEqual(candidates[0]["matchKey"], "C_CAT:126854525")
        self.assertEqual(candidates[1]["matchKey"], "CAT_TB:50025387:50014945")

    def test_resolve_xianyu_category_mapping_with_session_prefers_most_specific_match(self) -> None:
        exact_mapping = XianyuCategoryMapping(
            match_scope=XianyuCategoryMatchScope.CAT_TB,
            match_key=build_xianyu_category_match_key(
                match_scope="CAT_TB",
                xianyu_cat_id="50025387",
                xianyu_tb_cat_id="50014945",
            ),
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="50014945",
            category_id="cat-1",
            template_id="tpl-1",
            status="ACTIVE",
        )
        broader_mapping = XianyuCategoryMapping(
            match_scope=XianyuCategoryMatchScope.CAT,
            match_key=build_xianyu_category_match_key(match_scope="CAT", xianyu_cat_id="50025387"),
            xianyu_cat_id="50025387",
            category_id="cat-2",
            template_id="tpl-2",
            status="ACTIVE",
        )
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[broader_mapping, exact_mapping])])

        resolved = resolve_xianyu_category_mapping_with_session(
            session,
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="50014945",
        )

        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.match_key, "CAT_TB:50025387:50014945")

    def test_persist_xianyu_category_onboarding_with_session_creates_mapping_rows(self) -> None:
        category = SimpleNamespace(id="cat-apple")
        template = SimpleNamespace(id="tpl-apple")
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(scalar=None), _FakeExecuteResult(scalar=None)],
            categories={"cat-apple": category},
            templates={"tpl-apple": template},
        )

        with patch(
            "goofish_insight.application.services.xianyu_category_mapping.persist_catalog_template_payload_with_session",
            return_value={
                "categoryId": "cat-apple",
                "templateId": "tpl-apple",
                "requestId": "req-1",
            },
        ):
            result = persist_xianyu_category_onboarding_with_session(
                session,
                payload={
                    "requestId": "req-1",
                    "catalog": {
                        "category": {"code": "apple_m_series", "name": "Apple M 系列电脑", "path": "电脑/Apple", "level": 2},
                        "template": {
                            "version": 1,
                            "status": "PUBLISHED",
                            "effectiveAt": "2026-04-06T00:00:00+00:00",
                            "items": [],
                        },
                        "attributes": [],
                    },
                    "mappings": [
                        {"matchScope": "CAT_TB", "xianyuCatId": "50025387", "xianyuTbCatId": "50014945"},
                        {"matchScope": "C_CAT", "xianyuCCatId": "126854525"},
                    ],
                },
                operator_id="ops-bot",
                dry_run=False,
            )

        created_mappings = [obj for obj in session.added if isinstance(obj, XianyuCategoryMapping)]
        self.assertEqual(result["mappingCount"], 2)
        self.assertEqual(result["createdCount"], 2)
        self.assertEqual(len(created_mappings), 2)

    def test_build_xianyu_category_onboarding_draft_with_session_outputs_payload(self) -> None:
        item = Item(
            item_id="apple-item-1",
            task_id=1,
            business_domain="apple_m_series",
            title="MacBook Pro M3 Pro 18G 512G",
            source_keyword="macbookpro14",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="50014945",
            normalized_brand="Apple",
            normalized_model_family="MacBook Pro",
            normalized_model="MacBook Pro",
            normalized_chip="M3 Pro",
            normalized_memory_gb=18,
            normalized_storage_gb=512,
        )
        item.spec_enrichment = ItemSpecEnrichment(
            business_domain="apple_m_series",
            extractor_type="llm",
            extractor_version="v1",
            status="complete",
            product_line="MacBook Pro",
            model_name="MacBook Pro",
            chip_family="M3 Pro",
            cpu_cores=12,
            gpu_cores=18,
            memory_gb=18,
            storage_gb=512,
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(scalar=None), _FakeExecuteResult(rows=[item])]
        )

        result = build_xianyu_category_onboarding_draft_with_session(
            session,
            source_keyword="macbookpro14",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="50014945",
        )

        payload = result["payload"]
        self.assertEqual(payload["mappings"][0]["matchScope"], "CAT_TB")
        self.assertEqual(payload["catalog"]["category"]["code"], "computer_device_cat_50025387_tb_50014945")
        attribute_codes = [row["code"] for row in payload["catalog"]["attributes"]]
        self.assertIn("brand_name", attribute_codes)
        self.assertIn("model_name", attribute_codes)
        self.assertIn("memory_gb", attribute_codes)
        self.assertIn("storage_gb", attribute_codes)
        self.assertIn("computer_device", [row["code"] for row in result["analysis"]["categoryHints"]])

    def test_build_xianyu_category_onboarding_draft_with_session_suggests_lens_attributes(self) -> None:
        item = Item(
            item_id="lens-item-1",
            task_id=9,
            business_domain="xianyu_onboarding",
            title="95新尼康 Z 24-70mm f/2.8 S 镜头 国行",
            source_keyword="尼康 z 24-70 2.8 s",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="140116",
            xianyu_c_cat_id="126864783",
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(scalar=None), _FakeExecuteResult(rows=[item])]
        )

        result = build_xianyu_category_onboarding_draft_with_session(
            session,
            source_keyword="尼康 z 24-70 2.8 s",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="140116",
            xianyu_c_cat_id="126864783",
        )

        analysis = result["analysis"]
        payload = result["payload"]
        attribute_codes = [row["code"] for row in payload["catalog"]["attributes"]]
        self.assertIn("brand_name", attribute_codes)
        self.assertIn("model_name", attribute_codes)
        self.assertIn("mount_system", attribute_codes)
        self.assertIn("focal_length_range", attribute_codes)
        self.assertIn("max_aperture", attribute_codes)
        self.assertIn("lens_series", attribute_codes)
        self.assertEqual(analysis["brandHints"][0]["value"], "Nikon")
        self.assertEqual(analysis["categoryHints"][0]["code"], "camera_interchangeable_lens")
        observations = {row["attributeCode"]: row for row in analysis["attributeObservations"]}
        self.assertEqual(observations["mount_system"]["sampleValues"][0], "Nikon Z")
        self.assertEqual(observations["focal_length_range"]["sampleValues"][0], "24-70mm")
        self.assertEqual(observations["max_aperture"]["sampleValues"][0], "f/2.8")

    def test_build_xianyu_category_onboarding_draft_with_session_suggests_reusing_existing_canonical_template(self) -> None:
        item = Item(
            item_id="lens-item-2",
            task_id=10,
            business_domain="xianyu_onboarding",
            title="尼康 Z 50mm f/1.2 S 镜头",
            source_keyword="尼康z50 1.2s",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="140116",
            xianyu_c_cat_id="126864783",
        )
        category = SimpleNamespace(
            id="cat-lens",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="摄影器材/镜头/可换镜头",
            level=2,
            status="ACTIVE",
        )
        template = SimpleNamespace(
            id="tpl-lens",
            category=category,
            category_id=category.id,
            version=3,
            status=SimpleNamespace(value="PUBLISHED"),
            effective_at=None,
            published_by="ops-bot",
            created_at=None,
            updated_at=None,
            items=[
                SimpleNamespace(
                    sort_no=index * 10,
                    attribute=SimpleNamespace(
                        id=f"attr-{code}",
                        code=code,
                        name=name,
                        data_type=SimpleNamespace(value="TEXT"),
                        value_scope="SPU",
                        is_multi=False,
                        options=[],
                    ),
                    is_required=code in {"brand_name", "model_name"},
                    is_sale=False,
                    is_filter=True,
                    is_search=code in {"brand_name", "model_name"},
                    is_display=True,
                )
                for index, (code, name) in enumerate(
                    [
                        ("brand_name", "Brand"),
                        ("model_name", "Model Name"),
                        ("mount_system", "Mount System"),
                        ("focal_length_range", "Focal Length Range"),
                        ("max_aperture", "Max Aperture"),
                        ("lens_series", "Lens Series"),
                    ],
                    start=1,
                )
            ],
        )
        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(scalar=None),
                _FakeExecuteResult(rows=[item]),
                _FakeExecuteResult(rows=[category]),
                _FakeExecuteResult(rows=[template]),
            ],
            templates={"tpl-lens": template},
        )

        result = build_xianyu_category_onboarding_draft_with_session(
            session,
            source_keyword="尼康z50 1.2s",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="140116",
            xianyu_c_cat_id="126864783",
        )

        reuse_suggestion = result["reuseSuggestion"]
        self.assertIsNotNone(reuse_suggestion)
        self.assertEqual(reuse_suggestion["category"]["code"], "camera_interchangeable_lens")
        self.assertEqual(reuse_suggestion["template"]["id"], "tpl-lens")
        self.assertEqual(reuse_suggestion["coverage"]["missingSuggestedAttributeCodes"], [])
        self.assertEqual(result["payload"]["categoryId"], "cat-lens")
        self.assertEqual(result["payload"]["templateId"], "tpl-lens")

    def test_build_xianyu_category_onboarding_draft_with_session_suggests_graphics_card_attributes(self) -> None:
        item = Item(
            item_id="gpu-item-1",
            task_id=12,
            business_domain="xianyu_onboarding",
            title="微星 RTX 4070 Ti Super 16G 显卡",
            source_keyword="rtx 4070 ti super",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="50012222",
            xianyu_c_cat_id="126800001",
            normalized_brand="MSI",
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(scalar=None), _FakeExecuteResult(rows=[item])]
        )

        result = build_xianyu_category_onboarding_draft_with_session(
            session,
            source_keyword="rtx 4070 ti super",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="50012222",
            xianyu_c_cat_id="126800001",
        )

        analysis = result["analysis"]
        attribute_codes = [row["code"] for row in result["payload"]["catalog"]["attributes"]]
        self.assertIn("gpu_vendor", attribute_codes)
        self.assertIn("gpu_model", attribute_codes)
        self.assertIn("vram_gb", attribute_codes)
        self.assertEqual(analysis["categoryHints"][0]["code"], "graphics_card")
        observations = {row["attributeCode"]: row for row in analysis["attributeObservations"]}
        self.assertEqual(observations["gpu_vendor"]["sampleValues"][0], "NVIDIA")
        self.assertEqual(observations["gpu_model"]["sampleValues"][0], "RTX 4070 TI SUPER")
        self.assertEqual(observations["vram_gb"]["sampleValues"][0], 16)

    def test_build_xianyu_category_onboarding_draft_with_session_suggests_phone_attributes(self) -> None:
        item = Item(
            item_id="phone-item-1",
            task_id=13,
            business_domain="xianyu_onboarding",
            title="iPhone 15 Pro Max 256G 原色钛金",
            source_keyword="iphone 15 pro max",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="50019999",
            xianyu_c_cat_id="126800002",
            normalized_brand="Apple",
            normalized_model_family="iPhone 15 Pro Max",
            normalized_storage_gb=256,
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(scalar=None), _FakeExecuteResult(rows=[item])]
        )

        result = build_xianyu_category_onboarding_draft_with_session(
            session,
            source_keyword="iphone 15 pro max",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="50019999",
            xianyu_c_cat_id="126800002",
        )

        analysis = result["analysis"]
        attribute_codes = [row["code"] for row in result["payload"]["catalog"]["attributes"]]
        self.assertIn("phone_series", attribute_codes)
        self.assertIn("device_color", attribute_codes)
        self.assertEqual(analysis["categoryHints"][0]["code"], "smartphone_device")
        observations = {row["attributeCode"]: row for row in analysis["attributeObservations"]}
        self.assertEqual(observations["phone_series"]["sampleValues"][0], "iPhone 15 Pro Max")
        self.assertEqual(observations["device_color"]["sampleValues"][0], "Titanium")

    def test_backfill_xianyu_raw_category_signals_with_session_updates_item_from_raw_response(self) -> None:
        item = Item(
            item_id="apple-item-raw-1",
            task_id=1,
            business_domain="apple_m_series",
            source_keyword="macbookpro14",
            title="MacBook Pro M3 Pro",
            current_raw_response_id=uuid4(),
        )
        response_body = {
            "data": {
                "resultList": [
                    {
                        "data": {
                            "item": {
                                "main": {
                                    "exContent": {
                                        "itemId": "apple-item-raw-1",
                                        "title": "MacBook Pro M3 Pro",
                                        "price": [{"type": "integer", "text": "7999"}],
                                    },
                                    "clickParam": {
                                        "args": {
                                            "id": "apple-item-raw-1",
                                            "cCatId": "ccat-1",
                                            "catId": "cat-1",
                                            "tbCatId": "tb-1",
                                        }
                                    },
                                }
                            }
                        }
                    }
                ]
            }
        }
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[(item, response_body)])])

        result = backfill_xianyu_raw_category_signals_with_session(
            session,
            source_keyword="macbookpro14",
            dry_run=False,
        )

        self.assertEqual(result["candidateCount"], 1)
        self.assertEqual(result["matchedCount"], 1)
        self.assertEqual(result["updatedCount"], 1)
        self.assertEqual(result["reasonCounts"]["updated"], 1)
        self.assertEqual(item.xianyu_c_cat_id, "ccat-1")
        self.assertEqual(item.xianyu_cat_id, "cat-1")
        self.assertEqual(item.xianyu_tb_cat_id, "tb-1")

    def test_build_xianyu_raw_category_coverage_report_with_session_returns_counts(self) -> None:
        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(scalar=10),
                _FakeExecuteResult(scalar=7),
                _FakeExecuteResult(scalar=6),
                _FakeExecuteResult(scalar=4),
                _FakeExecuteResult(scalar=3),
            ]
        )

        with patch(
            "goofish_insight.application.services.xianyu_category_mapping.build_xianyu_raw_category_summary_with_session",
            return_value={
                "limit": 5,
                "itemScanLimit": 500,
                "returnedCount": 1,
                "scannedItemCount": 10,
                "totalGroupedCount": 2,
                "items": [{"xianyuCatId": "cat-1", "itemCount": 3}],
            },
        ):
            result = build_xianyu_raw_category_coverage_report_with_session(
                session,
                source_keyword="macbookpro14",
                unmapped_limit=5,
                item_scan_limit=500,
            )

        self.assertEqual(result["counts"]["totalItems"], 10)
        self.assertEqual(result["counts"]["itemsWithCurrentRawResponse"], 7)
        self.assertEqual(result["counts"]["itemsWithAnyRawCategorySignal"], 6)
        self.assertEqual(result["counts"]["itemsWithCompleteRawCategorySignal"], 4)
        self.assertEqual(result["counts"]["backfillCandidateItems"], 3)
        self.assertEqual(result["coverage"]["rawSignalCoverageRatio"], 0.6)
        self.assertEqual(len(result["topUnmappedRawCategories"]), 1)

    def test_sync_xianyu_category_onboarding_queue_with_session_creates_queue_row(self) -> None:
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[])])

        with patch(
            "goofish_insight.application.services.xianyu_category_mapping.build_xianyu_raw_category_summary_with_session",
            return_value={
                "scannedItemCount": 4,
                "items": [
                    {
                        "xianyuCCatId": "ccat-1",
                        "xianyuCatId": "cat-1",
                        "xianyuTbCatId": "tb-1",
                        "itemCount": 4,
                        "sampleItemIds": ["item-1", "item-2"],
                        "sampleTitles": ["title-1", "title-2"],
                        "sourceKeywords": ["kw-1"],
                        "businessDomains": ["apple_m_series"],
                        "candidateMatchKeys": ["C_CAT:ccat-1", "CAT_TB:cat-1:tb-1"],
                        "resolvedMapping": None,
                        "needsOnboarding": True,
                    }
                ],
            },
        ):
            result = sync_xianyu_category_onboarding_queue_with_session(
                session,
                operator_id="ops-bot",
                dry_run=False,
            )

        created_rows = [obj for obj in session.added if isinstance(obj, XianyuCategoryOnboardingQueue)]
        self.assertEqual(result["createdCount"], 1)
        self.assertEqual(result["candidateCount"], 1)
        self.assertEqual(len(created_rows), 1)
        self.assertEqual(created_rows[0].status, "PENDING")
        self.assertEqual(created_rows[0].match_key, "C_CAT:ccat-1")

    def test_persist_xianyu_category_onboarding_with_session_resolves_queue_row(self) -> None:
        category = SimpleNamespace(id="cat-apple")
        template = SimpleNamespace(id="tpl-apple")
        queue_row = XianyuCategoryOnboardingQueue(
            match_scope=XianyuCategoryMatchScope.C_CAT,
            match_key="C_CAT:126854525",
            xianyu_c_cat_id="126854525",
            status="PENDING",
            metadata_json={"candidateMatchKeys": ["C_CAT:126854525", "CAT_TB:50025387:50014945"]},
        )
        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(scalar=None),
                _FakeExecuteResult(rows=[queue_row]),
            ],
            categories={"cat-apple": category},
            templates={"tpl-apple": template},
        )

        result = persist_xianyu_category_onboarding_with_session(
            session,
            payload={
                "requestId": "req-2",
                "categoryId": "cat-apple",
                "templateId": "tpl-apple",
                "mappings": [
                    {"matchScope": "CAT_TB", "xianyuCatId": "50025387", "xianyuTbCatId": "50014945"},
                ],
            },
            operator_id="ops-bot",
            dry_run=False,
        )

        self.assertEqual(result["resolvedQueueCount"], 1)
        self.assertEqual(queue_row.status, "RESOLVED")
        self.assertEqual((queue_row.resolved_mapping_json or {})["matchKey"], "CAT_TB:50025387:50014945")

    def test_list_xianyu_category_onboarding_queue_with_session_returns_rows(self) -> None:
        pending_row = XianyuCategoryOnboardingQueue(
            match_scope=XianyuCategoryMatchScope.CAT_TB,
            match_key="CAT_TB:cat-1:tb-1",
            xianyu_cat_id="cat-1",
            xianyu_tb_cat_id="tb-1",
            status="PENDING",
            item_count_snapshot=5,
        )
        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(scalar=1),
                _FakeExecuteResult(rows=[pending_row]),
            ]
        )

        result = list_xianyu_category_onboarding_queue_with_session(
            session,
            include_closed=False,
            limit=20,
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["status"], "PENDING")

    def test_serialize_xianyu_category_onboarding_queue_converts_datetimes_to_iso_strings(self) -> None:
        queue_row = XianyuCategoryOnboardingQueue(
            match_scope=XianyuCategoryMatchScope.C_CAT,
            match_key="C_CAT:126864782",
            xianyu_c_cat_id="126864782",
            status="PENDING",
            metadata_json={"seenAt": datetime(2026, 4, 6, 10, 30, tzinfo=UTC)},
            resolved_mapping_json={"resolvedAt": datetime(2026, 4, 6, 10, 31, tzinfo=UTC)},
        )
        queue_row.created_at = datetime(2026, 4, 6, 10, 32, tzinfo=UTC)
        queue_row.updated_at = datetime(2026, 4, 6, 10, 33, tzinfo=UTC)

        payload = serialize_xianyu_category_onboarding_queue(queue_row)

        self.assertEqual(payload["createdAt"], "2026-04-06T10:32:00+00:00")
        self.assertEqual(payload["updatedAt"], "2026-04-06T10:33:00+00:00")
        self.assertEqual(payload["metadata"]["seenAt"], "2026-04-06T10:30:00+00:00")
        self.assertEqual(payload["resolvedMapping"]["resolvedAt"], "2026-04-06T10:31:00+00:00")

    def test_update_xianyu_category_onboarding_queue_status_with_session_updates_row(self) -> None:
        queue_row = XianyuCategoryOnboardingQueue(
            id="queue-1",
            match_scope=XianyuCategoryMatchScope.C_CAT,
            match_key="C_CAT:126854525",
            xianyu_c_cat_id="126854525",
            status="PENDING",
        )
        session = _FakeSession(execute_results=[_FakeExecuteResult(scalar=queue_row)])

        result = update_xianyu_category_onboarding_queue_status_with_session(
            session,
            operator_id="ops-bot",
            status="in_progress",
            queue_id="queue-1",
            owner_operator_id="alice",
            status_note="picked up",
            dry_run=False,
        )

        self.assertEqual(result["queue"]["status"], "IN_PROGRESS")
        self.assertEqual(queue_row.owner_operator_id, "alice")
        self.assertEqual(queue_row.status_note, "picked up")


if __name__ == "__main__":
    unittest.main()
