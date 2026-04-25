from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from goofish_insight.webapp import create_app


class TemplateConfigEntrypointTests(unittest.TestCase):
    def test_config_templates_page_renders_react_shell(self) -> None:
        client = TestClient(create_app())

        response = client.get("/config/templates")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="root"', response.text)

    def test_config_templates_list_route_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.list_template_configs",
            return_value={"total": 1, "items": [{"id": "tpl-1", "categoryCode": "apple_computer"}]},
        ) as list_mock:
            response = client.get("/api/config/templates?status=DRAFT&category_code=apple_computer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["categoryCode"], "apple_computer")
        list_mock.assert_called_once_with(status="DRAFT", category_code="apple_computer")

    def test_config_templates_upsert_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.upsert_template_config",
            return_value={"template": {"id": "tpl-1", "categoryCode": "garmin_watch", "version": 1}},
        ) as upsert_mock:
            response = client.post(
                "/api/config/templates",
                json={
                    "operatorId": "ops-bot",
                    "apply": True,
                    "payload": {
                        "categoryCode": "garmin_watch",
                        "version": 1,
                        "status": "DRAFT",
                        "items": [{"attributeCode": "case_size_mm", "sortNo": 10}],
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["template"]["categoryCode"], "garmin_watch")
        upsert_mock.assert_called_once_with(
            payload={
                "categoryCode": "garmin_watch",
                "version": 1,
                "status": "DRAFT",
                "items": [{"attributeCode": "case_size_mm", "sortNo": 10}],
            },
            operator_id="ops-bot",
            dry_run=False,
        )

    def test_config_templates_diff_preview_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.preview_template_config_diff",
            return_value={"addedAttributeCodes": ["storage_gb"]},
        ) as preview_mock:
            response = client.post(
                "/api/config/templates/diff-preview",
                json={
                    "payload": {
                        "categoryCode": "apple_computer",
                        "items": [{"attributeCode": "storage_gb", "sortNo": 10}],
                    }
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["addedAttributeCodes"], ["storage_gb"])
        preview_mock.assert_called_once_with(
            payload={
                "categoryCode": "apple_computer",
                "items": [{"attributeCode": "storage_gb", "sortNo": 10}],
            }
        )

    def test_category_spec_schema_route_returns_active_schema(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.get_category_spec_schema",
            return_value={
                "categoryCode": "apple_computer",
                "templateVersion": 3,
                "lockingAttrs": ["chip_family", "memory_gb"],
            },
        ) as schema_mock:
            response = client.get("/api/categories/apple_computer/spec-schema")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["lockingAttrs"], ["chip_family", "memory_gb"])
        schema_mock.assert_called_once_with(category_code="apple_computer")


if __name__ == "__main__":
    unittest.main()
