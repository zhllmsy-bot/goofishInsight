from __future__ import annotations

import unittest

from goofish_insight.application.services.spec_candidate_queue import filter_frozen_db_item_ids
from goofish_insight.application.services.spec_worker_state import (
    FREEZE_REASON_REPEAT_RESULT,
    result_signature,
    update_worker_state_from_batch,
)


class SpecEnrichmentWorkerTests(unittest.TestCase):
    def test_result_signature_captures_stable_identity(self) -> None:
        signature = result_signature(
            {
                "item_id": "abc",
                "status": "partial",
                "confidence": 0.78,
                "model_name": "NIKKOR Z 24-70mm S",
                "extractor_type": "rule",
            }
        )

        self.assertEqual(signature, "partial|0.78|NIKKOR Z 24-70mm S|rule")

    def test_filter_frozen_db_item_ids_removes_blocked_items(self) -> None:
        self.assertEqual(
            filter_frozen_db_item_ids(db_item_ids=[1, 2, 3, 4], frozen_db_ids={2, 4}),
            [1, 3],
        )

    def test_repeat_result_freezes_item_after_threshold(self) -> None:
        state = {"frozen_items": {}, "repeat_tracker": {}}
        batch_items = [
            {
                "db_item_id": 42,
                "item_id": "item-42",
                "status": "partial",
                "confidence": 0.74,
                "model_name": None,
                "extractor_type": "rule",
            }
        ]

        first = update_worker_state_from_batch(
            state=state,
            batch_items=batch_items,
            repeat_threshold=2,
        )
        second = update_worker_state_from_batch(
            state=state,
            batch_items=batch_items,
            repeat_threshold=2,
        )

        self.assertEqual(first, [])
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0]["reason"], FREEZE_REASON_REPEAT_RESULT)
        self.assertIn("42", state["frozen_items"])

    def test_complete_result_clears_repeat_tracker_and_freeze(self) -> None:
        state = {
            "frozen_items": {"42": {"reason": FREEZE_REASON_REPEAT_RESULT}},
            "repeat_tracker": {"42": {"signature": "partial|0.74||rule", "repeat_count": 2}},
        }

        update_worker_state_from_batch(
            state=state,
            batch_items=[
                {
                    "db_item_id": 42,
                    "item_id": "item-42",
                    "status": "complete",
                    "confidence": 0.92,
                    "model_name": "NIKKOR Z 24-70mm f/2.8 S",
                    "extractor_type": "hybrid",
                }
            ],
            repeat_threshold=2,
        )

        self.assertNotIn("42", state["repeat_tracker"])
        self.assertNotIn("42", state["frozen_items"])


if __name__ == "__main__":
    unittest.main()
