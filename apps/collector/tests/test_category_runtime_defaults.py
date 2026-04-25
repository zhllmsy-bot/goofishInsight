from __future__ import annotations

import unittest

from goofish_insight.category_runtime_defaults import (
    get_category_runtime_default,
    recommended_prompt_profile_for_category,
)


class CategoryRuntimeDefaultsTests(unittest.TestCase):
    def test_camera_body_runtime_default_is_available(self) -> None:
        runtime_default = get_category_runtime_default("camera_body")

        self.assertIsNotNone(runtime_default)
        self.assertEqual(runtime_default.prompt_profile, "camera_body_extract_v1")
        self.assertEqual(runtime_default.extractor_profile, "default")

    def test_camera_body_recommended_prompt_profile_is_exposed(self) -> None:
        self.assertEqual(
            recommended_prompt_profile_for_category("camera_body"),
            "camera_body_extract_v1",
        )


if __name__ == "__main__":
    unittest.main()
