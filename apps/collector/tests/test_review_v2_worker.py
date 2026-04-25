from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "run_item_llm_review_v2_worker.py"


spec = importlib.util.spec_from_file_location("review_v2_worker", SCRIPT_PATH)
assert spec is not None and spec.loader is not None
review_v2_worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review_v2_worker)


class ReviewV2WorkerTests(unittest.TestCase):
    def test_settle_unresolved_item_ids_quarantines_instead_of_releasing(self) -> None:
        with patch.object(review_v2_worker, "quarantine_item_claims", return_value=["a", "b"]) as mock_quarantine:
            item_ids = review_v2_worker.settle_unresolved_item_ids(
                unresolved_item_ids=["a", "b"],
                worker_name="worker-x",
            )

        self.assertEqual(item_ids, ["a", "b"])
        mock_quarantine.assert_called_once_with(
            item_ids=["a", "b"],
            worker_name="worker-x",
            audit_reason="low_confidence_v2",
        )

    def test_settle_unresolved_item_ids_is_noop_for_empty_list(self) -> None:
        with patch.object(review_v2_worker, "quarantine_item_claims") as mock_quarantine:
            item_ids = review_v2_worker.settle_unresolved_item_ids(
                unresolved_item_ids=[],
                worker_name="worker-x",
            )

        self.assertEqual(item_ids, [])
        mock_quarantine.assert_not_called()


if __name__ == "__main__":
    unittest.main()
