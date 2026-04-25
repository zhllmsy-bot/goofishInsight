from __future__ import annotations

import json
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from goofish_insight.domain.catalog.blueprints import (
    build_blueprint_template_detail,
    get_catalog_backfill_blueprint,
)
from goofish_insight.models import Item
from goofish_insight.specs import (
    SpecEnrichmentCandidate,
    apply_runtime_context_to_candidate,
    build_system_prompt,
    build_user_prompt,
    candidate_from_llm_payload,
    enrich_candidate_with_catalog_attributes,
    extract_rule_specs,
    lens_title_is_non_target_body_listing,
    anthropic_messages_url,
    load_template_detail_for_business_domain,
    load_template_detail_for_item,
    openai_chat_completions_url,
)


class _FakeScalarResult:
    def __init__(self, value) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        values = self.value if isinstance(self.value, list) else ([] if self.value is None else [self.value])

        class _Rows:
            def __init__(self, rows) -> None:
                self.rows = rows

            def all(self):
                return list(self.rows)

        return _Rows(values)


class _FakeSession:
    def __init__(self, execute_values, *, get_map=None) -> None:
        self.execute_values = list(execute_values)
        self.get_map = get_map or {}

    def execute(self, stmt):
        value = self.execute_values.pop(0) if self.execute_values else None
        return _FakeScalarResult(value)

    def get(self, model, key):
        return self.get_map.get((getattr(model, "__name__", ""), key))


class SpecsDynamicTemplateTests(unittest.TestCase):
    def test_ark_compatible_urls_are_normalized(self) -> None:
        self.assertEqual(
            openai_chat_completions_url("https://ark.cn-beijing.volces.com/api/coding/v3"),
            "https://ark.cn-beijing.volces.com/api/coding/v3/chat/completions",
        )
        self.assertEqual(
            anthropic_messages_url("https://ark.cn-beijing.volces.com/api/coding"),
            "https://ark.cn-beijing.volces.com/api/coding/messages",
        )

    def test_build_user_prompt_includes_catalog_template_attributes(self) -> None:
        blueprint = get_catalog_backfill_blueprint("apple_m_series")
        assert blueprint is not None
        template_detail = build_blueprint_template_detail(blueprint)
        item = Item(
            item_id="apple-item-1",
            task_id=1,
            business_domain="apple_m_series",
            target_category_id="cat-apple",
            resolved_category_id="cat-apple",
            resolved_template_id=template_detail["template"]["id"],
            category_validation_status="MATCH_TASK_CATEGORY",
            title="MacBook Pro M3 Pro 18G 512G",
            normalized_model_family="MacBook Pro",
            normalized_model="MacBook Pro",
            normalized_chip="M3 Pro",
            normalized_memory_gb=18,
            normalized_storage_gb=512,
        )
        candidate = enrich_candidate_with_catalog_attributes(
            item,
            SpecEnrichmentCandidate(
                status="partial",
                product_line="MacBook Pro",
                model_name="MacBook Pro",
                chip_family="M3 Pro",
                memory_gb=18,
                storage_gb=512,
            ),
            template_detail=template_detail,
        )

        prompt = build_user_prompt(
            item=item,
            rule_candidate=candidate,
            template_detail=template_detail,
            runtime_context={"promptProfile": "apple_computer_extract_v1"},
            model_catalog=[
                {
                    "id": "model-apple-1",
                    "modelCode": "mbp_14_m3_pro",
                    "modelName": "MacBook Pro 14 M3 Pro",
                    "aliases": [{"aliasText": "MacBook Pro M3 Pro", "aliasNormalized": "macbookprom3pro"}],
                }
            ],
        )
        payload = json.loads(prompt)
        template_attributes = payload["catalog_template"]["attributes"]
        model_catalog_row = payload["model_catalog"][0]
        rule_candidate_payload = payload["rule_candidate"]

        self.assertEqual(payload["item_id"], "apple-item-1")
        self.assertEqual(payload["business_domain"], "apple_m_series")
        self.assertIn("catalog_template", payload)
        self.assertEqual(set(payload["catalog_template"].keys()), {"attributes"})
        self.assertTrue(any(row["attributeCode"] == "chip_family" for row in template_attributes))
        self.assertTrue(any(row["valueScope"] == "SKU" for row in template_attributes))
        self.assertIn("catalogAttributes", rule_candidate_payload)
        self.assertNotIn("resolved_category_id", payload)
        self.assertNotIn("prompt_profile", payload)
        self.assertNotIn("source_keyword", payload)
        self.assertNotIn("status", rule_candidate_payload)
        self.assertNotIn("confidence", rule_candidate_payload)
        self.assertNotIn("id", model_catalog_row)
        self.assertNotIn("aliasNormalized", json.dumps(model_catalog_row, ensure_ascii=False))
        self.assertEqual(model_catalog_row["aliases"], [{"aliasText": "MacBook Pro M3 Pro"}])

    def test_candidate_from_llm_payload_maps_dynamic_catalog_attributes(self) -> None:
        blueprint = get_catalog_backfill_blueprint("garmin")
        assert blueprint is not None
        template_detail = build_blueprint_template_detail(blueprint)
        item = Item(
            item_id="garmin-item-1",
            task_id=1,
            business_domain="garmin",
            title="佳明 Fenix 7 Solar",
            normalized_brand="Garmin",
        )

        candidate = candidate_from_llm_payload(
            {
                "status": "complete",
                "confidence": 0.82,
                "needs_review": False,
                "spuAttributes": [
                    {"attributeCode": "product_line", "textValue": "Fenix"},
                    {"attributeCode": "model_name", "textValue": "Fenix 7"},
                    {"attributeCode": "display_type", "textValue": "AMOLED"},
                    {"attributeCode": "case_size_mm", "numberValue": 47},
                    {"attributeCode": "is_solar", "boolValue": True},
                    {"attributeCode": "edition_tags", "jsonValue": ["Solar", "Sapphire"]},
                ],
                "evidence": {"source": "listing_title"},
            },
            item=item,
            provider="openai_compatible",
            model="qwen",
            template_detail=template_detail,
        )

        self.assertEqual(candidate.product_line, "Fenix")
        self.assertEqual(candidate.model_name, "Fenix 7")
        self.assertEqual(candidate.display_type, "AMOLED")
        self.assertEqual(candidate.case_size_mm, 47)
        self.assertTrue(candidate.is_solar)
        self.assertEqual(candidate.edition_tags, ["Solar", "Sapphire"])
        self.assertEqual(
            candidate.extraction_payload["catalogAttributes"]["spuAttributes"][0]["attributeCode"],
            "product_line",
        )
        self.assertEqual(candidate.confidence, Decimal("0.82"))

    def test_candidate_from_llm_payload_normalizes_noncanonical_status(self) -> None:
        blueprint = get_catalog_backfill_blueprint("garmin")
        assert blueprint is not None
        template_detail = build_blueprint_template_detail(blueprint)
        item = Item(
            item_id="garmin-item-2",
            task_id=1,
            business_domain="garmin",
            title="佳明 Fenix 7 Solar",
            normalized_brand="Garmin",
        )

        candidate = candidate_from_llm_payload(
            {
                "status": "success",
                "confidence": 0.91,
                "spuAttributes": [
                    {"attributeCode": "product_line", "textValue": "Fenix"},
                    {"attributeCode": "model_name", "textValue": "Fenix 7"},
                ],
            },
            item=item,
            provider="openai_compatible",
            model="qwen",
            template_detail=template_detail,
        )

        self.assertEqual(candidate.status, "partial")
        self.assertIn("case_size_mm", candidate.extraction_payload["contract"]["missingRequiredFields"])
        self.assertEqual(candidate.extraction_payload["rawStatus"], "success")

    def test_build_system_prompt_constrains_status_values(self) -> None:
        prompt = build_system_prompt(prompt_profile="apple_computer_extract_v1")
        self.assertIn("status must be one of complete, partial, or unresolved", prompt)
        self.assertIn("Do not use valid, success, resolved", prompt)

    def test_apply_runtime_context_canonicalizes_lens_catalog_values(self) -> None:
        template_detail = {
            "category": {"id": "cat-lens", "code": "camera_interchangeable_lens"},
            "template": {"id": "tpl-lens", "version": 1},
            "items": [
                {
                    "attributeCode": "brand_name",
                    "attributeName": "品牌名称",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "isSale": False,
                    "sortNo": 10,
                },
                {
                    "attributeCode": "model_name",
                    "attributeName": "型号名称",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "isSale": False,
                    "sortNo": 20,
                },
                {
                    "attributeCode": "lens_series",
                    "attributeName": "镜头系列",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "isSale": False,
                    "sortNo": 30,
                },
                {
                    "attributeCode": "mount_system",
                    "attributeName": "卡口系统",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "isSale": False,
                    "sortNo": 40,
                },
                {
                    "attributeCode": "focal_length_range",
                    "attributeName": "焦段",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "isSale": False,
                    "sortNo": 50,
                },
                {
                    "attributeCode": "max_aperture",
                    "attributeName": "最大光圈",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "isSale": False,
                    "sortNo": 60,
                },
            ],
        }
        item = Item(
            item_id="lens-item-1",
            task_id=1,
            business_domain="camera_interchangeable_lens",
            resolved_category_id="cat-lens",
            resolved_template_id=template_detail["template"]["id"],
            title="尼康Z 70-200 f2.8，成像对焦都没问题",
            normalized_model="尼康Z 70-200 f/2.8",
        )

        candidate = SpecEnrichmentCandidate(
            extractor_type="hybrid",
            status="partial",
            confidence=Decimal("0.85"),
            brand="Nikon/尼康",
            product_line="S系列",
            model_family="S系列",
            model_name="尼康Z 70-200 f/2.8",
            extraction_payload={
                "catalogAttributes": {
                    "spuAttributes": [
                        {"attributeCode": "brand_name", "textValue": "Nikon/尼康"},
                        {"attributeCode": "model_name", "textValue": "尼康Z 70-200 f/2.8"},
                        {"attributeCode": "model_name", "textValue": "NIKKOR Z 70-200mm f/2.8 VR S"},
                        {"attributeCode": "lens_series", "textValue": "S系列"},
                        {"attributeCode": "mount_system", "textValue": "Z卡口"},
                        {"attributeCode": "focal_length_range", "textValue": "70-200"},
                        {"attributeCode": "max_aperture", "textValue": "F2.8"},
                    ],
                    "skuAttributes": [],
                    "saleAttributes": [],
                }
            },
        )

        resolved = apply_runtime_context_to_candidate(
            item=item,
            candidate=candidate,
            runtime_context={
                "templateDetail": template_detail,
                "promptProfile": "camera_interchangeable_lens_extract_v1",
                "modelCatalog": [
                    {
                        "id": "model-lens-1",
                        "brandName": "Nikon",
                        "seriesName": "NIKKOR Z",
                        "modelCode": "nikon_z_70_200_f28_vr_s",
                        "modelName": "NIKKOR Z 70-200mm f/2.8 VR S",
                        "aliases": [
                            {"aliasText": "尼康 Z 70-200 2.8 S", "aliasNormalized": "尼康z7020028s"}
                        ],
                    }
                ],
            },
        )

        self.assertEqual(resolved.model_catalog_id, "model-lens-1")
        self.assertEqual(resolved.brand, "尼康")
        self.assertEqual(resolved.product_line, "NIKKOR Z")
        self.assertEqual(resolved.model_family, "NIKKOR Z")
        self.assertEqual(resolved.model_name, "NIKKOR Z 70-200mm f/2.8 VR S")

        spu_rows = resolved.extraction_payload["catalogAttributes"]["spuAttributes"]
        model_name_rows = [row for row in spu_rows if row["attributeCode"] == "model_name"]
        lens_series_rows = [row for row in spu_rows if row["attributeCode"] == "lens_series"]
        brand_rows = [row for row in spu_rows if row["attributeCode"] == "brand_name"]
        mount_rows = [row for row in spu_rows if row["attributeCode"] == "mount_system"]
        focal_rows = [row for row in spu_rows if row["attributeCode"] == "focal_length_range"]
        aperture_rows = [row for row in spu_rows if row["attributeCode"] == "max_aperture"]

        self.assertEqual(model_name_rows, [{"attributeCode": "model_name", "textValue": "NIKKOR Z 70-200mm f/2.8 VR S"}])
        self.assertEqual(lens_series_rows, [{"attributeCode": "lens_series", "textValue": "NIKKOR Z"}])
        self.assertEqual(brand_rows, [{"attributeCode": "brand_name", "textValue": "尼康"}])
        self.assertEqual(mount_rows, [{"attributeCode": "mount_system", "textValue": "尼康Z卡口"}])
        self.assertEqual(focal_rows, [{"attributeCode": "focal_length_range", "textValue": "70-200mm"}])
        self.assertEqual(aperture_rows, [{"attributeCode": "max_aperture", "textValue": "f/2.8"}])

    def test_apply_runtime_context_canonicalizes_lens_shorthand_without_catalog_match(self) -> None:
        template_detail = {
            "category": {"id": "cat-lens", "code": "camera_interchangeable_lens"},
            "template": {"id": "tpl-lens", "version": 1},
            "items": [
                {
                    "attributeCode": "model_name",
                    "attributeName": "型号名称",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "isSale": False,
                    "sortNo": 20,
                },
                {
                    "attributeCode": "lens_series",
                    "attributeName": "镜头系列",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "isSale": False,
                    "sortNo": 30,
                },
            ],
        }
        item = Item(
            item_id="lens-item-2",
            task_id=1,
            business_domain="camera_interchangeable_lens",
            resolved_category_id="cat-lens",
            resolved_template_id=template_detail["template"]["id"],
            title="尼康 Z 24-70 S 镜头",
            normalized_brand="尼康",
            normalized_model="Z 24-70 S",
        )
        candidate = SpecEnrichmentCandidate(
            extractor_type="hybrid",
            status="partial",
            confidence=Decimal("0.70"),
            brand="尼康",
            model_name="Z 24-70 S",
            extraction_payload={
                "catalogAttributes": {
                    "spuAttributes": [{"attributeCode": "model_name", "textValue": "Z 24-70 S"}],
                    "skuAttributes": [],
                    "saleAttributes": [],
                }
            },
        )

        resolved = apply_runtime_context_to_candidate(
            item=item,
            candidate=candidate,
            runtime_context={
                "templateDetail": template_detail,
                "promptProfile": "camera_interchangeable_lens_extract_v1",
                "modelCatalog": [],
            },
        )

        self.assertEqual(resolved.model_name, "NIKKOR Z 24-70mm S")
        self.assertEqual(resolved.product_line, "NIKKOR Z")
        self.assertEqual(resolved.model_family, "NIKKOR Z")

    def test_extract_lens_rule_marks_camera_body_listing_as_non_target(self) -> None:
        item = Item(
            item_id="lens-body-mismatch-1",
            task_id=1,
            business_domain="camera_interchangeable_lens",
            title="全新尼康Z7二代机身 全画幅高清数码微单 配件齐全 z72套",
        )

        candidate = extract_rule_specs(item)

        self.assertEqual(candidate.status, "unresolved")
        self.assertEqual(candidate.confidence, Decimal("0.20"))
        self.assertEqual(candidate.evidence.get("reason"), "non_target_camera_body")
        self.assertIsNone(candidate.model_name)
        self.assertFalse(candidate.needs_review)
        self.assertTrue(lens_title_is_non_target_body_listing(item.title))

    def test_extract_lens_rule_builds_confident_nikon_z_model_name(self) -> None:
        item = Item(
            item_id="lens-rule-24-70",
            task_id=1,
            business_domain="camera_interchangeable_lens",
            title="尼康 Z 24-70 f2.8 S 镜头",
            normalized_brand="尼康",
        )

        candidate = extract_rule_specs(item)

        self.assertEqual(candidate.status, "complete")
        self.assertEqual(candidate.model_name, "NIKKOR Z 24-70mm f/2.8 S")
        self.assertEqual(candidate.product_line, "NIKKOR Z")
        self.assertGreaterEqual(candidate.confidence or Decimal("0"), Decimal("0.75"))

    def test_load_template_detail_for_item_prefers_xianyu_mapping(self) -> None:
        blueprint = get_catalog_backfill_blueprint("apple_m_series")
        assert blueprint is not None
        template_detail = build_blueprint_template_detail(blueprint)
        item = Item(
            item_id="mapped-item-1",
            task_id=1,
            business_domain="unknown_domain",
            title="MacBook Pro M3 Pro 18G 512G",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="50014945",
        )

        with patch(
            "goofish_insight.specs.load_xianyu_catalog_template_detail_for_item",
            return_value=template_detail,
        ), patch("goofish_insight.specs.session_scope") as session_scope_mock:
            session_scope_mock.return_value.__enter__.return_value = _FakeSession([])
            session_scope_mock.return_value.__exit__.return_value = False
            detail = load_template_detail_for_item(item)

        self.assertEqual(detail["template"]["id"], template_detail["template"]["id"])

    def test_load_template_detail_for_item_prefers_resolved_template(self) -> None:
        runtime_detail = {
            "category": {"id": "cat-phone", "code": "phone"},
            "template": {"id": "tpl-resolved", "version": 2},
            "items": [],
        }
        item = Item(
            item_id="phone-item-1",
            task_id=1,
            business_domain="phone",
            resolved_category_id="cat-phone",
            resolved_template_id="tpl-resolved",
            title="iPhone 15 Pro",
        )

        fake_session = _FakeSession(
            [None, None],
            get_map={("Category", "cat-phone"): SimpleNamespace(id="cat-phone", code="phone")},
        )

        class _FakeSessionScope:
            def __enter__(self):
                return fake_session

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("goofish_insight.specs.session_scope", return_value=_FakeSessionScope()), patch(
            "goofish_insight.specs.build_catalog_template_detail",
            return_value=runtime_detail,
        ):
            detail = load_template_detail_for_item(item)

        self.assertEqual(detail["template"]["id"], "tpl-resolved")

    def test_load_template_detail_for_business_domain_prefers_category_runtime_profile(self) -> None:
        runtime_detail = {
            "category": {"id": "cat-lens", "code": "camera_interchangeable_lens"},
            "template": {"id": "tpl-runtime", "version": 3},
            "items": [],
        }
        fake_session = _FakeSession(
            [
                SimpleNamespace(id="cat-lens", code="camera_interchangeable_lens"),
                SimpleNamespace(active_template_id="tpl-runtime", status="ACTIVE"),
            ]
        )

        class _FakeSessionScope:
            def __enter__(self):
                return fake_session

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("goofish_insight.specs.session_scope", return_value=_FakeSessionScope()), patch(
            "goofish_insight.specs.build_catalog_template_detail",
            return_value=runtime_detail,
        ):
            detail = load_template_detail_for_business_domain("camera_interchangeable_lens")

        self.assertEqual(detail["template"]["id"], "tpl-runtime")

    def test_load_template_detail_for_business_domain_injects_common_runtime_attributes(self) -> None:
        runtime_detail = {
            "category": {"id": "cat-airpods", "code": "apple_airpods"},
            "template": {"id": "tpl-airpods", "version": 1},
            "items": [
                {
                    "attributeCode": "brand_name",
                    "attributeName": "品牌",
                    "dataType": "TEXT",
                    "valueScope": "SPU",
                    "isMulti": False,
                    "isRequired": False,
                    "isSale": False,
                    "isFilter": True,
                    "isSearch": False,
                    "isDisplay": True,
                    "sortNo": 10,
                    "options": [],
                }
            ],
        }
        common_generation_row = SimpleNamespace(
            id="attr-generation",
            code="generation",
            name="代际",
            data_type=SimpleNamespace(value="TEXT"),
            value_scope="SPU",
            is_multi=False,
            unit=None,
            options=[],
            validation_schema={"runtimeCommon": True},
        )
        common_brand_row = SimpleNamespace(
            id="attr-brand",
            code="brand_name",
            name="品牌",
            data_type=SimpleNamespace(value="TEXT"),
            value_scope="SPU",
            is_multi=False,
            unit=None,
            options=[],
            validation_schema={"runtimeCommon": True},
        )
        fake_session = _FakeSession(
            [
                SimpleNamespace(id="cat-airpods", code="apple_airpods"),
                SimpleNamespace(active_template_id="tpl-airpods", status="ACTIVE"),
            ]
        )

        class _FakeSessionScope:
            def __enter__(self):
                return fake_session

            def __exit__(self, exc_type, exc, tb):
                return False

        with patch("goofish_insight.specs.session_scope", return_value=_FakeSessionScope()), patch(
            "goofish_insight.specs.build_catalog_template_detail",
            return_value=runtime_detail,
        ), patch(
            "goofish_insight.specs._load_common_runtime_attribute_rows",
            return_value=[common_brand_row, common_generation_row],
        ):
            detail = load_template_detail_for_business_domain("apple_airpods")

        self.assertEqual(detail["template"]["id"], "tpl-airpods")
        item_by_code = {row["attributeCode"]: row for row in detail["items"]}
        self.assertIn("generation", item_by_code)
        self.assertTrue(item_by_code["brand_name"]["isRequired"])
        self.assertTrue(item_by_code["brand_name"]["isSearch"])


if __name__ == "__main__":
    unittest.main()
