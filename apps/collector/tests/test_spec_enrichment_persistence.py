from __future__ import annotations

import unittest
from contextlib import contextmanager
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from goofish_insight.cli import enrich_single_item, load_items_for_enrichment
from goofish_insight.models import Item
from goofish_insight.specs import SpecEnrichmentCandidate


class _FakeInsertStatement:
    def __init__(self) -> None:
        self.payload: dict[str, object] = {}
        self.conflict_kwargs: dict[str, object] = {}
        self.excluded = SimpleNamespace(
            business_domain="excluded.business_domain",
            category_id="excluded.category_id",
            template_id="excluded.template_id",
            model_catalog_id="excluded.model_catalog_id",
            extractor_type="excluded.extractor_type",
            extractor_version="excluded.extractor_version",
            llm_provider="excluded.llm_provider",
            llm_model="excluded.llm_model",
            status="excluded.status",
            confidence="excluded.confidence",
            needs_review="excluded.needs_review",
            brand="excluded.brand",
            product_line="excluded.product_line",
            model_family="excluded.model_family",
            model_name="excluded.model_name",
            generation="excluded.generation",
            case_size_mm="excluded.case_size_mm",
            is_solar="excluded.is_solar",
            display_type="excluded.display_type",
            screen_size_in="excluded.screen_size_in",
            chip_family="excluded.chip_family",
            cpu_model="excluded.cpu_model",
            cpu_cores="excluded.cpu_cores",
            gpu_cores="excluded.gpu_cores",
            memory_gb="excluded.memory_gb",
            storage_gb="excluded.storage_gb",
            edition_tags="excluded.edition_tags",
            evidence="excluded.evidence",
            extraction_payload="excluded.extraction_payload",
        )

    def values(self, **payload: object) -> _FakeInsertStatement:
        self.payload = dict(payload)
        return self

    def on_conflict_do_update(self, *, constraint: str, set_: dict[str, object]) -> tuple[str, dict[str, object]]:
        self.conflict_kwargs = {"constraint": constraint, "set_": dict(set_)}
        return ("UPSERT", self.conflict_kwargs)


class _FakeSession:
    def __init__(self, item: Item) -> None:
        self.item = item
        self.executed: list[object] = []

    def get(self, model, key):  # noqa: ANN001
        if key == self.item.id:
            return self.item
        return None

    def execute(self, stmt):  # noqa: ANN001
        self.executed.append(stmt)
        return None


class _FakeScalarRows:
    def __init__(self, rows) -> None:
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)

    def all(self):
        return list(self.rows)


class _FakeExecuteResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def scalars(self):
        return _FakeScalarRows(self.rows)

    def all(self):
        normalized = []
        for row in self.rows:
            if isinstance(row, tuple):
                normalized.append(row)
            else:
                normalized.append((row, None))
        return normalized


class _FakeLoadItemsSession:
    def __init__(self, rows) -> None:
        self.rows = rows

    def execute(self, stmt):  # noqa: ANN001
        return _FakeExecuteResult(self.rows)


class SpecEnrichmentPersistenceTests(unittest.TestCase):
    def test_enrich_single_item_updates_catalog_foreign_keys_on_conflict(self) -> None:
        item = Item(
            id=123,
            item_id="lens-item-24-70",
            task_id=1,
            business_domain="camera_interchangeable_lens",
            normalized_model="尼康Z 24-70mm F2.8 S",
        )
        candidate = SpecEnrichmentCandidate(
            category_id="cat-lens",
            template_id="tpl-lens",
            model_catalog_id="model-lens-24-70",
            extractor_type="hybrid",
            status="complete",
            confidence=Decimal("0.99"),
            brand="尼康",
            product_line="NIKKOR Z",
            model_family="NIKKOR Z",
            model_name="NIKKOR Z 24-70mm f/2.8 S",
        )
        session = _FakeSession(item)
        insert_stmt = _FakeInsertStatement()

        @contextmanager
        def fake_session_scope():
            yield session

        with (
            patch("goofish_insight.cli.session_scope", fake_session_scope),
            patch("goofish_insight.cli.extract_item_specs", return_value=candidate),
            patch("goofish_insight.cli.insert", return_value=insert_stmt),
        ):
            result = enrich_single_item(db_item_id=123, allow_llm=True)

        conflict_set = insert_stmt.conflict_kwargs["set_"]
        self.assertEqual(conflict_set["category_id"], "excluded.category_id")
        self.assertEqual(conflict_set["template_id"], "excluded.template_id")
        self.assertEqual(conflict_set["model_catalog_id"], "excluded.model_catalog_id")
        self.assertEqual(item.normalized_model, "NIKKOR Z 24-70mm f/2.8 S")
        self.assertEqual(item.normalized_brand, "尼康")
        self.assertEqual(result["item_id"], "lens-item-24-70")
        self.assertEqual(result["status"], "complete")

    def test_load_items_for_enrichment_skips_lens_body_titles(self) -> None:
        kept_item = Item(
            id=1,
            item_id="lens-real-1",
            task_id=1,
            business_domain="camera_interchangeable_lens",
            title="尼康 Z 24-70 f2.8 S 镜头",
            current_price=Decimal("8888"),
        )
        skipped_item = Item(
            id=2,
            item_id="lens-body-1",
            task_id=1,
            business_domain="camera_interchangeable_lens",
            title="全新尼康Z7二代机身 全画幅高清数码微单",
            current_price=Decimal("9999"),
        )

        @contextmanager
        def fake_session_scope():
            yield _FakeLoadItemsSession([kept_item, skipped_item])

        with patch("goofish_insight.cli.session_scope", fake_session_scope):
            ids = load_items_for_enrichment(
                business_domain="camera_interchangeable_lens",
                item_id=None,
                limit=10,
                force=False,
            )

        self.assertEqual(ids, [1])
