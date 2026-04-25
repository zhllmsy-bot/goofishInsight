from __future__ import annotations

import threading
import unittest

from goofish_insight.application.services import web_section_cache


class WebSectionCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        web_section_cache._SECTION_CACHE.clear()

    def test_returns_deepcopied_cached_value(self) -> None:
        build_calls = 0

        def builder() -> dict[str, object]:
            nonlocal build_calls
            build_calls += 1
            return {"items": [{"id": 1}]}

        first = web_section_cache.get_ttl_cached_payload(
            namespace="dashboard",
            key=("header",),
            ttl_seconds=60.0,
            builder=builder,
        )
        first["items"][0]["id"] = 99

        second = web_section_cache.get_ttl_cached_payload(
            namespace="dashboard",
            key=("header",),
            ttl_seconds=60.0,
            builder=builder,
        )

        self.assertEqual(build_calls, 1)
        self.assertEqual(second["items"][0]["id"], 1)

    def test_nested_cache_builders_do_not_deadlock(self) -> None:
        result: dict[str, object] = {}
        errors: list[BaseException] = []

        def target() -> None:
            try:
                result["value"] = web_section_cache.get_ttl_cached_payload(
                    namespace="outer",
                    key=("hero",),
                    ttl_seconds=60.0,
                    builder=lambda: {
                        "inner": web_section_cache.get_ttl_cached_payload(
                            namespace="inner",
                            key=("filters",),
                            ttl_seconds=60.0,
                            builder=lambda: {"ok": True},
                        )
                    },
                )
            except BaseException as exc:  # pragma: no cover - test helper guard
                errors.append(exc)

        thread = threading.Thread(target=target, daemon=True)
        thread.start()
        thread.join(timeout=1.0)

        self.assertFalse(thread.is_alive(), "nested cache access should not deadlock")
        self.assertEqual(errors, [])
        self.assertEqual(result["value"], {"inner": {"ok": True}})


if __name__ == "__main__":
    unittest.main()
