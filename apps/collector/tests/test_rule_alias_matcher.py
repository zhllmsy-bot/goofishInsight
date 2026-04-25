from __future__ import annotations

import unittest

from goofish_insight.application.services.rule_alias_matcher import match_rule_alias, normalize_alias_text


class RuleAliasMatcherTests(unittest.TestCase):
    def test_normalize_alias_text_removes_common_separators(self) -> None:
        self.assertEqual(normalize_alias_text(" MacBook-Pro / M4 "), "macbookprom4")

    def test_match_rule_alias_prefers_longer_higher_confidence_alias(self) -> None:
        match = match_rule_alias(
            title="自用 MBP M3 Pro 18G 512G 国行",
            category_code="apple_computer",
            field="model_family",
        )

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.value, "MacBook Pro")
        self.assertEqual(match.match_type, "contains")
        self.assertGreaterEqual(match.confidence, 0.6)

    def test_match_rule_alias_handles_chinese_garmin_family(self) -> None:
        match = match_rule_alias(
            title="佳明飞耐时8 51mm 蓝宝石太阳能",
            category_code="garmin_watch",
            field="model_family",
        )

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.value, "Fenix")

    def test_match_rule_alias_prefers_exact_over_contains(self) -> None:
        match = match_rule_alias(
            title="MBP",
            category_code="apple_computer",
            field="model_family",
        )

        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.value, "MacBook Pro")
        self.assertEqual(match.match_type, "exact")


if __name__ == "__main__":
    unittest.main()
