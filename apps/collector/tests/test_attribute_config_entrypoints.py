from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from goofish_insight.webapp import create_app


class AttributeConfigEntrypointTests(unittest.TestCase):
    def test_attribute_config_page_renders_template(self) -> None:
        client = TestClient(create_app())

        response = client.get("/config/attributes")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Attribute Dictionary Config", response.text)

    def test_attribute_config_list_route_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.list_attribute_configs",
            return_value={"total": 1, "items": [{"code": "memory_gb"}]},
        ) as list_mock:
            response = client.get("/api/config/attributes?status=ACTIVE&scope_type=PLATFORM")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["code"], "memory_gb")
        list_mock.assert_called_once_with(status="ACTIVE", scope_type="PLATFORM")

    def test_attribute_config_upsert_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.upsert_attribute_config",
            return_value={"attribute": {"code": "device_color", "name": "颜色"}},
        ) as upsert_mock:
            response = client.post(
                "/api/config/attributes",
                json={
                    "operatorId": "ops-bot",
                    "apply": True,
                    "payload": {
                        "code": "device_color",
                        "name": "颜色",
                        "scopeType": "PLATFORM",
                        "scopeId": "platform",
                        "dataType": "ENUM",
                        "valueScope": "SALE",
                        "options": [{"optionCode": "black", "optionName": "黑色"}],
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["attribute"]["code"], "device_color")
        upsert_mock.assert_called_once_with(
            payload={
                "code": "device_color",
                "name": "颜色",
                "scopeType": "PLATFORM",
                "scopeId": "platform",
                "dataType": "ENUM",
                "valueScope": "SALE",
                "options": [{"optionCode": "black", "optionName": "黑色"}],
            },
            operator_id="ops-bot",
            dry_run=False,
        )


if __name__ == "__main__":
    unittest.main()
