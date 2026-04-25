from __future__ import annotations

import unittest
from unittest.mock import patch

from goofish_insight.cli import resolve_cdp_url


class CdpDiscoveryTests(unittest.TestCase):
    def test_resolve_cdp_url_falls_back_to_default_local_port(self) -> None:
        with (
            patch("goofish_insight.cli.discover_attached_browsers", return_value=[]),
            patch(
                "goofish_insight.cli.fetch_cdp_tabs",
                side_effect=lambda cdp_url: [{"id": "tab-1"}] if cdp_url == "http://127.0.0.1:9222" else None,
            ),
        ):
            resolved = resolve_cdp_url("auto")

        self.assertEqual(resolved, "http://127.0.0.1:9222")


if __name__ == "__main__":
    unittest.main()
