from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from goofish_insight.webapp import create_app


class WebappCorsTests(unittest.TestCase):
    def test_react_dev_origin_is_allowed_for_dashboard_api(self) -> None:
        client = TestClient(create_app())

        response = client.options(
            "/api/dashboard/runtime/status",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://127.0.0.1:5173")

    def test_vite_default_port_is_allowed_for_dashboard_api(self) -> None:
        client = TestClient(create_app())

        response = client.options(
            "/api/dashboard/runtime/status",
            headers={
                "Origin": "http://127.0.0.1:5174",
                "Access-Control-Request-Method": "GET",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("access-control-allow-origin"), "http://127.0.0.1:5174")
