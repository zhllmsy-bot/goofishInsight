from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from goofish_insight.application.services.mobile_overlay_analysis import build_mobile_overlay_analysis
from goofish_insight.application.services.mobile_overlay_vlm import OverlayVlmAnalysis


class MobileOverlayAnalysisTests(unittest.TestCase):
    def test_build_mobile_overlay_analysis_prefers_vlm_title_when_confident(self) -> None:
        task = SimpleNamespace(
            business_domain="apple_m_series",
            task_key="apple-m-series",
            display_name="Apple M Series",
        )
        vlm_result = OverlayVlmAnalysis(
            title_candidate="Apple MacBook Pro 14 M3 Pro 18G 512G",
            brand_hint="Apple",
            business_domain_hint="apple_m_series",
            model_hint="MacBook Pro 14 M3 Pro",
            spec_hint="18G 512G",
            price_hint="￥10999",
            confidence=0.93,
            reason="截图标题和机型区域清晰可见",
            raw_output="{}",
            usage={"input_tokens": 1200, "output_tokens": 96, "total_tokens": 1296},
            queue={"job_id": "job-1", "queue_position": 1, "queue_wait_seconds": 0.0, "run_seconds": 1.2},
            thinking_enabled=True,
            model="Qwen2.5-VL-72B-Instruct-4bit-MLX",
        )

        with (
            patch(
                "goofish_insight.application.services.mobile_overlay_analysis.load_active_tasks_by_domain",
                return_value={"apple_m_series": task},
            ),
            patch(
                "goofish_insight.application.services.mobile_overlay_analysis.analyze_mobile_overlay_screenshot",
                return_value=vlm_result,
            ),
            patch(
                "goofish_insight.application.services.mobile_overlay_analysis.analyze_domain_candidate",
                return_value={
                    "business_domain": "apple_m_series",
                    "pricing": {
                        "label": "MacBook Pro 14",
                        "product_label": "MacBook Pro 14",
                        "spec_label": "M3 Pro 18G 512G",
                        "reliability_score": 88,
                        "sample_confident": True,
                        "is_actionable": True,
                        "target_buy_ceiling": 9800,
                        "fair_price": 10600,
                        "safe_buy_price": 9300,
                        "listing_price": 9600,
                        "expected_profit_margin_pct": 10.4,
                    },
                    "score": 320,
                    "trend": {"trend_quality_ok": True},
                },
            ),
        ):
            result = build_mobile_overlay_analysis(
                session=None,
                ocr_lines=[],
                screenshot_base64="data:image/png;base64,abc",
                screen_width=1080,
                screen_height=2400,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["ocr_summary"]["title_candidate_source"], "vlm")
        self.assertEqual(result["ocr_summary"]["title_candidate"], "Apple MacBook Pro 14 M3 Pro 18G 512G")
        self.assertEqual(result["vlm_summary"]["business_domain_hint"], "apple_m_series")
        self.assertTrue(result["vlm_summary"]["thinking_enabled"])
        self.assertEqual(result["match"]["business_domain"], "apple_m_series")


if __name__ == "__main__":
    unittest.main()
