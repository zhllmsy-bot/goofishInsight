from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from decimal import Decimal
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from goofish_insight.cli import (
    CATEGORY_INGEST_GATE_PROFILES,
    CapturedSearchPayload,
    ManualVerificationRequired,
    SearchPlanEntry,
    classify_category_ingest_block_reason,
    classify_title_length_ingest_block_reason,
    capture_run_progress,
    detect_page_risk_control_signal,
    extract_source_numeric_signature_tokens,
    finalize_search_capture_interruption,
    reconcile_stale_running_runs_with_session,
    run_live_search_batch,
    title_matches_source_numeric_signature,
)
from goofish_insight.application.services.collector_ingest import is_permanent_category_gate_reason


class SearchCaptureRunStateTests(TestCase):
    @patch("goofish_insight.cli.resolve_cdp_url", return_value="ws://attached-browser")
    @patch("goofish_insight.cli.execute_search_capture_on_page")
    @patch("goofish_insight.cli.sync_playwright")
    def test_run_live_search_batch_stops_and_closes_attached_tab_on_risk_control(
        self,
        sync_playwright_mock,
        execute_search_capture_on_page_mock,
        _resolve_cdp_url_mock,
    ) -> None:
        class _FakePage:
            def __init__(self) -> None:
                self.closed = False
                self.wait_calls = 0
                self.close_calls = 0

            def is_closed(self) -> bool:
                return self.closed

            def close(self) -> None:
                self.close_calls += 1
                self.closed = True

            def wait_for_timeout(self, _milliseconds: int) -> None:
                self.wait_calls += 1

        class _FakeContext:
            def __init__(self, page: _FakePage) -> None:
                self._page = page

            def new_page(self) -> _FakePage:
                return self._page

        class _FakeBrowser:
            def __init__(self, context: _FakeContext) -> None:
                self.contexts = [context]

        class _FakePlaywrightManager:
            def __init__(self, browser: _FakeBrowser) -> None:
                self.chromium = SimpleNamespace(connect_over_cdp=lambda _url: browser)

            def __enter__(self) -> SimpleNamespace:
                return self

            def __exit__(self, exc_type, exc, tb) -> bool:
                return False

        page = _FakePage()
        browser = _FakeBrowser(_FakeContext(page))
        sync_playwright_mock.return_value = _FakePlaywrightManager(browser)
        execute_search_capture_on_page_mock.side_effect = ManualVerificationRequired(
            "Risk control blocked the search.",
            auth_state="risk_control",
            keep_page_open=False,
        )
        plans = [
            SearchPlanEntry(
                task=SimpleNamespace(id=1, task_key="task-a"),
                query="fenix 8",
                pages=1,
                task_query_id=101,
            ),
            SearchPlanEntry(
                task=SimpleNamespace(id=2, task_key="task-b"),
                query="forerunner 965",
                pages=1,
                task_query_id=102,
            ),
        ]

        outcomes = run_live_search_batch(
            plans=plans,
            channel="chrome",
            headless=False,
            cdp_url="ws://attached-browser",
            parallel_tabs=1,
            profile_key="chrome-attached",
            profile_dir=Path("/tmp/chrome-attached"),
            login_wait_seconds=30,
        )

        self.assertEqual(execute_search_capture_on_page_mock.call_count, 1)
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].status, "manual_verification_required")
        self.assertEqual(outcomes[0].auth_state, "risk_control")
        self.assertEqual(page.close_calls, 1)
        self.assertEqual(page.wait_calls, 0)

    def test_reconcile_stale_running_runs_marks_only_expired_rows(self) -> None:
        now = datetime.utcnow()
        stale_run = SimpleNamespace(
            status="running",
            started_at=now - timedelta(minutes=25),
            finished_at=None,
            error_message=None,
        )
        recent_run = SimpleNamespace(
            status="running",
            started_at=now - timedelta(minutes=3),
            finished_at=None,
            error_message=None,
        )
        completed_run = SimpleNamespace(
            status="completed",
            started_at=now - timedelta(minutes=40),
            finished_at=now - timedelta(minutes=35),
            error_message=None,
        )

        class _FakeScalarResult:
            def __init__(self, items) -> None:
                self._items = items

            def scalars(self):
                return self

            def all(self):
                return list(self._items)

        class _FakeSession:
            def execute(self, _statement):
                return _FakeScalarResult([stale_run, recent_run, completed_run])

        recovered = reconcile_stale_running_runs_with_session(
            _FakeSession(),
            now=now,
            older_than=timedelta(minutes=10),
        )

        self.assertEqual(recovered, 1)
        self.assertEqual(stale_run.status, "cancelled")
        self.assertEqual(stale_run.finished_at, now)
        self.assertIn("10 minute timeout", stale_run.error_message)
        self.assertEqual(recent_run.status, "running")
        self.assertIsNone(recent_run.finished_at)
        self.assertEqual(completed_run.status, "completed")

    def test_capture_run_progress_counts_attempted_and_succeeded_pages(self) -> None:
        now = datetime.utcnow()
        captures = {
            1: CapturedSearchPayload(
                page_number=1,
                request_url="https://example.com/1",
                request_body={},
                request_headers={},
                response_status=200,
                payload={"data": {"resultList": [{"id": "a"}]}},
                captured_at=now,
            ),
            2: CapturedSearchPayload(
                page_number=2,
                request_url="https://example.com/2",
                request_body={},
                request_headers={},
                response_status=200,
                payload={"data": {"resultList": []}},
                captured_at=now,
            ),
        }

        pages_attempted, pages_succeeded = capture_run_progress(
            captures=captures,
            attempted_pages=5,
        )

        self.assertEqual(pages_attempted, 5)
        self.assertEqual(pages_succeeded, 1)

    @patch("goofish_insight.cli.upsert_browser_session_state")
    @patch("goofish_insight.cli.finalize_run")
    def test_finalize_search_capture_interruption_marks_cancelled(
        self,
        finalize_run_mock,
        upsert_browser_session_state_mock,
    ) -> None:
        now = datetime.utcnow()
        captures = {
            1: CapturedSearchPayload(
                page_number=1,
                request_url="https://example.com/1",
                request_body={},
                request_headers={},
                response_status=200,
                payload={"data": {"resultList": [{"id": "a"}]}},
                captured_at=now,
            )
        }
        run_id = uuid4()

        finalize_search_capture_interruption(
            run_id=run_id,
            captures=captures,
            attempted_pages=3,
            profile_key="chrome-attached",
            profile_dir=Path("/tmp/chrome-attached"),
            browser_channel="chrome",
            auth_state="authenticated",
            login_required_at=None,
            authenticated_at=now,
        )

        finalize_run_mock.assert_called_once_with(
            run_id=run_id,
            status="cancelled",
            pages_attempted=3,
            pages_succeeded=1,
            error_message="Interrupted by user.",
        )
        upsert_browser_session_state_mock.assert_called_once()
        self.assertEqual(
            upsert_browser_session_state_mock.call_args.kwargs["last_error"],
            "Interrupted by user.",
        )

    def test_category_gate_blocks_body_accessories_by_keyword_and_price(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="camera_body",
            title="佳能R5硅胶套 相机保护套",
            price=Decimal("41"),
            source_keyword="佳能 R5 机身",
            profile=CATEGORY_INGEST_GATE_PROFILES["camera_body"],
        )

        self.assertEqual(reason, "price_floor")

    def test_category_gate_blocks_apple_watch_in_apple_computer(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="apple_computer",
            title="Apple Watch Ultra 2 49mm 海外版",
            price=Decimal("4200"),
            source_keyword="apple watch ultra 2",
            profile=CATEGORY_INGEST_GATE_PROFILES["apple_computer"],
        )

        self.assertEqual(reason, "domain_mismatch:apple_watch_like")

    def test_category_gate_blocks_lens_listing_under_camera_body(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="camera_body",
            title="尼康 Z 50mm f/1.8 S 镜头 成色好",
            price=Decimal("2800"),
            source_keyword="尼康 Z50",
            profile=CATEGORY_INGEST_GATE_PROFILES["camera_body"],
        )

        self.assertEqual(reason, "domain_redirect:camera_interchangeable_lens")

    def test_category_gate_blocks_lens_signature_mismatch(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="camera_interchangeable_lens",
            title="尼康Z 70-200mm f/2.8 S VR 国行",
            price=Decimal("10000"),
            source_keyword="尼康 Z 24-70 2.8 S 镜头",
            profile=CATEGORY_INGEST_GATE_PROFILES["camera_interchangeable_lens"],
        )

        self.assertEqual(reason, "signature_mismatch")

    def test_category_gate_blocks_low_price_body_noise_even_without_known_keyword(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="camera_body",
            title="佳能EOS R5 相机底标贴纸",
            price=Decimal("13"),
            source_keyword="佳能 R5 机身",
            profile=CATEGORY_INGEST_GATE_PROFILES["camera_body"],
        )

        self.assertEqual(reason, "price_floor")

    def test_camera_domain_redirect_is_not_marked_as_permanent_rejection(self) -> None:
        self.assertFalse(
            is_permanent_category_gate_reason(
                category_code="camera_body",
                reason="domain_redirect:camera_interchangeable_lens",
            )
        )
        self.assertTrue(
            is_permanent_category_gate_reason(
                category_code="apple_computer",
                reason="domain_mismatch:apple_watch_like",
            )
        )

    def test_title_length_gate_blocks_overlong_keyword_spam(self) -> None:
        reason = classify_title_length_ingest_block_reason(title="车架 配件 " * 150)

        self.assertEqual(reason, "title_length_gt_500")

    def test_category_gate_blocks_low_price_garmin_watch_as_price_floor(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="garmin_watch",
            title="佳明 Garmin Instinct 2 本能 2 太阳能 功能正常",
            price=Decimal("399"),
            source_keyword="佳明 instinct 2",
            profile=CATEGORY_INGEST_GATE_PROFILES["garmin_watch"],
        )

        self.assertEqual(reason, "price_floor")

    def test_category_gate_blocks_400_price_garmin_watch_as_price_floor(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="garmin_watch",
            title="佳明 Garmin Instinct 2X 本能 2X 功能正常",
            price=Decimal("400"),
            source_keyword="佳明 instinct 2x",
            profile=CATEGORY_INGEST_GATE_PROFILES["garmin_watch"],
        )

        self.assertEqual(reason, "price_floor")

    def test_category_gate_blocks_garmin_accessory_noise(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="garmin_watch",
            title="适配佳明 Garmin 965 尼龙表带 快拆",
            price=Decimal("45"),
            source_keyword="佳明 forerunner 965",
            profile=CATEGORY_INGEST_GATE_PROFILES["garmin_watch"],
        )

        self.assertEqual(reason, "non_comparable_title")

    def test_category_gate_keeps_garmin_watch_with_normal_band_or_map_context(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="garmin_watch",
            title="佳明 Garmin Fenix 8 AMOLED 51mm 国行 带原装表带和地图",
            price=Decimal("5200"),
            source_keyword="佳明 fenix 8 51mm",
            profile=CATEGORY_INGEST_GATE_PROFILES["garmin_watch"],
        )

        self.assertIsNone(reason)

    def test_category_gate_does_not_permanently_block_exchange_keyword(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="garmin_watch",
            title="可置换 佳明 Garmin MARQ 2 Athlete 国行 钛表带 支持置换回收",
            price=Decimal("7800"),
            source_keyword="佳明 marq 2",
            profile=CATEGORY_INGEST_GATE_PROFILES["garmin_watch"],
        )

        self.assertIsNone(reason)

    def test_category_gate_blocks_garmin_watchface_service_by_phrase_combo(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="garmin_watch",
            title="Garmin fenix 8 amoled 解锁佳明表盘 可以来图定制 安装需要用电脑 售出不退不换",
            price=Decimal("10"),
            source_keyword="佳明 fenix 8",
            profile=CATEGORY_INGEST_GATE_PROFILES["garmin_watch"],
        )

        self.assertEqual(reason, "non_comparable_title")

    def test_category_gate_blocks_garmin_placeholder_low_price_listing(self) -> None:
        reason = classify_category_ingest_block_reason(
            category_code="garmin_watch",
            title="【可置换】佳明garmin marq2 Adventurer 全新腕表 官方价19800 国行正品",
            price=Decimal("1"),
            source_keyword="佳明 marq2",
            profile=CATEGORY_INGEST_GATE_PROFILES["garmin_watch"],
        )

        self.assertEqual(reason, "non_comparable_title")

    def test_source_numeric_signature_helpers_extract_and_match(self) -> None:
        self.assertEqual(
            extract_source_numeric_signature_tokens("NIKKOR Z 24-70mm f/2.8 S 镜头"),
            ["2470", "28"],
        )
        self.assertTrue(
            title_matches_source_numeric_signature(
                title="尼康 NIKKOR Z 24-70mm f/2.8 S 镜头 国行",
                source_keyword="NIKKOR Z 24-70mm f/2.8 S 镜头",
            )
        )

    def test_detect_page_risk_control_signal_hits_iframe_marker(self) -> None:
        signal = detect_page_risk_control_signal(
            frame_urls=[
                "https://g.alicdn.com/platform/xdomain-storage/0.2.4/frame.html",
                "https://h5api.m.goofish.com/h5/mtop.taobao.idlemtopsearch.pc.search/1.0/executeCaptcha?x5secdata=abc",
            ],
            page_text=None,
        )

        self.assertIsNotNone(signal)
        self.assertIn("iframe:", signal)
        self.assertIn("executeCaptcha", signal)

    def test_detect_page_risk_control_signal_hits_dom_hint(self) -> None:
        signal = detect_page_risk_control_signal(
            frame_urls=[],
            page_text="请依次连出___ 点击反馈",
        )

        self.assertEqual(signal, "dom:请依次连出")

    def test_detect_page_risk_control_signal_returns_none_for_normal_page(self) -> None:
        signal = detect_page_risk_control_signal(
            frame_urls=["https://www.goofish.com/search?q=fenix"],
            page_text="搜索结果",
        )

        self.assertIsNone(signal)
