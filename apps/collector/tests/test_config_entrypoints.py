from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from goofish_insight.webapp import create_app


class ConfigEntrypointTests(unittest.TestCase):
    def test_config_root_page_renders_react_shell(self) -> None:
        client = TestClient(create_app())

        response = client.get("/config")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="root"', response.text)

    def test_config_categories_page_renders_react_shell(self) -> None:
        client = TestClient(create_app())

        response = client.get("/config/categories")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="root"', response.text)

    def test_config_categories_list_route_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.list_category_configs",
            return_value={"total": 1, "items": [{"code": "apple_computer"}]},
        ) as list_mock:
            response = client.get("/api/config/categories?status=ACTIVE")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["code"], "apple_computer")
        list_mock.assert_called_once_with(status="ACTIVE")

    def test_config_categories_upsert_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.upsert_category_config",
            return_value={"category": {"code": "garmin_watch", "name": "Garmin手表"}},
        ) as upsert_mock:
            response = client.post(
                "/api/config/categories",
                json={
                    "operatorId": "ops-bot",
                    "apply": True,
                    "payload": {
                        "code": "garmin_watch",
                        "name": "Garmin手表",
                        "path": "wearables/garmin-watch",
                        "level": 2,
                        "promptProfile": "garmin_watch_extract_v1",
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["category"]["code"], "garmin_watch")
        upsert_mock.assert_called_once_with(
            payload={
                "code": "garmin_watch",
                "name": "Garmin手表",
                "path": "wearables/garmin-watch",
                "level": 2,
                "promptProfile": "garmin_watch_extract_v1",
            },
            operator_id="ops-bot",
            dry_run=False,
        )

    def test_config_categories_ai_draft_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.generate_category_ai_draft",
            return_value={"draft": {"category": {"code": "camera_interchangeable_lens"}}},
        ) as draft_mock:
            response = client.post(
                "/api/config/categories/ai-draft",
                json={
                    "description": "做一个尼康可换镜头大类，自动识别型号和焦段光圈",
                    "categoryCodeHint": "camera_interchangeable_lens",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["draft"]["category"]["code"], "camera_interchangeable_lens")
        draft_mock.assert_called_once_with(
            description="做一个尼康可换镜头大类，自动识别型号和焦段光圈",
            category_code_hint="camera_interchangeable_lens",
        )

    def test_config_categories_ai_apply_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.apply_category_ai_draft",
            return_value={
                "category": {"code": "camera_interchangeable_lens"},
                "template": {"id": "tpl-1"},
                "attributeCount": 6,
            },
        ) as apply_mock:
            response = client.post(
                "/api/config/categories/ai-apply",
                json={
                    "operatorId": "ops-bot",
                    "apply": True,
                    "draft": {
                        "category": {"code": "camera_interchangeable_lens", "name": "可换镜头", "path": "camera/interchangeable-lens", "level": 2},
                        "runtime": {"promptProfile": "camera_interchangeable_lens_extract_v1"},
                        "attributes": [{"code": "brand_name", "name": "品牌", "dataType": "TEXT", "valueScope": "SPU"}],
                        "template": {"items": [{"attributeCode": "brand_name"}]},
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["template"]["id"], "tpl-1")
        apply_mock.assert_called_once_with(
            operator_id="ops-bot",
            draft={
                "category": {"code": "camera_interchangeable_lens", "name": "可换镜头", "path": "camera/interchangeable-lens", "level": 2},
                "runtime": {"promptProfile": "camera_interchangeable_lens_extract_v1"},
                "attributes": [{"code": "brand_name", "name": "品牌", "dataType": "TEXT", "valueScope": "SPU"}],
                "template": {"items": [{"attributeCode": "brand_name"}]},
            },
            dry_run=False,
            allow_existing_category_update=False,
            allow_active_template_rebind=False,
        )

    def test_config_categories_ai_apply_route_passes_risk_flags(self) -> None:
        client = TestClient(create_app())
        with patch(
            "goofish_insight.entrypoints.web.routers.config.apply_category_ai_draft",
            return_value={"category": {"code": "phone"}, "template": {"id": "tpl-2"}},
        ) as apply_mock:
            response = client.post(
                "/api/config/categories/ai-apply",
                json={
                    "operatorId": "ops-bot",
                    "apply": True,
                    "allowExistingCategoryUpdate": True,
                    "allowActiveTemplateRebind": True,
                    "draft": {
                        "category": {"code": "phone", "name": "手机", "path": "electronics/phone", "level": 2},
                        "runtime": {"promptProfile": "smartphone_extract_v1"},
                        "attributes": [{"code": "brand_name", "name": "品牌", "dataType": "TEXT", "valueScope": "SPU"}],
                        "template": {"items": [{"attributeCode": "brand_name"}]},
                    },
                },
            )
        self.assertEqual(response.status_code, 200)
        apply_mock.assert_called_once_with(
            operator_id="ops-bot",
            draft={
                "category": {"code": "phone", "name": "手机", "path": "electronics/phone", "level": 2},
                "runtime": {"promptProfile": "smartphone_extract_v1"},
                "attributes": [{"code": "brand_name", "name": "品牌", "dataType": "TEXT", "valueScope": "SPU"}],
                "template": {"items": [{"attributeCode": "brand_name"}]},
            },
            dry_run=False,
            allow_existing_category_update=True,
            allow_active_template_rebind=True,
        )


if __name__ == "__main__":
    unittest.main()
