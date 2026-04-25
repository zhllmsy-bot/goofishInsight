from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from goofish_insight.application.services.review_v3_executor import (
    ReviewV3ExecutionResult,
    execute_review_v3_prompt,
)
from goofish_insight.application.services.review_v3_profiles import get_review_v3_profile


class ReviewV3ExecutorTests(unittest.TestCase):
    def test_execute_review_v3_prompt_retries_once_on_timeout(self) -> None:
        profile = get_review_v3_profile("apple_computer")
        assert profile is not None
        settings = SimpleNamespace(
            ai_base_url="https://example.invalid/v1",
            ai_api_key="test-key",
            ai_model="doubao-seed-2.0-pro",
            ai_timeout_sec=30,
            ai_enable_thinking=False,
            review_v3_ai_max_tokens=220,
            review_v3_batch_ai_max_tokens=900,
            ai_provider="openai_compatible",
            review_v3_executor="direct",
        )
        payload = {"choices": [{"message": {"content": "{\"ok\":true}"}}], "usage": {"total_tokens": 12}}
        with patch(
            "goofish_insight.application.services.review_v3_executor.get_settings",
            return_value=settings,
        ), patch(
            "goofish_insight.application.services.review_v3_executor.call_openai_compatible_chat",
            side_effect=[TimeoutError("read timed out"), payload],
        ) as call_mock, patch(
            "goofish_insight.application.services.review_v3_executor.extract_message_content",
            return_value="{\"ok\":true}",
        ), patch(
            "goofish_insight.application.services.review_v3_executor.extract_usage_stats",
            return_value={"total_tokens": 12},
        ), patch(
            "goofish_insight.application.services.review_v3_executor.time.sleep",
        ) as sleep_mock:
            result = execute_review_v3_prompt(
                profile=profile,
                phase="first_pass",
                user_payload={"item_id": "demo"},
            )

        self.assertIsInstance(result, ReviewV3ExecutionResult)
        self.assertEqual(result.content, "{\"ok\":true}")
        self.assertEqual(result.usage, {"total_tokens": 12})
        self.assertEqual(call_mock.call_count, 2)
        sleep_mock.assert_called_once()
        kwargs = call_mock.call_args.kwargs
        self.assertEqual(kwargs["max_tokens"], 220)
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})

    def test_execute_review_v3_prompt_retries_once_on_429_runtime_error(self) -> None:
        profile = get_review_v3_profile("garmin_watch")
        assert profile is not None
        settings = SimpleNamespace(
            ai_base_url="https://ark.cn-beijing.volces.com/api/coding/v3",
            ai_api_key="test-key",
            ai_model="doubao-seed-2.0-pro",
            ai_timeout_sec=30,
            ai_enable_thinking=False,
            review_v3_ai_max_tokens=220,
            review_v3_batch_ai_max_tokens=900,
            ai_provider="openai_compatible",
            review_v3_executor="direct",
        )
        payload = {"choices": [{"message": {"content": "{\"ok\":true}"}}], "usage": {"total_tokens": 34}}
        with patch(
            "goofish_insight.application.services.review_v3_executor.get_settings",
            return_value=settings,
        ), patch(
            "goofish_insight.application.services.review_v3_executor.call_openai_compatible_chat",
            side_effect=[
                RuntimeError("LLM request failed with HTTP 429: {\"error\":{\"code\":\"RequestBurstTooFast\"}}"),
                payload,
            ],
        ) as call_mock, patch(
            "goofish_insight.application.services.review_v3_executor.extract_message_content",
            return_value="{\"ok\":true}",
        ), patch(
            "goofish_insight.application.services.review_v3_executor.extract_usage_stats",
            return_value={"total_tokens": 34},
        ), patch(
            "goofish_insight.application.services.review_v3_executor.random.uniform",
            return_value=0.0,
        ), patch(
            "goofish_insight.application.services.review_v3_executor.time.sleep",
        ) as sleep_mock:
            result = execute_review_v3_prompt(
                profile=profile,
                phase="first_pass",
                user_payload={"item_id": "demo"},
            )

        self.assertIsInstance(result, ReviewV3ExecutionResult)
        self.assertEqual(result.usage, {"total_tokens": 34})
        self.assertEqual(call_mock.call_count, 2)
        sleep_mock.assert_called_once_with(3.0)

    def test_execute_review_v3_prompt_does_not_retry_generic_runtime_error(self) -> None:
        profile = get_review_v3_profile("apple_computer")
        assert profile is not None
        settings = SimpleNamespace(
            ai_base_url="https://example.invalid/v1",
            ai_api_key="test-key",
            ai_model="doubao-seed-2.0-pro",
            ai_timeout_sec=30,
            ai_enable_thinking=False,
            review_v3_ai_max_tokens=220,
            review_v3_batch_ai_max_tokens=900,
            ai_provider="openai_compatible",
            review_v3_executor="direct",
        )
        with patch(
            "goofish_insight.application.services.review_v3_executor.get_settings",
            return_value=settings,
        ), patch(
            "goofish_insight.application.services.review_v3_executor.call_openai_compatible_chat",
            side_effect=RuntimeError("schema mismatch"),
        ) as call_mock, patch(
            "goofish_insight.application.services.review_v3_executor.time.sleep",
        ) as sleep_mock:
            with self.assertRaisesRegex(RuntimeError, "schema mismatch"):
                execute_review_v3_prompt(
                    profile=profile,
                    phase="first_pass",
                    user_payload={"item_id": "demo"},
                )

        self.assertEqual(call_mock.call_count, 1)
        sleep_mock.assert_not_called()

    def test_execute_review_v3_prompt_disables_json_response_format_for_ark(self) -> None:
        profile = get_review_v3_profile("apple_computer")
        assert profile is not None
        settings = SimpleNamespace(
            ai_base_url="https://ark.cn-beijing.volces.com/api/coding/v3",
            ai_api_key="test-key",
            ai_model="doubao-seed-2.0-pro",
            ai_timeout_sec=30,
            ai_enable_thinking=False,
            review_v3_ai_max_tokens=220,
            review_v3_batch_ai_max_tokens=900,
            ai_provider="openai_compatible",
            review_v3_executor="direct",
        )
        payload = {"choices": [{"message": {"content": "{\"ok\":true}"}}], "usage": {"total_tokens": 12}}
        with patch(
            "goofish_insight.application.services.review_v3_executor.get_settings",
            return_value=settings,
        ), patch(
            "goofish_insight.application.services.review_v3_executor.call_openai_compatible_chat",
            return_value=payload,
        ) as call_mock, patch(
            "goofish_insight.application.services.review_v3_executor.extract_message_content",
            return_value="{\"ok\":true}",
        ), patch(
            "goofish_insight.application.services.review_v3_executor.extract_usage_stats",
            return_value={"total_tokens": 12},
        ):
            execute_review_v3_prompt(
                profile=profile,
                phase="first_pass",
                user_payload={"item_id": "demo"},
            )

        kwargs = call_mock.call_args.kwargs
        self.assertIsNone(kwargs["response_format"])

    def test_execute_review_v3_prompt_uses_system_prompt_override(self) -> None:
        profile = get_review_v3_profile("camera_interchangeable_lens")
        assert profile is not None
        settings = SimpleNamespace(
            ai_base_url="https://example.invalid/v1",
            ai_api_key="test-key",
            ai_model="doubao-seed-2.0-pro",
            ai_timeout_sec=30,
            ai_enable_thinking=False,
            review_v3_ai_max_tokens=220,
            review_v3_batch_ai_max_tokens=900,
            ai_provider="openai_compatible",
            review_v3_executor="direct",
        )
        payload = {"choices": [{"message": {"content": "{\"ok\":true}"}}], "usage": {"total_tokens": 12}}
        with patch(
            "goofish_insight.application.services.review_v3_executor.get_settings",
            return_value=settings,
        ), patch(
            "goofish_insight.application.services.review_v3_executor.call_openai_compatible_chat",
            return_value=payload,
        ) as call_mock, patch(
            "goofish_insight.application.services.review_v3_executor.extract_message_content",
            return_value="{\"ok\":true}",
        ), patch(
            "goofish_insight.application.services.review_v3_executor.extract_usage_stats",
            return_value={"total_tokens": 12},
        ):
            execute_review_v3_prompt(
                profile=profile,
                phase="first_pass",
                user_payload={"item_id": "demo"},
                system_prompt_override="batch system prompt",
            )

        kwargs = call_mock.call_args.kwargs
        self.assertEqual(kwargs["messages"][0]["content"], "batch system prompt")

    def test_execute_review_v3_prompt_uses_batch_max_tokens_for_first_pass_batch(self) -> None:
        profile = get_review_v3_profile("apple_computer")
        assert profile is not None
        settings = SimpleNamespace(
            ai_base_url="https://example.invalid/v1",
            ai_api_key="test-key",
            ai_model="doubao-seed-2.0-pro",
            ai_timeout_sec=30,
            ai_enable_thinking=False,
            review_v3_ai_max_tokens=220,
            review_v3_batch_ai_max_tokens=900,
            ai_provider="openai_compatible",
            review_v3_executor="direct",
        )
        payload = {"choices": [{"message": {"content": "{\"items\":[]}"}}], "usage": {"total_tokens": 12}}
        with patch(
            "goofish_insight.application.services.review_v3_executor.get_settings",
            return_value=settings,
        ), patch(
            "goofish_insight.application.services.review_v3_executor.call_openai_compatible_chat",
            return_value=payload,
        ) as call_mock, patch(
            "goofish_insight.application.services.review_v3_executor.extract_message_content",
            return_value="{\"items\":[]}",
        ), patch(
            "goofish_insight.application.services.review_v3_executor.extract_usage_stats",
            return_value={"total_tokens": 12},
        ):
            execute_review_v3_prompt(
                profile=profile,
                phase="first_pass",
                user_payload={"task": "first_pass_feature_extraction_batch", "items": []},
            )

        kwargs = call_mock.call_args.kwargs
        self.assertEqual(kwargs["max_tokens"], 900)


if __name__ == "__main__":
    unittest.main()
