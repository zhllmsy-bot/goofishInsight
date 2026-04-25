from __future__ import annotations

import unittest
from unittest.mock import patch

from goofish_insight.application.services.review_v3_cozeloop import (
    _managed_prompt_detail_snapshot,
    build_review_v3_cozeloop_prompt_detail,
    build_review_v3_cozeloop_prompt_key,
    execute_review_v3_prompt_via_cozeloop,
)
from goofish_insight.application.services.review_v3_profiles import get_review_v3_profile


class ReviewV3CozeloopTests(unittest.TestCase):
    def test_prompt_key_uses_v3_prefix(self) -> None:
        profile = get_review_v3_profile("camera_interchangeable_lens")
        assert profile is not None

        key = build_review_v3_cozeloop_prompt_key(profile, "first_pass")

        self.assertEqual(key, "goofish-review-v3-first_pass-camera_interchangeable_lens")

    def test_prompt_detail_disables_json_mode_for_ark_compatibility(self) -> None:
        profile = get_review_v3_profile("garmin_watch")
        assert profile is not None

        detail = build_review_v3_cozeloop_prompt_detail(profile, "second_pass")

        self.assertEqual(detail["model_config"]["model_id"], "1")
        self.assertEqual(detail["model_config"]["json_mode"], False)
        self.assertEqual(detail["model_config"]["thinking"]["thinking_option"], "disabled")
        self.assertEqual(detail["model_config"]["thinking"]["reasoning_effort"], "minimal")
        self.assertEqual(detail["prompt_template"]["messages"][1]["content"], "{{ payload_json }}")
        self.assertEqual(detail["prompt_template"]["variable_defs"][0]["key"], "payload_json")

    def test_first_pass_prompt_uses_phase_model_slot(self) -> None:
        profile = get_review_v3_profile("apple_computer")
        assert profile is not None

        detail = build_review_v3_cozeloop_prompt_detail(profile, "first_pass")

        self.assertEqual(detail["model_config"]["model_id"], "1")

    def test_prompt_detail_snapshot_ignores_server_only_fields(self) -> None:
        desired = {
            "prompt_template": {
                "template_type": "jinja2",
                "messages": [{"role": "system", "content": "x"}],
                "variable_defs": [{"key": "payload_json", "type": "string"}],
            },
            "model_config": {
                "model_id": "1",
                "temperature": 0,
                "max_tokens": 700,
                "json_mode": False,
                "thinking": {
                    "thinking_option": "disabled",
                    "reasoning_effort": "minimal",
                },
            },
        }
        current = {
            "prompt_template": {
                "template_type": "jinja2",
                "messages": [{"role": "system", "content": "x"}],
                "variable_defs": [{"key": "payload_json", "type": "string"}],
                "has_snippet": False,
            },
            "model_config": {
                "model_id": "1",
                "temperature": 0,
                "max_tokens": 700,
                "json_mode": False,
                "thinking": {
                    "thinking_option": "disabled",
                    "reasoning_effort": "minimal",
                },
            },
        }

        self.assertEqual(
            _managed_prompt_detail_snapshot(current),
            _managed_prompt_detail_snapshot(desired),
        )

    @patch("goofish_insight.application.services.review_v3_cozeloop.get_settings")
    @patch("goofish_insight.application.services.review_v3_cozeloop._cozeloop_json_request")
    def test_execute_prompt_uses_variable_payload_and_parses_usage(self, request_mock, settings_mock) -> None:
        profile = get_review_v3_profile("apple_computer")
        assert profile is not None
        settings_mock.return_value = type(
            "Settings",
            (),
            {
                "cozeloop_base_url": "http://127.0.0.1:8888",
                "cozeloop_workspace_id": "7627180063670140929",
                "cozeloop_pat": "pat-token",
                "cozeloop_prompt_key_prefix": "goofish-review-v3",
                "cozeloop_model_id": 1,
                "cozeloop_first_pass_model_id": 1,
                "cozeloop_second_pass_model_id": 1,
                "cozeloop_first_pass_model_name": "doubao-seed-2.0-pro",
                "cozeloop_second_pass_model_name": "doubao-seed-2.0-pro",
                "ai_model": "doubao-seed-2.0-pro",
            },
        )()
        request_mock.return_value = {
            "code": 0,
            "data": {
                "message": {"content": '{"ok":true}'},
                "usage": {"input_tokens": 12, "output_tokens": 34},
            },
        }

        result = execute_review_v3_prompt_via_cozeloop(
            profile=profile,
            phase="first_pass",
            user_payload={"item_id": "123", "title": "macbook pro"},
        )

        self.assertEqual(result.content, '{"ok":true}')
        self.assertEqual(result.provider, "cozeloop")
        self.assertEqual(result.model, "doubao-seed-2.0-pro")
        self.assertEqual(result.usage, {"input_tokens": 12, "output_tokens": 34, "total_tokens": 46})
        _, kwargs = request_mock.call_args
        self.assertEqual(kwargs["path"], "/v1/loop/prompts/execute")
        self.assertEqual(kwargs["body"]["prompt_identifier"]["prompt_key"], "goofish-review-v3-first_pass-apple_computer")
        self.assertIn('"item_id":"123"', kwargs["body"]["variable_vals"][0]["value"])


if __name__ == "__main__":
    unittest.main()
