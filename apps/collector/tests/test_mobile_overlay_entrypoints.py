from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from goofish_insight.webapp import create_app


class _DummySession:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


class MobileOverlayEntrypointTests(unittest.TestCase):
    def test_analyze_overlay_route_serializes_vlm_response(self) -> None:
        client = TestClient(create_app())

        with (
            patch(
                "goofish_insight.entrypoints.web.routers.mobile_overlay.SessionLocal",
                return_value=_DummySession(),
            ),
            patch(
                "goofish_insight.entrypoints.web.routers.mobile_overlay.build_mobile_overlay_analysis",
                return_value={
                    "ok": True,
                    "ocr_summary": {"title_candidate": "Garmin Fenix 8"},
                    "vlm_summary": {"used": True, "thinking_enabled": True},
                },
            ) as analysis_mock,
        ):
            response = client.post(
                "/api/mobile-overlay/analyze",
                json={
                    "screen_width": 1080,
                    "screen_height": 2400,
                    "screenshot_base64": "data:image/png;base64,abc",
                    "ocr_lines": [{"text": "Garmin Fenix 8"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["vlm_summary"]["used"])
        analysis_mock.assert_called_once()

    def test_mobile_overlay_healthz_exposes_vlm_queue_status(self) -> None:
        client = TestClient(create_app())

        with patch(
            "goofish_insight.entrypoints.web.routers.mobile_overlay.build_overlay_vlm_runtime_status",
            return_value={
                "enabled": True,
                "base_url": "http://127.0.0.1:8020",
                "model": "Qwen2.5-VL-72B-Instruct-4bit-MLX",
                "thinking_enabled": True,
                "queue": {"pending_jobs": 2, "worker_alive": True},
            },
        ):
            response = client.get("/api/mobile-overlay/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(response.json()["vlm"]["queue"]["pending_jobs"], 2)


if __name__ == "__main__":
    unittest.main()
