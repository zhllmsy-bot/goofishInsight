from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from goofish_insight.specs import (
    build_openai_request,
    call_openai_compatible_chat,
    build_anthropic_request,
    build_ark_responses_request,
    extract_message_content,
    extract_usage_stats,
    llm_is_configured,
)


class LlmClientTests(unittest.TestCase):
    def test_build_openai_request_explicitly_disables_thinking_for_ark(self) -> None:
        request = build_openai_request(
            base_url="https://ark.cn-beijing.volces.com/api/coding/v3",
            api_key="secret",
            model="doubao-seed-2.0-pro",
            enable_thinking=False,
            max_tokens=5000,
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": "Audit listings."},
            ],
        )

        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["extra_body"], {"enable_thinking": False})

    def test_build_anthropic_request_moves_system_prompt_and_uses_messages_endpoint(self) -> None:
        request = build_anthropic_request(
            base_url="http://192.168.10.16:8000",
            api_key="",
            model="qwen2.5-vl-32b-mlx-4bit",
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": "Extract specs."},
            ],
        )

        self.assertEqual(request.full_url, "http://192.168.10.16:8000/v1/messages")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(request.get_header("Anthropic-version"), "2023-06-01")
        self.assertIsNone(request.get_header("Authorization"))

        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "qwen2.5-vl-32b-mlx-4bit")
        self.assertEqual(payload["system"], "Return JSON only.")
        self.assertEqual(
            payload["messages"],
            [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "Extract specs."}],
                }
            ],
        )

    def test_extract_message_content_supports_anthropic_payload(self) -> None:
        payload = {
            "id": "msg_123",
            "type": "message",
            "role": "assistant",
            "model": "qwen2.5-vl-32b-mlx-4bit",
            "content": [
                {"type": "text", "text": '{"status":"complete","confidence":0.92}'},
            ],
            "stop_reason": "end_turn",
        }

        self.assertEqual(
            extract_message_content(payload),
            '{"status":"complete","confidence":0.92}',
        )

    def test_build_ark_responses_request_uses_responses_endpoint(self) -> None:
        request = build_ark_responses_request(
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="secret",
            model="doubao-seed-1-6-flash-250828",
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {"role": "user", "content": "Extract specs."},
            ],
        )

        self.assertEqual(request.full_url, "https://ark.cn-beijing.volces.com/api/v3/responses")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "doubao-seed-1-6-flash-250828")
        self.assertEqual(payload["input"][0]["role"], "system")
        self.assertEqual(payload["input"][1]["content"][0]["type"], "input_text")

    def test_extract_message_content_supports_responses_api_payload(self) -> None:
        payload = {
            "object": "response",
            "output": [
                {"type": "reasoning", "summary": []},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": '[{"item_id":"abc","review_status":"valid","confidence":0.95}]'},
                    ],
                },
            ],
        }

        self.assertEqual(
            extract_message_content(payload),
            '[{"item_id":"abc","review_status":"valid","confidence":0.95}]',
        )

    def test_extract_usage_stats_supports_openai_style_usage(self) -> None:
        payload = {
            "usage": {
                "prompt_tokens": 1200,
                "completion_tokens": 180,
                "total_tokens": 1380,
            }
        }

        self.assertEqual(
            extract_usage_stats(payload),
            {
                "input_tokens": 1200,
                "output_tokens": 180,
                "total_tokens": 1380,
                "cached_tokens": 0,
            },
        )

    def test_extract_usage_stats_supports_responses_usage(self) -> None:
        payload = {
            "usage": {
                "input_tokens": 800,
                "output_tokens": 100,
                "total_tokens": 900,
                "input_tokens_details": {"cached_tokens": 240},
            }
        }

        self.assertEqual(
            extract_usage_stats(payload),
            {
                "input_tokens": 800,
                "output_tokens": 100,
                "total_tokens": 900,
                "cached_tokens": 240,
            },
        )

    def test_llm_is_configured_allows_anthropic_without_api_key(self) -> None:
        settings = SimpleNamespace(
            ai_provider="anthropic_compatible",
            ai_base_url="http://192.168.10.16:8000",
            ai_model="qwen2.5-vl-32b-mlx-4bit",
            ai_api_key="",
        )
        with patch("goofish_insight.specs.get_settings", return_value=settings):
            self.assertTrue(llm_is_configured())

    def test_call_openai_compatible_chat_writes_prompt_trace_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            settings = SimpleNamespace(
                ai_provider="ark_responses",
                ai_max_tokens=600,
                ai_prompt_trace_enabled=True,
                ai_prompt_trace_dir=tmp_dir,
            )

            class _FakeResponse:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

                def read(self):
                    return json.dumps(
                        {
                            "output": [
                                {
                                    "type": "message",
                                    "role": "assistant",
                                    "content": [{"type": "output_text", "text": '{"ok":true}'}],
                                }
                            ]
                        }
                    ).encode("utf-8")

            with (
                patch("goofish_insight.specs.get_settings", return_value=settings),
                patch("goofish_insight.specs.urlopen", return_value=_FakeResponse()),
            ):
                payload = call_openai_compatible_chat(
                    base_url="https://ark.cn-beijing.volces.com/api/v3",
                    api_key="secret",
                    model="doubao-seed-1-6-flash-250828",
                    timeout_sec=30,
                    enable_thinking=False,
                    messages=[
                        {"role": "system", "content": "Return JSON only."},
                        {"role": "user", "content": "Extract specs."},
                    ],
                )

            self.assertEqual(payload["output"][0]["type"], "message")
            trace_files = list(Path(tmp_dir).glob("*.json"))
            self.assertEqual(len(trace_files), 1)
            trace_payload = json.loads(trace_files[0].read_text(encoding="utf-8"))
            self.assertEqual(trace_payload["provider"], "ark_responses")
            self.assertEqual(trace_payload["messages"][0]["content"], "Return JSON only.")
            self.assertEqual(trace_payload["requestHeaders"]["Authorization"], "[REDACTED]")
            self.assertEqual(trace_payload["requestPayload"]["input"][1]["content"][0]["text"], "Extract specs.")
            self.assertIsNone(trace_payload["error"])


if __name__ == "__main__":
    unittest.main()
