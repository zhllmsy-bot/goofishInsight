from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from goofish_insight.application.services.category_ai_config import (
    CategoryAIConfigError,
    apply_category_ai_draft_with_session,
    generate_category_ai_draft_with_session,
    normalize_category_ai_draft,
)


class CategoryAIConfigServiceTests(unittest.TestCase):
    def test_normalize_category_ai_draft_canonicalizes_lens_profile(self) -> None:
        payload = {
            "category": {
                "code": "interchangeable_lens",
                "name": "可换镜头",
                "path": "photo/interchangeable_lens",
                "level": 2,
            },
            "runtime": {
                "promptProfile": "snake_case_extract_v1",
                "validatorProfile": "optional",
            },
            "attributes": [
                {"code": "品牌", "name": "品牌", "dataType": "TEXT", "valueScope": "SPU"},
                {"code": "型号", "name": "型号", "dataType": "TEXT", "valueScope": "SPU"},
                {"code": "焦段", "name": "焦段", "dataType": "TEXT", "valueScope": "SPU"},
                {"code": "sensor_format", "name": "传感器画幅", "dataType": "TEXT", "valueScope": "SPU"},
            ],
            "template": {
                "status": "PUBLISHED",
                "items": [
                    {"attributeCode": "brand_name"},
                    {"attributeCode": "model_name"},
                    {"attributeCode": "focal_length_range"},
                    {"attributeCode": "sensor_format"},
                ],
            },
        }

        result = normalize_category_ai_draft(
            payload,
            description="新增尼康可换镜头大类",
            category_code_hint=None,
        )

        self.assertEqual(result["category"]["code"], "camera_interchangeable_lens")
        self.assertEqual(result["runtime"]["promptProfile"], "camera_interchangeable_lens_extract_v1")
        self.assertEqual(result["runtime"]["validatorProfile"], "lens_basic_v1")
        self.assertIn("brand_name", [row["code"] for row in result["attributes"]])
        self.assertIn("model_name", [row["code"] for row in result["attributes"]])
        self.assertIn("focal_length_type", [row["code"] for row in result["attributes"]])
        focal_type = next(row for row in result["attributes"] if row["code"] == "focal_length_type")
        self.assertEqual(focal_type["dataType"], "ENUM")
        self.assertEqual([option["optionCode"] for option in focal_type["options"]], ["prime", "zoom"])
        self.assertNotIn("sensor_format", [row["code"] for row in result["attributes"]])
        self.assertIn(
            "focal_length_type",
            [row["attributeCode"] for row in result["template"]["items"]],
        )
        self.assertNotIn("sensor_format", [row["attributeCode"] for row in result["template"]["items"]])
        governance = result.get("governance") or {}
        self.assertTrue(governance.get("policyApplied"))
        self.assertEqual(governance.get("canonicalCategoryCode"), "camera_interchangeable_lens")
        self.assertTrue(governance.get("sanitizationApplied"))
        self.assertIn("sensor_format", governance.get("removedAttributeCodes") or [])

    def test_normalize_category_ai_draft_merges_subcategory_into_canonical_family(self) -> None:
        payload = {
            "category": {
                "code": "camera_prime_lens",
                "name": "定焦镜头",
                "path": "camera/prime-lens",
                "level": 2,
            },
            "runtime": {
                "promptProfile": "camera_prime_lens_extract_v1",
            },
            "attributes": [
                {"code": "brand_name", "name": "品牌", "dataType": "TEXT", "valueScope": "SPU"},
                {"code": "model_name", "name": "型号", "dataType": "TEXT", "valueScope": "SPU"},
            ],
            "template": {
                "items": [
                    {"attributeCode": "brand_name"},
                    {"attributeCode": "model_name"},
                ]
            },
        }

        result = normalize_category_ai_draft(
            payload,
            description="新增尼康 50 1.2 定焦镜头大类",
            category_code_hint="camera_prime_lens",
        )

        self.assertEqual(result["category"]["code"], "camera_interchangeable_lens")
        self.assertEqual(result["runtime"]["promptProfile"], "camera_interchangeable_lens_extract_v1")
        governance = result.get("governance") or {}
        self.assertTrue(governance.get("policyApplied"))
        self.assertTrue(governance.get("categoryCodeAdjusted"))
        self.assertEqual(governance.get("canonicalCategoryCode"), "camera_interchangeable_lens")
        signal_attrs = [row.get("attributeCode") for row in governance.get("variantSignals") or []]
        self.assertIn("focal_length_type", signal_attrs)
        runtime_governance = (result.get("runtime") or {}).get("runtimeMetadata", {}).get("taxonomyGovernance", {})
        self.assertEqual(runtime_governance.get("canonicalCategoryCode"), "camera_interchangeable_lens")

    @patch("goofish_insight.application.services.category_ai_config.call_openai_compatible_chat")
    @patch("goofish_insight.application.services.category_ai_config.get_settings")
    @patch("goofish_insight.application.services.category_ai_config.llm_is_configured")
    def test_generate_category_ai_draft_with_session_returns_draft(
        self,
        llm_configured_mock,
        settings_mock,
        call_llm_mock,
    ) -> None:
        llm_configured_mock.return_value = True
        settings_mock.return_value = SimpleNamespace(
            ai_provider="ark_responses",
            ai_base_url="https://example.com/api/v3",
            ai_api_key="test-key",
            ai_model="doubao-seed-1-6-flash-250828",
            ai_timeout_sec=30,
            ai_enable_thinking=False,
        )
        call_llm_mock.return_value = {
            "choices": [
                {
                    "message": {
                        "content": '{"category":{"code":"camera_interchangeable_lens","name":"可换镜头","path":"camera/interchangeable-lens","level":2},"runtime":{"promptProfile":"camera_interchangeable_lens_extract_v1"},"attributes":[{"code":"brand_name","name":"品牌","dataType":"TEXT","valueScope":"SPU"},{"code":"model_name","name":"型号","dataType":"TEXT","valueScope":"SPU"}],"template":{"items":[{"attributeCode":"brand_name"},{"attributeCode":"model_name"}]}}'
                    }
                }
            ]
        }

        result = generate_category_ai_draft_with_session(
            None,  # service function doesn't use the session object
            description="新增镜头大类",
            category_code_hint=None,
        )

        self.assertEqual(result["provider"], "ark_responses")
        self.assertEqual(result["model"], "doubao-seed-1-6-flash-250828")
        self.assertEqual(result["draft"]["category"]["code"], "camera_interchangeable_lens")

    @patch("goofish_insight.application.services.category_ai_config.call_openai_compatible_chat")
    @patch("goofish_insight.application.services.category_ai_config.get_settings")
    @patch("goofish_insight.application.services.category_ai_config.llm_is_configured")
    def test_generate_category_ai_draft_with_session_parses_json_with_trailing_text(
        self,
        llm_configured_mock,
        settings_mock,
        call_llm_mock,
    ) -> None:
        llm_configured_mock.return_value = True
        settings_mock.return_value = SimpleNamespace(
            ai_provider="ark_responses",
            ai_base_url="https://example.com/api/v3",
            ai_api_key="test-key",
            ai_model="doubao-seed-1-6-flash-250828",
            ai_timeout_sec=30,
            ai_enable_thinking=False,
        )
        call_llm_mock.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"category":{"code":"camera_interchangeable_lens","name":"可换镜头","path":"camera/interchangeable-lens","level":2},'
                            '"runtime":{"promptProfile":"camera_interchangeable_lens_extract_v1"},'
                            '"attributes":[{"code":"brand_name","name":"品牌","dataType":"TEXT","valueScope":"SPU"},{"code":"model_name","name":"型号","dataType":"TEXT","valueScope":"SPU"}],'
                            '"template":{"items":[{"attributeCode":"brand_name"},{"attributeCode":"model_name"}]}}\n'
                            "additional trailing assistant text"
                        )
                    }
                }
            ]
        }

        result = generate_category_ai_draft_with_session(
            None,
            description="新增镜头大类",
            category_code_hint=None,
        )
        self.assertEqual(result["draft"]["category"]["code"], "camera_interchangeable_lens")

    @patch("goofish_insight.application.services.category_ai_config.normalize_category_ai_draft")
    def test_apply_category_ai_draft_with_session_blocks_existing_category_by_default(
        self,
        normalize_mock,
    ) -> None:
        normalize_mock.return_value = {
            "category": {"code": "camera_interchangeable_lens", "name": "相机", "path": "camera", "level": 2, "status": "ACTIVE"},
            "runtime": {"promptProfile": "camera_interchangeable_lens_extract_v1", "runtimeStatus": "ACTIVE"},
            "attributes": [{"code": "brand_name", "name": "品牌", "dataType": "TEXT", "valueScope": "SPU"}],
            "template": {"items": [{"attributeCode": "brand_name"}], "status": "PUBLISHED", "bindAsActiveTemplate": True},
            "governance": {},
        }
        session = MagicMock()
        session.execute.return_value.scalar_one_or_none.return_value = SimpleNamespace(
            id="cat-1",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="camera/interchangeable-lens",
            level=2,
            status="ACTIVE",
        )

        with self.assertRaises(CategoryAIConfigError):
            apply_category_ai_draft_with_session(
                session,
                operator_id="ops-bot",
                draft={"category": {"code": "camera_interchangeable_lens"}},
                dry_run=False,
            )

    @patch("goofish_insight.application.services.category_ai_config._next_template_version")
    @patch("goofish_insight.application.services.category_ai_config.upsert_template_config_with_session")
    @patch("goofish_insight.application.services.category_ai_config.upsert_attribute_config_with_session")
    @patch("goofish_insight.application.services.category_ai_config.upsert_category_config_with_session")
    @patch("goofish_insight.application.services.category_ai_config.normalize_category_ai_draft")
    def test_apply_category_ai_draft_with_session_existing_category_keeps_identity_and_no_active_rebind(
        self,
        normalize_mock,
        upsert_category_mock,
        upsert_attribute_mock,
        upsert_template_mock,
        next_version_mock,
    ) -> None:
        normalize_mock.return_value = {
            "category": {"code": "camera_interchangeable_lens", "name": "相机", "path": "camera", "level": 2, "status": "ACTIVE"},
            "runtime": {"promptProfile": "camera_interchangeable_lens_extract_v1", "runtimeStatus": "ACTIVE"},
            "attributes": [{"code": "brand_name", "name": "品牌", "dataType": "TEXT", "valueScope": "SPU"}],
            "template": {"items": [{"attributeCode": "brand_name"}], "status": "PUBLISHED", "bindAsActiveTemplate": True},
            "governance": {},
        }
        existing = SimpleNamespace(
            id="cat-1",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="camera/interchangeable-lens",
            level=2,
            status="ACTIVE",
            runtime_profile=SimpleNamespace(active_template_id="tpl-active-1"),
        )
        session = MagicMock()
        first_exec = MagicMock()
        first_exec.scalar_one_or_none.return_value = existing
        second_exec = MagicMock()
        second_exec.scalar_one_or_none.return_value = "tpl-active-1"
        session.execute.side_effect = [first_exec, second_exec]
        upsert_category_mock.return_value = {"category": {"id": "cat-1", "code": "camera_interchangeable_lens"}}
        upsert_attribute_mock.return_value = {"attribute": {"id": "attr-1", "code": "brand_name"}}
        upsert_template_mock.return_value = {"template": {"id": "tpl-1"}, "runtimeProfile": None}
        next_version_mock.return_value = 9

        result = apply_category_ai_draft_with_session(
            session,
            operator_id="ops-bot",
            draft={"category": {"code": "camera_interchangeable_lens"}},
            dry_run=False,
            allow_existing_category_update=True,
            allow_active_template_rebind=False,
        )

        category_payload = upsert_category_mock.call_args.kwargs["payload"]
        self.assertEqual(category_payload["name"], "可换镜头")
        self.assertEqual(category_payload["path"], "camera/interchangeable-lens")
        self.assertEqual(category_payload["activeTemplateId"], "tpl-active-1")
        template_payload = upsert_template_mock.call_args.kwargs["payload"]
        self.assertFalse(template_payload["bindAsActiveTemplate"])
        self.assertTrue(result["bindRequested"])
        self.assertFalse(result["bindApplied"])


if __name__ == "__main__":
    unittest.main()
