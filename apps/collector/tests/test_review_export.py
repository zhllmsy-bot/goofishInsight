from __future__ import annotations

import unittest

from goofish_insight.application.services.review_export import split_evenly, take_trailing_share


class ReviewExportTests(unittest.TestCase):
    def test_take_trailing_share_skips_front_twenty_percent(self) -> None:
        selected, skipped_count = take_trailing_share(list(range(10)), tail_fraction=0.8)

        self.assertEqual(skipped_count, 2)
        self.assertEqual(selected, [2, 3, 4, 5, 6, 7, 8, 9])

    def test_split_evenly_returns_exact_group_count(self) -> None:
        groups = split_evenly(list(range(8)), group_count=3)

        self.assertEqual(len(groups), 3)
        self.assertEqual([len(group) for group in groups], [3, 3, 2])

    def test_split_evenly_handles_more_groups_than_items(self) -> None:
        groups = split_evenly(["a", "b"], group_count=4)

        self.assertEqual(len(groups), 4)
        self.assertEqual(groups, [["a"], ["b"], [], []])


if __name__ == "__main__":
    unittest.main()
