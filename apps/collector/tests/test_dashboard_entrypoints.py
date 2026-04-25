from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from goofish_insight.webapp import create_app


class _DummySession:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def commit(self) -> None:
        return None


class DashboardEntrypointTests(unittest.TestCase):
    def test_listing_preference_api_records_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.dashboard.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.dashboard.upsert_user_listing_preference",
            return_value={
                "id": "pref-1",
                "itemId": "item-1",
                "preference": "interested",
                "status": "active",
            },
        ) as upsert_mock:
            response = client.post(
                "/api/dashboard/listing-preferences",
                json={
                    "item_id": "item-1",
                    "preference": "interested",
                    "reason": "dashboard_card_interest",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["preference"]["itemId"], "item-1")
        upsert_mock.assert_called_once()
        self.assertEqual(upsert_mock.call_args.kwargs["item_id"], "item-1")
        self.assertEqual(upsert_mock.call_args.kwargs["preference"], "interested")


if __name__ == "__main__":
    unittest.main()
