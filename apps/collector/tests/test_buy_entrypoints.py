from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from goofish_analyzer.services.buy_feedback import BuyFeedbackError

from goofish_insight.webapp import create_app


class _DummySession:
    def __init__(self, session_obj: object | None = None) -> None:
        self._session_obj = session_obj if session_obj is not None else object()

    def __enter__(self) -> object:
        return self._session_obj

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class _DummyWritableSession:
    def commit(self) -> None:
        return


class BuyEntrypointTests(unittest.TestCase):
    def test_buy_opportunities_api_returns_explanations(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.build_buy_opportunity_workbench",
            return_value={
                "categoryCode": "apple_computer",
                "summary": {
                    "opportunityCount": 1,
                    "baselineCount": 1,
                    "watchTargetCount": 1,
                    "alertHitRate": 0.0,
                    "alertCount": 0,
                    "alertHitCount": 0,
                },
                "opportunities": [
                    {
                        "id": "opp-1",
                        "title": "MacBook Pro M5 Pro 18G 512G",
                        "status": "REFERENCE_ONLY",
                        "explanation": {
                            "readinessSummary": "仅参考：缺 screen_size_in",
                            "reviewGateSummary": "review ready",
                            "specGateSummary": "规格置信度低于价格池门槛",
                            "missingRequiredFields": ["screen_size_in"],
                        },
                    }
                ],
                "baselines": [],
                "watchTargets": [],
            },
        ):
            response = client.get("/api/buy/opportunities")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["opportunities"][0]["explanation"]["readinessSummary"], "仅参考：缺 screen_size_in")

    def test_buy_opportunities_page_serves_react_shell(self) -> None:
        client = TestClient(create_app())

        response = client.get("/buy/opportunities?category_code=apple_computer")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="root"', response.text)
        self.assertIn('/assets/', response.text)

    def test_buy_opportunity_detail_page_serves_react_shell(self) -> None:
        client = TestClient(create_app())

        response = client.get("/buy/opportunities/opp-1?category_code=apple_computer")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="root"', response.text)
        self.assertIn('/assets/', response.text)

    def test_buy_targets_page_serves_react_shell(self) -> None:
        client = TestClient(create_app())

        response = client.get("/buy/targets?category_code=apple_computer")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="root"', response.text)
        self.assertIn('/assets/', response.text)

    def test_buy_baselines_page_serves_react_shell(self) -> None:
        client = TestClient(create_app())

        response = client.get("/buy/baselines?category_code=apple_computer")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="root"', response.text)
        self.assertIn('/assets/', response.text)

    def test_buy_targets_api_returns_targets(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.build_buy_watch_targets_with_session",
            return_value={
                "categoryCode": "apple_computer",
                "summary": {
                    "watchTargetCount": 2,
                    "activeWatchTargetCount": 1,
                },
                "watchTargets": [
                    {
                        "id": "target-1",
                        "targetName": "apple_computer:default",
                        "profileKey": "default",
                        "status": "ACTIVE",
                    }
                ],
            },
        ):
            response = client.get("/api/buy/targets?category_code=apple_computer&status=ACTIVE")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["watchTargetCount"], 2)
        self.assertEqual(payload["watchTargets"][0]["targetName"], "apple_computer:default")

    def test_buy_data_value_api_returns_product_utilization_report(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.build_buy_data_value_report_with_session",
            return_value={
                "categoryCode": "apple_computer",
                "summary": {
                    "itemCount": 46081,
                    "opportunityCount": 4938,
                    "feedbackCount": 0,
                    "dataValueScore": 17.8,
                },
                "diagnosis": {
                    "stage": "value_unproven",
                    "statusLabel": "资源消耗态",
                },
                "stages": [],
                "categoryBreakdown": [],
                "recommendations": [],
            },
        ) as report_mock:
            response = client.get("/api/buy/data-value?category_code=apple_computer")

        self.assertEqual(response.status_code, 200)
        report_mock.assert_called_once()
        self.assertEqual(report_mock.call_args.kwargs["category_code"], "apple_computer")
        payload = response.json()
        self.assertEqual(payload["summary"]["itemCount"], 46081)
        self.assertEqual(payload["diagnosis"]["statusLabel"], "资源消耗态")

    def test_buy_baselines_api_returns_baselines(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.build_buy_price_baselines_with_session",
            return_value={
                "categoryCode": "apple_computer",
                "summary": {
                    "baselineCount": 1,
                    "baselineDateFrom": "2026-04-18",
                    "baselineDateTo": "2026-04-18",
                },
                "baselines": [
                    {
                        "id": "baseline-1",
                        "baselineKey": "template:apple",
                        "sampleSize": 12,
                        "fairPrice": 7600,
                        "buyCeiling": 7200,
                        "confidence": 0.86,
                        "baselineDate": "2026-04-18",
                    }
                ],
            },
        ):
            response = client.get("/api/buy/baselines?category_code=apple_computer&baseline_date=2026-04-18")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["baselineCount"], 1)
        self.assertEqual(payload["baselines"][0]["baselineKey"], "template:apple")

    def test_buy_opportunity_detail_api_returns_evidence_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.build_buy_opportunity_detail_with_session",
            return_value={
                "categoryCode": "apple_computer",
                "opportunity": {
                    "id": "opp-1",
                    "title": "MacBook Pro M5 Pro 16G 512G",
                    "itemId": "xy-101",
                },
                "baseline": {
                    "baselineKey": "apple:m5:16:512",
                },
                "watchTarget": {
                    "targetName": "apple_computer:default",
                },
                "risks": [
                    {
                        "riskCode": "LOW_SAMPLE_SIZE",
                    }
                ],
                "alertEvents": [],
                "feedbackEntries": [],
            },
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.build_item_detail",
            return_value={
                "item": {
                    "item_id": "xy-101",
                    "title": "MacBook Pro M5 Pro 16G 512G",
                }
            },
        ) as item_detail_mock:
            response = client.get("/api/buy/opportunities/opp-1?category_code=apple_computer")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["opportunity"]["id"], "opp-1")
        self.assertEqual(payload["watchTarget"]["targetName"], "apple_computer:default")
        self.assertEqual(payload["itemDetail"]["item"]["item_id"], "xy-101")
        item_detail_mock.assert_called_once_with(unittest.mock.ANY, "xy-101")

    def test_buy_opportunity_detail_api_returns_404_when_missing(self) -> None:
        client = TestClient(create_app(), raise_server_exceptions=False)

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.build_buy_opportunity_detail_with_session",
            return_value=None,
        ):
            response = client.get("/api/buy/opportunities/opp-missing")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Opportunity not found: opp-missing")

    def test_buy_feedback_quality_api_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.summarize_buy_feedback_quality_with_session",
            return_value={
                "categoryCode": "apple_computer",
                "windowDays": 30,
                "opportunityCount": 12,
                "feedbackCount": 8,
                "acceptCount": 3,
                "rejectCount": 4,
                "tierStats": {
                    "guidance_ready": {
                        "opportunityCount": 5,
                        "feedbackCount": 4,
                        "acceptCount": 2,
                        "rejectCount": 1,
                        "neutralCount": 1,
                        "decisionCount": 3,
                        "acceptanceRate": 0.6667,
                        "feedbackCoverageRate": 0.8,
                    }
                },
            },
        ):
            response = client.get("/api/buy/feedback-quality?category_code=apple_computer&window_days=30")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["categoryCode"], "apple_computer")
        self.assertEqual(payload["feedbackCount"], 8)
        self.assertIn("guidance_ready", payload["tierStats"])

    def test_buy_feedback_calibration_api_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.summarize_buy_feedback_calibration_with_session",
            return_value={
                "categoryCode": "apple_computer",
                "windowDays": 30,
                "recommendations": {
                    "templateFieldRecommendations": [
                        {"id": "template_key_coverage", "title": "补齐模板键覆盖"}
                    ],
                    "thresholdRecommendations": [],
                    "rankingRecommendations": [],
                    "totalRecommendationCount": 1,
                },
            },
        ):
            response = client.get("/api/buy/feedback-calibration?category_code=apple_computer&window_days=30")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["categoryCode"], "apple_computer")
        self.assertEqual(payload["recommendations"]["totalRecommendationCount"], 1)

    def test_buy_feedback_calibration_apply_api_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(_DummyWritableSession()),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.apply_buy_feedback_calibration_with_session",
            return_value={
                "categoryCode": "apple_computer",
                "windowDays": 30,
                "appliedRecommendationCount": 2,
                "skippedRecommendationCount": 1,
                "baselineRebuild": {"baselineCount": 12},
                "opportunityRefresh": {"opportunityCount": 5},
            },
        ) as apply_mock:
            response = client.post(
                "/api/buy/feedback-calibration/apply",
                json={
                    "categoryCode": "apple_computer",
                    "windowDays": 30,
                },
            )

        self.assertEqual(response.status_code, 200)
        apply_mock.assert_called_once()
        self.assertEqual(apply_mock.call_args.kwargs["category_code"], "apple_computer")
        payload = response.json()
        self.assertEqual(payload["appliedRecommendationCount"], 2)
        self.assertEqual(payload["baselineRebuild"]["baselineCount"], 12)

    def test_buy_template_monitoring_api_returns_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.summarize_template_availability_monitoring_with_session",
            return_value={
                "categoryCode": "apple_computer",
                "windowDays": 30,
                "featureFlags": {"priceTemplateContractEnabled": True},
                "baseline": {"count": 12, "tierCounts": {"guidance_ready": 8, "reference_only": 4}},
                "opportunity": {"count": 34, "tierCounts": {"guidance_ready": 10, "reference_only": 24}},
            },
        ):
            response = client.get("/api/buy/template-monitoring?category_code=apple_computer&window_days=30")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["categoryCode"], "apple_computer")
        self.assertEqual(payload["baseline"]["count"], 12)

    def test_buy_feedback_api_passes_linkage_flag(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(_DummyWritableSession()),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.record_buy_decision_feedback_with_session",
            return_value={
                "dryRun": False,
                "opportunity": {"id": "opp-1", "status": "CONTACTED", "decision": "contacted"},
                "alertCandidateLinkage": {"status": "created"},
            },
        ) as feedback_mock:
            response = client.post(
                "/api/buy/feedback",
                json={
                    "opportunityId": "opp-1",
                    "feedbackLabel": "contacted",
                    "feedbackType": "decision",
                    "linkToAlertCandidate": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        feedback_mock.assert_called_once()
        self.assertTrue(feedback_mock.call_args.kwargs["link_to_alert_candidate"])
        payload = response.json()
        self.assertEqual(payload["alertCandidateLinkage"]["status"], "created")

    def test_buy_feedback_api_returns_404_for_missing_opportunity(self) -> None:
        client = TestClient(create_app(), raise_server_exceptions=False)

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(_DummyWritableSession()),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.record_buy_decision_feedback_with_session",
            side_effect=BuyFeedbackError("Opportunity not found: opp-missing"),
        ):
            response = client.post(
                "/api/buy/feedback",
                json={
                    "opportunityId": "opp-missing",
                    "feedbackLabel": "contacted",
                    "feedbackType": "decision",
                },
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Opportunity not found: opp-missing")

    def test_buy_feedback_api_returns_400_for_invalid_decimal(self) -> None:
        client = TestClient(create_app(), raise_server_exceptions=False)

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(_DummyWritableSession()),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.record_buy_decision_feedback_with_session",
            side_effect=BuyFeedbackError("Invalid decimal value: not-a-number"),
        ):
            response = client.post(
                "/api/buy/feedback",
                json={
                    "opportunityId": "opp-1",
                    "feedbackLabel": "purchased",
                    "feedbackType": "decision",
                    "purchasePrice": "not-a-number",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Invalid decimal value: not-a-number")


if __name__ == "__main__":
    unittest.main()
