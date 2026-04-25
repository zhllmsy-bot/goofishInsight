from __future__ import annotations

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import typer
from typer.testing import CliRunner

from goofish_insight.application.services.review_second_pass import (
    ReviewPassTrace,
    build_second_pass_system_prompt,
    build_second_pass_user_prompt,
    extract_second_pass_json_items,
    review_item_with_second_pass,
)
from goofish_insight.entrypoints.cli.review import register_review_commands
from goofish_insight.settings import get_settings


class ReviewSecondPassTests(unittest.TestCase):
    @staticmethod
    def _stub_settings(*, ai_base_url: str = "", ai_model: str = ""):
        class _SettingsFactory:
            def __call__(self):
                return SimpleNamespace(ai_base_url=ai_base_url, ai_model=ai_model)

            def cache_clear(self) -> None:
                return None

        return _SettingsFactory()

    def make_item(self, *, item_id: str = "abc123", title: str = "MacBook Air M2 16G 512G") -> dict:
        return {
            "item_id": item_id,
            "business_domain": "apple_m_series",
            "title": title,
            "current_price": 5999,
            "source_keyword": "macbook air m2",
            "condition_tags": ["95新"],
            "region": "Shanghai",
            "listing_description": "自用出售，M2，16G+512G，价格可聊",
            "listing_description_length": 20,
            "current_values": {},
            "rule_candidate": {},
        }

    def test_second_pass_prompts_emphasize_single_item_array_output(self) -> None:
        system_prompt = build_second_pass_system_prompt()
        user_prompt = build_second_pass_user_prompt(
            item=self.make_item(),
            first_pass_candidate={
                "item_id": "abc123",
                "review_status": "valid",
                "confidence": 0.71,
                "invalid_reason": None,
                "not_match_field": [],
            },
        )
        payload = json.loads(user_prompt)

        self.assertIn("one-element JSON array", system_prompt)
        self.assertIn("maximize downstream pricing reliability", system_prompt)
        self.assertIn("probability that the listing is a real target-device sale listing", system_prompt)
        self.assertIn("first_pass_hint", user_prompt)
        self.assertIn("second_pass_reliability_review", user_prompt)
        self.assertEqual(
            payload["first_pass_hint"],
            {
                "review_status": "valid",
                "confidence": 0.71,
            },
        )
        self.assertEqual(
            payload["item"],
            {
                "item_id": "abc123",
                "d": "apple_m_series",
                "t": "MacBook Air M2 16G 512G",
                "p": 5999,
                "k": "macbook air m2",
                "tags": ["95新"],
                "desc": "自用出售，M2，16G+512G，价格可聊",
            },
        )
        self.assertNotIn("not_match_field", payload["first_pass_hint"])
        self.assertNotIn("r", payload["item"])
        self.assertNotIn("desc_len", payload["item"])
        self.assertNotIn("rule", payload["item"])

    def test_extract_second_pass_json_items_accepts_single_object_payload(self) -> None:
        payload = '{"item_id":"abc123","review_status":"valid","confidence":0.93,"invalid_reason":"","not_match_field":[]}'

        parsed = extract_second_pass_json_items(payload)

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["item_id"], "abc123")

    def test_review_item_with_second_pass_keeps_rule_precheck_without_llm(self) -> None:
        item = self.make_item(title="想收一个 MacBook Air M2")

        result = review_item_with_second_pass(item=item)

        self.assertEqual(result.llm_request_count, 0)
        self.assertEqual(result.review_count, 1)
        self.assertEqual(result.entries[0]["review_status"], "invalid")
        self.assertEqual(result.entries[0]["invalid_reason"], "recycling")
        self.assertEqual(result.second_pass_requested_count, 0)

    @patch("goofish_insight.application.services.review_second_pass.execute_review_pass")
    def test_review_item_with_second_pass_rescues_low_confidence_first_pass(self, mock_execute_review_pass) -> None:
        item = self.make_item()
        mock_execute_review_pass.side_effect = [
            ReviewPassTrace(
                pass_name="first_pass",
                raw_items=[{"item_id": item["item_id"], "review_status": "valid", "confidence": 0.72, "not_match_field": []}],
                candidate={"item_id": item["item_id"], "review_status": "valid", "invalid_reason": None, "not_match_field": [], "confidence": 0.72},
                llm_usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120, "cached_tokens": 0},
                llm_request_count=1,
            ),
            ReviewPassTrace(
                pass_name="second_pass",
                raw_items=[{"item_id": item["item_id"], "review_status": "valid", "confidence": 0.95, "not_match_field": []}],
                candidate={"item_id": item["item_id"], "review_status": "valid", "invalid_reason": None, "not_match_field": [], "confidence": 0.95},
                llm_usage={"input_tokens": 90, "output_tokens": 18, "total_tokens": 108, "cached_tokens": 0},
                llm_request_count=1,
            ),
        ]

        result = review_item_with_second_pass(item=item)

        self.assertEqual(result.review_count, 1)
        self.assertEqual(result.high_confidence_kept_count, 1)
        self.assertEqual(result.low_confidence_filtered_count, 0)
        self.assertEqual(result.second_pass_requested_count, 1)
        self.assertEqual(result.second_pass_rescued_count, 1)
        self.assertEqual(result.llm_request_count, 2)
        self.assertEqual(result.entries[0]["item_id"], item["item_id"])
        self.assertEqual(result.entries[0]["review_status"], "valid")

    @patch("goofish_insight.application.services.review_second_pass.execute_review_pass")
    def test_review_item_with_second_pass_persists_unresolved_low_confidence(self, mock_execute_review_pass) -> None:
        item = self.make_item(item_id="xyz789")
        mock_execute_review_pass.side_effect = [
            ReviewPassTrace(
                pass_name="first_pass",
                raw_items=[{"item_id": item["item_id"], "review_status": "valid", "confidence": 0.61, "not_match_field": []}],
                candidate={"item_id": item["item_id"], "review_status": "valid", "invalid_reason": None, "not_match_field": [], "confidence": 0.61},
                llm_usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120, "cached_tokens": 0},
                llm_request_count=1,
            ),
            ReviewPassTrace(
                pass_name="second_pass",
                raw_items=[{"item_id": item["item_id"], "review_status": "invalid", "confidence": 0.54, "invalid_reason": "other", "not_match_field": []}],
                candidate={"item_id": item["item_id"], "review_status": "invalid", "invalid_reason": "other", "not_match_field": [], "confidence": 0.54},
                llm_usage={"input_tokens": 95, "output_tokens": 25, "total_tokens": 120, "cached_tokens": 0},
                llm_request_count=1,
            ),
        ]

        result = review_item_with_second_pass(item=item)

        self.assertEqual(result.review_count, 0)
        self.assertEqual(result.entries, [])
        self.assertEqual(result.low_confidence_filtered_count, 1)
        self.assertEqual(result.second_pass_requested_count, 1)
        self.assertEqual(result.second_pass_unresolved_count, 1)
        self.assertEqual(len(result.unresolved_details), 1)
        self.assertEqual(result.unresolved_details[0]["item_id"], item["item_id"])
        self.assertEqual(result.unresolved_details[0]["final_disposition"], "unresolved_low_confidence")

    @patch("goofish_insight.application.services.review_second_pass.execute_review_pass")
    def test_review_item_with_second_pass_accepts_strong_invalid_second_pass(self, mock_execute_review_pass) -> None:
        item = self.make_item(item_id="invalid-strong")
        mock_execute_review_pass.side_effect = [
            ReviewPassTrace(
                pass_name="first_pass",
                raw_items=[{"item_id": item["item_id"], "review_status": "valid", "confidence": 0.61, "not_match_field": []}],
                candidate={"item_id": item["item_id"], "review_status": "valid", "invalid_reason": None, "not_match_field": [], "confidence": 0.61},
                llm_usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120, "cached_tokens": 0},
                llm_request_count=1,
            ),
            ReviewPassTrace(
                pass_name="second_pass",
                raw_items=[{"item_id": item["item_id"], "review_status": "invalid", "confidence": 0.18, "invalid_reason": "other", "not_match_field": []}],
                candidate={"item_id": item["item_id"], "review_status": "invalid", "invalid_reason": "other", "not_match_field": [], "confidence": 0.18},
                llm_usage={"input_tokens": 95, "output_tokens": 25, "total_tokens": 120, "cached_tokens": 0},
                llm_request_count=1,
            ),
        ]

        result = review_item_with_second_pass(item=item)

        self.assertEqual(result.review_count, 1)
        self.assertEqual(result.low_confidence_filtered_count, 0)
        self.assertEqual(result.second_pass_requested_count, 1)
        self.assertEqual(result.second_pass_rescued_count, 1)
        self.assertEqual(result.entries[0]["review_status"], "invalid")
        self.assertEqual(result.entries[0]["confidence"], 0.18)

    def test_review_items_llm_second_pass_defaults_to_local_qwen(self) -> None:
        app = typer.Typer()
        register_review_commands(app)
        runner = CliRunner()
        captured: dict[str, str | None] = {}

        def fake_llm_is_configured() -> bool:
            captured["provider"] = os.environ.get("AI_PROVIDER")
            captured["base_url"] = os.environ.get("AI_BASE_URL")
            captured["api_key"] = os.environ.get("AI_API_KEY")
            captured["model"] = os.environ.get("AI_MODEL")
            return True

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("goofish_insight.entrypoints.cli.review.get_settings", self._stub_settings()),
            patch("goofish_insight.application.services.review_second_pass.get_settings", self._stub_settings()),
            patch("goofish_insight.entrypoints.cli.review.llm_is_configured", side_effect=fake_llm_is_configured),
            patch("goofish_insight.entrypoints.cli.review.run_review_v3_second_pass", return_value=[]),
        ):
            result = runner.invoke(app, ["review-items-llm-second-pass", "--limit", "1"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout.strip(), "[]")
        self.assertEqual(captured["provider"], "openai_compatible")
        self.assertEqual(captured["base_url"], "http://127.0.0.1:8000/v1")
        self.assertEqual(captured["api_key"], "local-dev")
        self.assertEqual(captured["model"], "Qwen3-30B-A3B-MLX-4bit")

    def test_review_items_llm_second_pass_keeps_explicit_ai_override(self) -> None:
        app = typer.Typer()
        register_review_commands(app)
        runner = CliRunner()
        captured: dict[str, str | None] = {}
        explicit_env = {
            "AI_PROVIDER": "custom-provider",
            "AI_BASE_URL": "https://example.com/v1",
            "AI_API_KEY": "explicit-key",
            "AI_MODEL": "custom-model",
        }

        def fake_llm_is_configured() -> bool:
            captured["provider"] = os.environ.get("AI_PROVIDER")
            captured["base_url"] = os.environ.get("AI_BASE_URL")
            captured["api_key"] = os.environ.get("AI_API_KEY")
            captured["model"] = os.environ.get("AI_MODEL")
            return True

        with (
            patch.dict(os.environ, explicit_env, clear=True),
            patch("goofish_insight.entrypoints.cli.review.get_settings", self._stub_settings()),
            patch("goofish_insight.application.services.review_second_pass.get_settings", self._stub_settings()),
            patch("goofish_insight.entrypoints.cli.review.llm_is_configured", side_effect=fake_llm_is_configured),
            patch("goofish_insight.entrypoints.cli.review.run_review_v3_second_pass", return_value=[]),
        ):
            result = runner.invoke(app, ["review-items-llm-second-pass", "--limit", "1"])

        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.stdout.strip(), "[]")
        self.assertEqual(captured["provider"], explicit_env["AI_PROVIDER"])
        self.assertEqual(captured["base_url"], explicit_env["AI_BASE_URL"])
        self.assertEqual(captured["api_key"], explicit_env["AI_API_KEY"])
        self.assertEqual(captured["model"], explicit_env["AI_MODEL"])


if __name__ == "__main__":
    unittest.main()
