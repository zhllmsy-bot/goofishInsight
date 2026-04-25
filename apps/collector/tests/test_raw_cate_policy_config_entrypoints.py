from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from goofish_insight.webapp import create_app


class RawCatePolicyConfigEntrypointTests(unittest.TestCase):
    def test_config_raw_cate_policy_page_renders_template(self) -> None:
        client = TestClient(create_app())

        response = client.get("/config/raw-cate-policy")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Xianyu Raw Category Governance", response.text)

    def test_config_raw_cate_policy_list_route_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.list_raw_cate_policy_configs",
            return_value={"total": 1, "items": [{"matchKey": "C_CAT:126864783"}]},
        ) as list_mock:
            response = client.get("/api/config/raw-cate-policy?status=ACTIVE&policy_mode=FORCE_TEMPLATE")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["matchKey"], "C_CAT:126864783")
        list_mock.assert_called_once_with(status="ACTIVE", policy_mode="FORCE_TEMPLATE")

    def test_config_raw_cate_policy_upsert_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.config.upsert_raw_cate_policy_config",
            return_value={"policy": {"matchKey": "C_CAT:126864783", "policyMode": "BLOCK"}},
        ) as upsert_mock:
            response = client.post(
                "/api/config/raw-cate-policy",
                json={
                    "operatorId": "ops-bot",
                    "apply": True,
                    "payload": {
                        "matchScope": "C_CAT",
                        "xianyuCCatId": "126864783",
                        "policyMode": "BLOCK",
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["policy"]["policyMode"], "BLOCK")
        upsert_mock.assert_called_once_with(
            payload={
                "matchScope": "C_CAT",
                "xianyuCCatId": "126864783",
                "policyMode": "BLOCK",
            },
            operator_id="ops-bot",
            dry_run=False,
        )


if __name__ == "__main__":
    unittest.main()
