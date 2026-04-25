from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from goofish_insight.settings import Settings, get_settings


class DatabaseSettingsTest(unittest.TestCase):
    def test_database_pool_defaults_are_large_enough_for_dashboard(self) -> None:
        settings = get_settings()

        self.assertGreaterEqual(settings.db_pool_size, 20)
        self.assertGreaterEqual(settings.db_max_overflow, 20)
        self.assertGreaterEqual(settings.db_pool_timeout_sec, 30)
        self.assertGreaterEqual(settings.db_pool_recycle_sec, 1800)

    def test_settings_support_ark_ai_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "ARK_AI_PROVIDER=ark_responses",
                        "ARK_AI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3",
                        "ARK_AI_API_KEY=test-ark-key",
                        "ARK_AI_MODEL=doubao-seed-1-6-251015",
                        "ARK_AI_TIMEOUT_SEC=75",
                        "ARK_AI_ENABLE_THINKING=false",
                        "ARK_AI_MAX_TOKENS=1024",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            settings = Settings(_env_file=env_path)

        self.assertEqual(settings.ai_provider, "ark_responses")
        self.assertEqual(settings.ai_base_url, "https://ark.cn-beijing.volces.com/api/v3")
        self.assertEqual(settings.ai_api_key, "test-ark-key")
        self.assertEqual(settings.ai_model, "doubao-seed-1-6-251015")
        self.assertEqual(settings.ai_timeout_sec, 75)
        self.assertFalse(settings.ai_enable_thinking)
        self.assertEqual(settings.ai_max_tokens, 1024)


if __name__ == "__main__":
    unittest.main()
