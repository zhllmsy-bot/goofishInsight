from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from goofish_insight.webapp import create_app


class ModelConfigEntrypointTests(unittest.TestCase):
    def test_config_models_page_renders_template(self) -> None:
        client = TestClient(create_app())

        response = client.get("/config/models")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Model Catalog Config", response.text)

    def test_config_models_list_route_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.list_model_configs",
            return_value={"total": 1, "items": [{"modelCode": "nikon_z_50_f12_s"}]},
        ) as list_mock:
            response = client.get(
                "/api/config/models?status=ACTIVE&category_code=camera_interchangeable_lens&brand_name=Nikon"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["modelCode"], "nikon_z_50_f12_s")
        list_mock.assert_called_once_with(
            status="ACTIVE",
            category_code="camera_interchangeable_lens",
            brand_name="Nikon",
        )

    def test_config_models_upsert_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.upsert_model_config",
            return_value={"model": {"modelCode": "nikon_z_50_f12_s"}},
        ) as upsert_mock:
            response = client.post(
                "/api/config/models",
                json={
                    "operatorId": "ops-bot",
                    "apply": True,
                    "payload": {
                        "categoryCode": "camera_interchangeable_lens",
                        "brandName": "Nikon",
                        "modelCode": "nikon_z_50_f12_s",
                        "modelName": "NIKKOR Z 50mm f/1.2 S",
                        "aliases": [{"aliasText": "尼康 Z50 1.2S"}],
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model"]["modelCode"], "nikon_z_50_f12_s")
        upsert_mock.assert_called_once_with(
            payload={
                "categoryCode": "camera_interchangeable_lens",
                "brandName": "Nikon",
                "modelCode": "nikon_z_50_f12_s",
                "modelName": "NIKKOR Z 50mm f/1.2 S",
                "aliases": [{"aliasText": "尼康 Z50 1.2S"}],
            },
            operator_id="ops-bot",
            dry_run=False,
        )

    def test_config_models_import_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.import_model_configs",
            return_value={"importedCount": 2},
        ) as import_mock:
            response = client.post(
                "/api/config/models/import",
                json={
                    "operatorId": "ops-bot",
                    "apply": True,
                    "payload": {"items": [{"modelCode": "m1"}, {"modelCode": "m2"}]},
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["importedCount"], 2)
        import_mock.assert_called_once_with(
            payload={"items": [{"modelCode": "m1"}, {"modelCode": "m2"}]},
            operator_id="ops-bot",
            dry_run=False,
        )


if __name__ == "__main__":
    unittest.main()
