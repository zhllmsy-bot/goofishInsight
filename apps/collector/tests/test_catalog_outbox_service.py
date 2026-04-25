from __future__ import annotations

import unittest
from datetime import datetime
from unittest.mock import patch

from goofish_insight.application.services.catalog_outbox import (
    build_catalog_outbox_rows,
    process_catalog_outbox_events_with_session,
)
from goofish_insight.models import OutboxEvent, OutboxStatus, ProductSpu, ProductStatus


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    def __init__(self, events: list[OutboxEvent], spus: dict[str, ProductSpu]) -> None:
        self.events = events
        self.spus = spus
        self.flush_count = 0

    def execute(self, stmt):
        return _FakeScalarResult(self.events)

    def get(self, model, key: str):
        if model is ProductSpu:
            return self.spus.get(key)
        return None

    def flush(self) -> None:
        self.flush_count += 1


class CatalogOutboxServiceTests(unittest.TestCase):
    def test_process_catalog_outbox_events_marks_event_done(self) -> None:
        spu = ProductSpu(
            id="spu-1",
            category_id="cat-1",
            template_id="tpl-1",
            title="小米 15",
            status=ProductStatus.ACTIVE,
            attr_snapshot_json={"spuId": "spu-1", "skus": [{"skuCode": "sku-1"}]},
        )
        event = OutboxEvent(
            id="evt-1",
            event_type="catalog.product_spu_changed",
            aggregate_type="product_spu",
            aggregate_id="spu-1",
            event_version=1,
            payload={},
            status=OutboxStatus.PENDING,
            retry_count=0,
        )
        session = _FakeSession([event], {"spu-1": spu})

        with patch(
            "goofish_insight.application.services.catalog_outbox.build_catalog_spu_detail",
            return_value={
                "spu": {"id": "spu-1", "attrSnapshotJson": {"spuId": "spu-1", "skus": [{"skuCode": "sku-1"}]}},
                "skus": [{"id": "sku-1"}],
            },
        ):
            result = process_catalog_outbox_events_with_session(session, limit=10, dry_run=False)

        self.assertEqual(result["processedCount"], 1)
        self.assertEqual(event.status, OutboxStatus.DONE)
        self.assertEqual(event.retry_count, 0)
        self.assertIn("_consumer", event.payload)
        self.assertGreaterEqual(session.flush_count, 2)

    def test_process_catalog_outbox_events_marks_failure_and_retry(self) -> None:
        event = OutboxEvent(
            id="evt-2",
            event_type="catalog.product_spu_changed",
            aggregate_type="product_spu",
            aggregate_id="missing-spu",
            event_version=1,
            payload={},
            status=OutboxStatus.PENDING,
            retry_count=0,
        )
        session = _FakeSession([event], {})

        result = process_catalog_outbox_events_with_session(session, limit=10, dry_run=False)

        self.assertEqual(result["failedCount"], 1)
        self.assertEqual(event.status, OutboxStatus.FAILED)
        self.assertEqual(event.retry_count, 1)
        self.assertIsNotNone(event.next_retry_at)
        self.assertIn("SPU not found", event.last_error)

    def test_build_catalog_outbox_rows_serializes_events(self) -> None:
        event = OutboxEvent(
            id="evt-3",
            event_type="catalog.product_spu_changed",
            aggregate_type="product_spu",
            aggregate_id="spu-3",
            event_version=1,
            payload={},
            status=OutboxStatus.PENDING,
            retry_count=2,
        )
        event.created_at = datetime(2026, 4, 5, 6, 45, 0)
        event.updated_at = datetime(2026, 4, 5, 6, 46, 0)
        session = _FakeSession([event], {})

        rows = build_catalog_outbox_rows(session, limit=5)

        self.assertEqual(rows[0]["id"], "evt-3")
        self.assertEqual(rows[0]["status"], "PENDING")
        self.assertEqual(rows[0]["retryCount"], 2)


if __name__ == "__main__":
    unittest.main()
