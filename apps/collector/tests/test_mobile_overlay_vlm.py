from __future__ import annotations

import threading
import time
import unittest

from goofish_insight.application.services.mobile_overlay_vlm import (
    OverlayVlmAnalysis,
    OverlayVlmQueue,
    _extract_vlm_text,
    _parse_vlm_json_output,
)


class MobileOverlayVlmTests(unittest.TestCase):
    def test_parse_vlm_json_output_extracts_embedded_json(self) -> None:
        raw_output = """
        先思考一下截图内容。
        ```json
        {
          "title_candidate": "Garmin Fenix 8 47mm Solar",
          "business_domain_hint": "garmin",
          "confidence": 0.91
        }
        ```
        """.strip()

        payload = _parse_vlm_json_output(raw_output)

        self.assertEqual(payload["title_candidate"], "Garmin Fenix 8 47mm Solar")
        self.assertEqual(payload["business_domain_hint"], "garmin")
        self.assertEqual(payload["confidence"], 0.91)

    def test_extract_vlm_text_uses_output_text_fallbacks(self) -> None:
        body = {
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": "{\"title_candidate\": \"MacBook Pro 14\"}",
                        }
                    ]
                }
            ]
        }

        self.assertEqual(_extract_vlm_text(body), "{\"title_candidate\": \"MacBook Pro 14\"}")

    def test_queue_runs_jobs_serially(self) -> None:
        active_count = 0
        max_active = 0
        state_lock = threading.Lock()

        def worker(job) -> OverlayVlmAnalysis:
            nonlocal active_count, max_active
            with state_lock:
                active_count += 1
                max_active = max(max_active, active_count)
            time.sleep(0.05)
            with state_lock:
                active_count -= 1
            return OverlayVlmAnalysis(
                title_candidate=f"title:{job.source_package}",
                brand_hint=None,
                business_domain_hint=None,
                model_hint=None,
                spec_hint=None,
                price_hint=None,
                confidence=0.9,
                reason="ok",
                raw_output="{}",
                usage={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                queue={"job_id": job.job_id, "queue_position": job.queue_position},
                thinking_enabled=True,
                model="local-72b",
            )

        overlay_queue = OverlayVlmQueue(worker_fn=worker, result_timeout_sec=2.0)
        results: list[OverlayVlmAnalysis] = []

        def submit(tag: str) -> None:
            result = overlay_queue.submit_and_wait(
                screenshot_base64="abc",
                ocr_lines=[],
                screen_width=None,
                screen_height=None,
                source_package=tag,
            )
            results.append(result)

        thread_one = threading.Thread(target=submit, args=("one",))
        thread_two = threading.Thread(target=submit, args=("two",))
        thread_one.start()
        time.sleep(0.01)
        thread_two.start()
        thread_one.join()
        thread_two.join()

        self.assertEqual(len(results), 2)
        self.assertEqual(max_active, 1)
        self.assertTrue(all(result.thinking_enabled for result in results))


if __name__ == "__main__":
    unittest.main()
