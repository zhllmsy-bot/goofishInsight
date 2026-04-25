from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

import typer
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from goofish_insight.application.services import review_apply, review_batches, review_ingest, review_queries
from goofish_insight.entrypoints.cli.review import apply_second_pass_local_ai_defaults, register_review_commands
from goofish_insight.item_llm_review import __all__ as review_facade_exports
from goofish_insight import item_llm_review
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


class _DummyTemplates:
    def TemplateResponse(self, *args: object) -> HTMLResponse:
        if len(args) == 3:
            _, template_name, context = args
        elif len(args) == 2:
            template_name, context = args
        else:
            raise AssertionError(f"Unexpected TemplateResponse args: {args!r}")

        assert isinstance(template_name, str)
        assert isinstance(context, dict)
        body = json.dumps(
            {
                "template": template_name,
                "page_title": context["page_title"],
            },
            ensure_ascii=False,
        )
        return HTMLResponse(body)


class ReviewEntrypointTests(unittest.TestCase):
    def test_second_pass_defaults_do_not_override_configured_remote_ai(self) -> None:
        sentinel = "https://ark.cn-beijing.volces.com/api/v3"
        with (
            patch.dict(os.environ, {}, clear=True),
            patch(
                "goofish_insight.entrypoints.cli.review.get_settings",
                return_value=type(
                    "ConfiguredSettings",
                    (),
                    {
                        "ai_provider": "ark_responses",
                        "ai_base_url": sentinel,
                        "ai_api_key": "test-ark-key",
                        "ai_model": "doubao-seed-1-6-251015",
                    },
                )(),
            ),
        ):
            changed = apply_second_pass_local_ai_defaults()
            self.assertNotIn("AI_BASE_URL", os.environ)

        self.assertFalse(changed)

    def test_item_llm_review_facade_reexports_split_services(self) -> None:
        self.assertIn("review_item_batch", review_facade_exports)
        self.assertIs(item_llm_review.review_item_batch, review_batches.review_item_batch)
        self.assertIs(item_llm_review.apply_review_file, review_apply.apply_review_file)
        self.assertIs(
            item_llm_review.contains_suspicious_listing_keyword,
            review_ingest.contains_suspicious_listing_keyword,
        )
        self.assertIs(item_llm_review.load_items_for_llm_review, review_queries.load_items_for_llm_review)

    def test_review_items_llm_command_serializes_entries(self) -> None:
        app = typer.Typer()
        register_review_commands(app)
        runner = CliRunner()
        items = [
            {
                "item_id": "abc",
                "business_domain": "garmin",
                "title": "Fenix 8",
                "source_keyword": "fenix 8",
                "current_price": 5880,
                "condition_tags": [],
                "region": None,
                "current_values": {},
                "rule_candidate": {},
            }
        ]

        async def fake_run_llm_item_review_batches(*, items: list[dict[str, object]], batch_size: int, concurrency: int):
            self.assertEqual(batch_size, 1)
            self.assertEqual(concurrency, 1)
            self.assertEqual(len(items), 1)
            return [
                review_batches.BatchReviewResult(
                    batch_size=1,
                    review_count=1,
                    entries=[
                        {
                            "item_id": "abc",
                            "review_status": "valid",
                            "invalid_reason": None,
                            "not_match_field": [
                                {"field_key": "spec.display_type", "true_value": "AMOLED"},
                            ],
                        }
                    ],
                    llm_request_count=1,
                    llm_usage={
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "total_tokens": 120,
                        "cached_tokens": 0,
                    },
                    garbage_hit_count=0,
                    low_confidence_filtered_count=2,
                    high_confidence_kept_count=1,
                )
            ]

        with (
            patch("goofish_insight.entrypoints.cli.review.llm_is_configured", return_value=True),
            patch("goofish_insight.application.services.review_output_artifacts.load_items_for_llm_review", return_value=items),
            patch(
                "goofish_insight.entrypoints.cli.review.run_llm_item_review_batches",
                side_effect=fake_run_llm_item_review_batches,
            ),
        ):
            result = runner.invoke(
                app,
                ["review-items-llm", "--limit", "1", "--batch-size", "1", "--concurrency", "1"],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["item_id"], "abc")
        self.assertEqual(payload[0]["not_match_field"][0]["true_value"], "AMOLED")
        progress = json.loads(result.stderr.strip())
        self.assertEqual(progress["event"], "review_chunk_completed")
        self.assertEqual(progress["entries_kept_total"], 1)
        self.assertEqual(progress["chunk_low_confidence_filtered_count"], 2)
        self.assertEqual(progress["high_confidence_kept_count_total"], 1)

    def test_review_items_llm_large_backlog_loads_details_in_chunks(self) -> None:
        app = typer.Typer()
        register_review_commands(app)
        runner = CliRunner()
        seen_item_id_chunks: list[list[str]] = []

        def fake_load_items_for_llm_review(
            *,
            business_domain: str | None,
            item_id: str | None,
            item_ids: list[str] | None = None,
            limit: int,
            force: bool,
        ) -> list[dict[str, object]]:
            self.assertIsNone(business_domain)
            self.assertIsNone(item_id)
            self.assertFalse(force)
            self.assertEqual(limit, 0)
            assert item_ids is not None
            seen_item_id_chunks.append(list(item_ids))
            return [
                {
                    "item_id": current_id,
                    "business_domain": "garmin_watch",
                    "title": f"title-{current_id}",
                    "source_keyword": "fenix",
                    "current_price": 5880,
                    "condition_tags": [],
                    "region": None,
                    "current_values": {},
                    "rule_candidate": {},
                }
                for current_id in item_ids
            ]

        async def fake_run_llm_item_review_batches(*, items: list[dict[str, object]], batch_size: int, concurrency: int):
            return [
                review_batches.BatchReviewResult(
                    batch_size=len(items),
                    review_count=len(items),
                    entries=[
                        {
                            "item_id": entry["item_id"],
                            "review_status": "valid",
                            "invalid_reason": None,
                            "not_match_field": [],
                        }
                        for entry in items
                    ],
                    llm_request_count=1,
                    llm_usage={
                        "input_tokens": 50,
                        "output_tokens": 10,
                        "total_tokens": 60,
                        "cached_tokens": 0,
                    },
                    garbage_hit_count=0,
                    low_confidence_filtered_count=0,
                    high_confidence_kept_count=len(items),
                )
            ]

        with (
            patch("goofish_insight.entrypoints.cli.review.llm_is_configured", return_value=True),
            patch(
                "goofish_insight.application.services.review_output_artifacts.fetch_pending_item_ids",
                return_value=["id-1", "id-2", "id-3", "id-4", "id-5"],
            ),
            patch(
                "goofish_insight.application.services.review_output_artifacts.load_items_for_llm_review",
                side_effect=fake_load_items_for_llm_review,
            ),
            patch(
                "goofish_insight.entrypoints.cli.review.run_llm_item_review_batches",
                side_effect=fake_run_llm_item_review_batches,
            ),
        ):
            result = runner.invoke(
                app,
                ["review-items-llm", "--limit", "0", "--batch-size", "2", "--concurrency", "2"],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload), 5)
        self.assertEqual(
            seen_item_id_chunks,
            [["id-1", "id-2", "id-3", "id-4"], ["id-5"]],
        )

    def test_apply_item_llm_review_command_serializes_summary(self) -> None:
        app = typer.Typer()
        register_review_commands(app)
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.review.apply_review_file",
            return_value={"review_entry_count": 1, "matched_item_count": 1},
        ) as apply_mock:
            result = runner.invoke(
                app,
                ["apply-item-llm-review", "dummy.json", "--dry-run"],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["matched_item_count"], 1)
        apply_mock.assert_called_once()

    def test_review_v3_revalidate_second_pass_command_serializes_summary(self) -> None:
        app = typer.Typer()
        register_review_commands(app)
        runner = CliRunner()

        with patch(
            "goofish_insight.entrypoints.cli.review.revalidate_review_v3_second_pass",
            return_value=[
                {
                    "item_id": "apple-1",
                    "business_domain": "apple_computer",
                    "old_status": "VALID_READY_FOR_PRICING",
                    "new_status": "MANUAL_AUDIT_REQUIRED",
                    "changed": True,
                }
            ],
        ) as revalidate_mock:
            result = runner.invoke(
                app,
                [
                    "review-v3-revalidate-second-pass",
                    "--business-domain",
                    "apple_computer",
                    "--limit",
                    "5",
                    "--apply",
                ],
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload[0]["new_status"], "MANUAL_AUDIT_REQUIRED")
        revalidate_mock.assert_called_once_with(
            business_domain="apple_computer",
            item_id=None,
            limit=5,
            dry_run=False,
        )

    def test_web_routes_split_react_shell_from_legacy_templates(self) -> None:
        app = create_app()
        app.state.templates = _DummyTemplates()
        client = TestClient(app)

        with (
            patch(
                "goofish_insight.entrypoints.web.routers.progress.SessionLocal",
                return_value=_DummySession(),
            ),
            patch(
                "goofish_insight.entrypoints.web.routers.dashboard.build_item_detail",
                return_value={"item": {"title": "Fenix 8"}},
            ),
        ):
            dashboard_response = client.get("/")
            llm_ops_response = client.get("/llm-devops")
            runtime_response = client.get("/runtime")
            agent_response = client.get("/agent-harness")
            item_response = client.get("/items/abc")
            progress_response = client.get("/progress")
            favicon_response = client.get("/favicon.svg")
            health_response = client.get("/healthz")

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn('id="root"', dashboard_response.text)
        self.assertEqual(llm_ops_response.status_code, 200)
        self.assertIn('id="root"', llm_ops_response.text)
        self.assertEqual(runtime_response.status_code, 200)
        self.assertIn('id="root"', runtime_response.text)
        self.assertEqual(agent_response.status_code, 200)
        self.assertIn('id="root"', agent_response.text)
        self.assertEqual(item_response.status_code, 200)
        self.assertIn('id="root"', item_response.text)
        self.assertEqual(progress_response.status_code, 200)
        self.assertIn('id="root"', progress_response.text)
        self.assertEqual(favicon_response.status_code, 200)
        self.assertEqual(health_response.status_code, 200)
        self.assertEqual(health_response.json(), {"ok": True})

    def test_item_detail_api_serializes_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.dashboard.build_item_detail",
            return_value={
                "item": {
                    "item_id": "abc",
                    "title": "Fenix 8",
                },
                "spec": None,
                "seller": {},
                "snapshots": [],
                "raw_response_body": None,
            },
        ):
            response = client.get("/api/dashboard/items/abc")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["item"]["item_id"], "abc")

    def test_dashboard_runtime_status_route_serializes_runtime_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.dashboard.build_runtime_control_panel_data",
            return_value={"updatedAt": "2026-04-05T05:50:37+00:00", "groups": [{"key": "home_feed"}]},
        ) as runtime_mock:
            response = client.get("/api/dashboard/runtime/status?category_code=apple_computer")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["groups"][0]["key"], "home_feed")
        runtime_mock.assert_called_once_with(category_code="apple_computer")

    def test_dashboard_agent_harness_status_route_serializes_payload(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.agent_harness.build_agent_harness_snapshot",
            return_value={
                "updatedAt": "2026-04-17T08:00:00+00:00",
                "leadRun": {"id": "lead-run-1"},
                "metrics": {"taskCount": 2},
                "tasks": [{"key": "baseline-primary-key"}],
                "events": [{"id": "evt-1"}],
                "middlewareStack": [{"name": "SummarizationMiddleware"}],
                "nextActions": ["wire real executor"],
                "workspace": {"name": "goofish-insight"},
            },
        ):
            response = client.get("/api/dashboard/agent-harness/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["leadRun"]["id"], "lead-run-1")
        self.assertEqual(response.json()["tasks"][0]["key"], "baseline-primary-key")

    def test_dashboard_llm_traces_routes_serialize_payload(self) -> None:
        client = TestClient(create_app())

        with (
            patch(
                "goofish_insight.entrypoints.web.routers.dashboard.build_dashboard_llm_traces_section_data",
                return_value={"trace_enabled": True, "traces": [{"trace_key": "abc"}]},
            ),
            patch(
                "goofish_insight.entrypoints.web.routers.dashboard.load_dashboard_llm_trace_detail",
                return_value={"trace_key": "abc", "model": "doubao"},
            ),
        ):
            section_response = client.get("/api/dashboard/sections/llm-traces")
            detail_response = client.get("/api/dashboard/llm-traces/abc")

        self.assertEqual(section_response.status_code, 200)
        self.assertTrue(section_response.json()["trace_enabled"])
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["trace"]["model"], "doubao")

    def test_dashboard_runtime_action_route_returns_service_result(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.dashboard.run_runtime_action",
            return_value={
                "ok": True,
                "target": "vlm_runtime",
                "action": "start",
                "runtime": {"groups": []},
            },
        ) as action_mock:
            response = client.post(
                "/api/dashboard/runtime/actions",
                json={
                    "target": "vlm_runtime",
                    "action": "start",
                    "categoryCode": "garmin_watch",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        action_mock.assert_called_once_with(target="vlm_runtime", action="start", category_code="garmin_watch")

    def test_dashboard_runtime_action_route_accepts_template_smoke(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.dashboard.run_runtime_action",
            return_value={
                "ok": True,
                "target": "template_smoke",
                "action": "run_smoke",
                "actionResult": {"overallStatus": "pass", "checkCount": 14},
                "runtime": {"groups": []},
            },
        ) as action_mock:
            response = client.post(
                "/api/dashboard/runtime/actions",
                json={
                    "target": "template_smoke",
                    "action": "run_smoke",
                    "categoryCode": "garmin_watch",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["actionResult"]["overallStatus"], "pass")
        action_mock.assert_called_once_with(
            target="template_smoke",
            action="run_smoke",
            category_code="garmin_watch",
        )

    def test_dashboard_runtime_action_route_accepts_buy_jobs(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.dashboard.run_runtime_action",
            return_value={
                "ok": True,
                "target": "buy_jobs",
                "action": "refresh-buy-opportunities",
                "actionResult": {
                    "action": "refresh-buy-opportunities",
                    "exit_code": 0,
                    "result": {"ok": True},
                },
                "runtime": {"groups": []},
            },
        ) as action_mock:
            response = client.post(
                "/api/dashboard/runtime/actions",
                json={
                    "target": "buy_jobs",
                    "action": "refresh-buy-opportunities",
                    "categoryCode": "apple_computer",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["actionResult"]["action"], "refresh-buy-opportunities")
        action_mock.assert_called_once_with(
            target="buy_jobs",
            action="refresh-buy-opportunities",
            category_code="apple_computer",
        )


class PrimaryWorkflowContractTests(unittest.TestCase):
    def test_dashboard_to_item_detail_round_trip(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.dashboard.build_item_detail",
            return_value={"item": {"item_id": "abc", "title": "Fenix 8"}, "spec": None, "seller": {}, "snapshots": [], "raw_response_body": None},
        ):
            page_response = client.get("/items/abc?category_code=garmin_watch")
            api_response = client.get("/api/dashboard/items/abc")

        self.assertEqual(page_response.status_code, 200)
        self.assertIn('id="root"', page_response.text)
        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.json()["item"]["item_id"], "abc")

    def test_dashboard_to_buy_opportunities_round_trip(self) -> None:
        client = TestClient(create_app())

        page_response = client.get("/buy/opportunities?category_code=apple_computer")
        self.assertEqual(page_response.status_code, 200)
        self.assertIn('id="root"', page_response.text)

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.build_buy_opportunity_workbench",
            return_value={
                "categoryCode": "apple_computer",
                "summary": {"opportunityCount": 0},
                "opportunities": [],
                "baselines": [],
                "watchTargets": [],
            },
        ):
            api_response = client.get("/api/buy/opportunities?category_code=apple_computer")

        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.json()["categoryCode"], "apple_computer")

    def test_buy_feedback_write_round_trip(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.buy.SessionLocal",
            return_value=_DummySession(_DummyWritableSession()),
        ), patch(
            "goofish_insight.entrypoints.web.routers.buy.record_buy_decision_feedback_with_session",
            return_value={
                "opportunityId": "opp-1",
                "feedbackLabel": "bought",
                "feedbackType": "decision",
                "status": "BOUGHT",
                "decision": "bought",
            },
        ):
            response = client.post(
                "/api/buy/feedback",
                json={
                    "opportunityId": "opp-1",
                    "feedbackLabel": "bought",
                    "feedbackType": "decision",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["opportunityId"], "opp-1")

    def test_dashboard_to_runtime_round_trip(self) -> None:
        client = TestClient(create_app())

        page_response = client.get("/runtime")
        self.assertEqual(page_response.status_code, 200)
        self.assertIn('id="root"', page_response.text)

        with patch(
            "goofish_insight.entrypoints.web.routers.dashboard.build_runtime_control_panel_data",
            return_value={"updatedAt": "2026-04-05T05:50:37+00:00", "groups": [{"key": "home_feed"}]},
        ) as runtime_mock:
            api_response = client.get("/api/dashboard/runtime/status?category_code=garmin_watch")

        self.assertEqual(api_response.status_code, 200)
        self.assertEqual(api_response.json()["groups"][0]["key"], "home_feed")
        runtime_mock.assert_called_once_with(category_code="garmin_watch")

    def test_dashboard_to_onboarding_round_trip(self) -> None:
        client = TestClient(create_app())

        page_response = client.get("/onboarding/xianyu")
        self.assertEqual(page_response.status_code, 200)
        self.assertIn('id="root"', page_response.text)

        with patch(
            "goofish_insight.entrypoints.web.routers.onboarding.build_xianyu_raw_category_coverage_report",
            return_value={"counts": {"totalItems": 5}, "coverage": {}, "filters": {}},
        ):
            coverage_response = client.get("/api/onboarding/xianyu/coverage")

        self.assertEqual(coverage_response.status_code, 200)
        self.assertEqual(coverage_response.json()["counts"]["totalItems"], 5)

    def test_dashboard_sections_accept_category_code_filter(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.dashboard.SessionLocal",
            return_value=_DummySession(),
        ), patch(
            "goofish_insight.entrypoints.web.routers.dashboard.build_dashboard_hero_section_data",
            return_value={"categoryCode": "garmin_watch", "label": "Garmin 手表"},
        ) as hero_mock:
            response = client.get("/api/dashboard/sections/hero?category_code=garmin_watch")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["categoryCode"], "garmin_watch")
        hero_mock.assert_called_once()

    def test_listing_preference_round_trip(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.dashboard.SessionLocal",
            return_value=_DummySession(_DummyWritableSession()),
        ), patch(
            "goofish_insight.entrypoints.web.routers.dashboard.upsert_user_listing_preference",
            return_value={"item_id": "abc", "preference": "interested"},
        ):
            response = client.post(
                "/api/dashboard/listing-preferences",
                json={"item_id": "abc", "preference": "interested"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["preference"]["item_id"], "abc")


if __name__ == "__main__":
    unittest.main()
