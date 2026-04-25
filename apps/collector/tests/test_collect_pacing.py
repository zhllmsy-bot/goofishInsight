from __future__ import annotations

import unittest
from unittest.mock import patch

from goofish_insight.cli import (
    SEARCH_PAGE_INTERVAL_MAX_MS,
    SEARCH_PAGE_INTERVAL_MIN_MS,
    search_page_interval_ms,
)


class CollectPacingTests(unittest.TestCase):
    def test_search_page_interval_ms_uses_30_second_window(self) -> None:
        with patch("goofish_insight.cli.random.randint", return_value=30000) as mocked:
            interval_ms = search_page_interval_ms()

        mocked.assert_called_once_with(
            SEARCH_PAGE_INTERVAL_MIN_MS,
            SEARCH_PAGE_INTERVAL_MAX_MS,
        )
        self.assertEqual(interval_ms, 30000)


if __name__ == "__main__":
    unittest.main()
