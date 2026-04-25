from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from goofish_insight.webapp import create_app


class TaskConfigEntrypointTests(unittest.TestCase):
    def test_task_config_page_renders_react_shell(self) -> None:
        client = TestClient(create_app())

        response = client.get("/config/tasks")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="root"', response.text)

    def test_task_config_list_route_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.list_task_configs",
            return_value={"total": 1, "items": [{"taskKey": "apple-core"}]},
        ) as list_mock:
            response = client.get("/api/config/tasks?status=active&category_code=apple_computer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["taskKey"], "apple-core")
        list_mock.assert_called_once_with(status="active", category_code="apple_computer")

    def test_task_config_upsert_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.upsert_task_config",
            return_value={"task": {"taskKey": "apple-core", "displayName": "Apple Core"}},
        ) as upsert_mock:
            response = client.post(
                "/api/config/tasks",
                json={
                    "operatorId": "ops-bot",
                    "apply": True,
                    "payload": {
                        "taskKey": "apple-core",
                        "displayName": "Apple Core",
                        "categoryCode": "apple_computer",
                        "queries": [{"query": "macbook pro"}],
                        "lexicons": {"BRAND": [{"term": "apple"}]},
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task"]["taskKey"], "apple-core")
        upsert_mock.assert_called_once_with(
            payload={
                "taskKey": "apple-core",
                "displayName": "Apple Core",
                "categoryCode": "apple_computer",
                "queries": [{"query": "macbook pro"}],
                "lexicons": {"BRAND": [{"term": "apple"}]},
            },
            operator_id="ops-bot",
            dry_run=False,
        )


if __name__ == "__main__":
    unittest.main()
