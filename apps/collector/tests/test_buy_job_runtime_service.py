from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from goofish_insight.application.services.buy_job_runtime import (
    BUY_JOB_ENRICH_SPECS,
    process_buy_job_events_with_session,
    schedule_buy_baseline_job_with_session,
)
from goofish_insight.compat import UTC
from goofish_insight.models import OutboxEvent, OutboxStatus


class _FakeExecuteResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, *, events=None) -> None:
        self.events = list(events or [])
        self.added: list[object] = []
        self.flush_count = 0

    def execute(self, stmt):
        statement_text = str(stmt)
        if "FROM outbox_event" in statement_text:
            return _FakeExecuteResult(self.events)
        raise AssertionError(f"Unexpected statement: {statement_text}")

    def add(self, obj) -> None:
        self.added.append(obj)
        if isinstance(obj, OutboxEvent):
            self.events.append(obj)

    def flush(self) -> None:
        self.flush_count += 1


class BuyJobRuntimeServiceTests(unittest.TestCase):
    def test_schedule_buy_baseline_job_dedupes_existing_pending_event(self) -> None:
        existing = OutboxEvent(
            id="event-1",
            event_type="buy.build_baseline",
            aggregate_type="buy_job",
            aggregate_id="11111111-1111-1111-1111-111111111111",
            payload={"dedupeKey": "scope=apple_computer|view=all|freshness=30|min_samples=4"},
            status=OutboxStatus.FAILED,
            retry_count=2,
        )
        existing.created_at = datetime.now(UTC)
        existing.updated_at = datetime.now(UTC)
        session = _FakeSession(events=[existing])

        result = schedule_buy_baseline_job_with_session(
            session,
            category_code="apple_computer",
            view="all",
            freshness_days=30,
            min_sample_points=4,
            debounce_minutes=10,
            requested_by="test",
        )

        self.assertFalse(result["queued"])
        self.assertTrue(result["deduped"])
        self.assertEqual(existing.status, OutboxStatus.PENDING)
        self.assertEqual(existing.payload["requestedBy"], "test")

    def test_process_buy_job_events_runs_enrich_job_and_schedules_followup(self) -> None:
        event = OutboxEvent(
            id="event-2",
            event_type=BUY_JOB_ENRICH_SPECS,
            aggregate_type="buy_job",
            aggregate_id="22222222-2222-2222-2222-222222222222",
            payload={
                "businessDomain": "apple_computer",
                "limit": 10,
                "force": False,
                "allowLlm": True,
                "followupDebounceMinutes": 10,
            },
            status=OutboxStatus.PENDING,
            next_retry_at=datetime.now(UTC),
        )
        session = _FakeSession(events=[event])

        with (
            patch(
                "goofish_insight.application.services.buy_job_runtime.run_spec_enrichment_batch_with_session",
                return_value={"processed": 2, "items": []},
            ),
            patch(
                "goofish_insight.application.services.buy_job_runtime.schedule_buy_baseline_job_with_session",
                return_value={"eventId": "followup-1"},
            ) as followup_mock,
        ):
            result = process_buy_job_events_with_session(session, limit=10, dry_run=True)

        self.assertEqual(result["processedCount"], 1)
        self.assertEqual(result["failedCount"], 0)
        self.assertEqual(event.status, OutboxStatus.DONE)
        followup_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
