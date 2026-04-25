from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from goofish_insight.webapp import create_app


class OnboardingEntrypointTests(unittest.TestCase):
    def test_onboarding_page_route_returns_react_shell(self) -> None:
        client = TestClient(create_app())

        response = client.get("/onboarding/xianyu")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="root"', response.text)

    def test_onboarding_coverage_route_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.build_xianyu_raw_category_coverage_report",
            return_value={"counts": {"totalItems": 12}},
        ) as coverage_mock:
            response = client.get("/api/onboarding/xianyu/coverage?source_keyword=macbookpro14")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["counts"]["totalItems"], 12)
        coverage_mock.assert_called_once_with(
            source_keyword="macbookpro14",
            task_id=None,
            business_domain=None,
            unmapped_limit=20,
            item_scan_limit=2000,
        )

    def test_onboarding_queue_route_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.list_xianyu_category_onboarding_queue",
            return_value={"total": 1, "items": [{"matchKey": "C_CAT:126854525"}]},
        ) as queue_mock:
            response = client.get("/api/onboarding/xianyu/queue?status=PENDING&limit=20")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        queue_mock.assert_called_once_with(status="PENDING", include_closed=False, limit=20)

    def test_onboarding_queue_sync_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.sync_xianyu_category_onboarding_queue",
            return_value={"createdCount": 2, "resolvedCount": 1},
        ) as sync_mock:
            response = client.post(
                "/api/onboarding/xianyu/queue/sync",
                json={
                    "operatorId": "ops-bot",
                    "sourceKeyword": "macbookpro14",
                    "itemScanLimit": 500,
                    "apply": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["createdCount"], 2)
        sync_mock.assert_called_once_with(
            operator_id="ops-bot",
            source_keyword="macbookpro14",
            task_id=None,
            business_domain=None,
            item_scan_limit=500,
            dry_run=False,
        )

    def test_onboarding_queue_status_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.update_xianyu_category_onboarding_queue_status",
            return_value={"queue": {"id": "queue-1", "status": "IN_PROGRESS"}},
        ) as status_mock:
            response = client.post(
                "/api/onboarding/xianyu/queue/status",
                json={
                    "operatorId": "ops-bot",
                    "status": "IN_PROGRESS",
                    "queueId": "queue-1",
                    "ownerOperatorId": "alice",
                    "statusNote": "picked up",
                    "apply": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["queue"]["status"], "IN_PROGRESS")
        status_mock.assert_called_once_with(
            operator_id="ops-bot",
            status="IN_PROGRESS",
            queue_id="queue-1",
            match_key=None,
            owner_operator_id="alice",
            status_note="picked up",
            dry_run=False,
        )

    def test_onboarding_discovery_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.run_xianyu_onboarding_discovery",
            return_value={
                "sourceKeyword": "macbookpro14",
                "executionMode": "persistent_context",
                "run": {"runId": "run-1", "pagesSucceeded": 1, "pagesAttempted": 1},
            },
        ) as discovery_mock:
            response = client.post(
                "/api/onboarding/xianyu/discovery",
                json={
                    "sourceKeyword": "macbookpro14",
                    "taskKey": "apple-monitor",
                    "businessDomain": "apple_m_series",
                    "pages": 2,
                    "profileKey": "default",
                    "loginWaitSeconds": 240,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["run"]["runId"], "run-1")
        discovery_mock.assert_called_once_with(
            source_keyword="macbookpro14",
            task_key="apple-monitor",
            business_domain="apple_m_series",
            pages=2,
            profile_key="default",
            login_wait_seconds=240,
        )

    def test_onboarding_draft_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.build_xianyu_category_onboarding_draft",
            return_value={
                "selection": {"xianyuCatId": "50025387", "xianyuTbCatId": "50014945"},
                "analysis": {"sampleCount": 3},
                "payload": {"catalog": {"attributes": []}, "mappings": []},
            },
        ) as draft_mock:
            response = client.post(
                "/api/onboarding/xianyu/draft",
                json={
                    "sourceKeyword": "macbookpro14",
                    "businessDomain": "apple_m_series",
                    "xianyuCatId": "50025387",
                    "xianyuTbCatId": "50014945",
                    "xianyuCCatId": "126854525",
                    "sampleLimit": 12,
                    "preferUnmapped": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["analysis"]["sampleCount"], 3)
        draft_mock.assert_called_once_with(
            source_keyword="macbookpro14",
            task_id=None,
            business_domain="apple_m_series",
            xianyu_cat_id="50025387",
            xianyu_tb_cat_id="50014945",
            xianyu_c_cat_id="126854525",
            sample_limit=12,
            prefer_unmapped=False,
        )

    def test_onboarding_persist_route_invokes_service(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.persist_xianyu_category_onboarding",
            return_value={
                "dryRun": False,
                "categoryId": "cat-apple",
                "templateId": "tpl-apple",
                "mappingCount": 1,
            },
        ) as persist_mock:
            response = client.post(
                "/api/onboarding/xianyu/persist",
                json={
                    "operatorId": "ops-bot",
                    "apply": True,
                    "payload": {
                        "requestId": "req-1",
                        "catalog": {
                            "category": {
                                "code": "apple_m_series",
                                "name": "Apple M Series",
                                "path": "电脑/Apple",
                                "level": 2,
                            },
                            "attributes": [],
                            "template": {"version": 1, "items": []},
                        },
                        "mappings": [{"matchScope": "CAT_TB", "xianyuCatId": "50025387", "xianyuTbCatId": "50014945"}],
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["templateId"], "tpl-apple")
        persist_mock.assert_called_once_with(
            payload={
                "requestId": "req-1",
                "catalog": {
                    "category": {
                        "code": "apple_m_series",
                        "name": "Apple M Series",
                        "path": "电脑/Apple",
                        "level": 2,
                    },
                    "attributes": [],
                    "template": {"version": 1, "items": []},
                },
                "mappings": [{"matchScope": "CAT_TB", "xianyuCatId": "50025387", "xianyuTbCatId": "50014945"}],
            },
            operator_id="ops-bot",
            dry_run=False,
        )


class OnboardingWorkflowContractTests(unittest.TestCase):
    def test_onboarding_queue_to_status_to_draft_to_persist_flow(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.list_xianyu_category_onboarding_queue",
            return_value={"total": 1, "items": [{"matchKey": "C_CAT:126854525", "status": "PENDING"}]},
        ):
            queue_response = client.get("/api/onboarding/xianyu/queue?status=PENDING")

        self.assertEqual(queue_response.status_code, 200)
        self.assertEqual(queue_response.json()["total"], 1)
        self.assertEqual(queue_response.json()["items"][0]["status"], "PENDING")

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.update_xianyu_category_onboarding_queue_status",
            return_value={"queue": {"id": "queue-1", "status": "IN_PROGRESS"}},
        ):
            status_response = client.post(
                "/api/onboarding/xianyu/queue/status",
                json={"operatorId": "ops-bot", "status": "IN_PROGRESS", "queueId": "queue-1", "apply": True},
            )

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["queue"]["status"], "IN_PROGRESS")

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.build_xianyu_category_onboarding_draft",
            return_value={
                "selection": {"xianyuCatId": "50025387"},
                "analysis": {"sampleCount": 3},
                "payload": {"catalog": {"attributes": []}, "mappings": []},
            },
        ):
            draft_response = client.post(
                "/api/onboarding/xianyu/draft",
                json={"sourceKeyword": "fenix8", "businessDomain": "garmin_watch", "xianyuCCatId": "126854525"},
            )

        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_response.json()["analysis"]["sampleCount"], 3)

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.persist_xianyu_category_onboarding",
            return_value={"dryRun": False, "categoryId": "cat-garmin", "templateId": "tpl-garmin", "mappingCount": 1},
        ):
            persist_response = client.post(
                "/api/onboarding/xianyu/persist",
                json={
                    "operatorId": "ops-bot",
                    "apply": True,
                    "payload": {
                        "catalog": {"category": {"code": "garmin_watch"}, "attributes": [], "template": {"version": 1, "items": []}},
                        "mappings": [{"matchScope": "C_CAT", "xianyuCCatId": "126854525"}],
                    },
                },
            )

        self.assertEqual(persist_response.status_code, 200)
        self.assertEqual(persist_response.json()["categoryId"], "cat-garmin")

    def test_onboarding_coverage_accepts_business_domain_filter(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.build_xianyu_raw_category_coverage_report",
            return_value={"counts": {"totalItems": 8}, "coverage": {}, "filters": {}},
        ) as coverage_mock:
            response = client.get("/api/onboarding/xianyu/coverage?business_domain=garmin_watch")

        self.assertEqual(response.status_code, 200)
        coverage_mock.assert_called_once_with(
            source_keyword=None,
            task_id=None,
            business_domain="garmin_watch",
            unmapped_limit=20,
            item_scan_limit=2000,
        )

    def test_onboarding_queue_sync_dry_run_default(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.sync_xianyu_category_onboarding_queue",
            return_value={"createdCount": 0, "resolvedCount": 0},
        ) as sync_mock:
            response = client.post(
                "/api/onboarding/xianyu/queue/sync",
                json={"operatorId": "ops-bot", "sourceKeyword": "fenix8"},
            )

        self.assertEqual(response.status_code, 200)
        sync_mock.assert_called_once_with(
            operator_id="ops-bot",
            source_keyword="fenix8",
            task_id=None,
            business_domain=None,
            item_scan_limit=2000,
            dry_run=True,
        )


if __name__ == "__main__":
    unittest.main()
