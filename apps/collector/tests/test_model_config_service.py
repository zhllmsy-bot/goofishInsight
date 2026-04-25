from __future__ import annotations

import unittest
from unittest.mock import patch

from goofish_insight.application.services.model_config import (
    list_model_configs_with_session,
    normalize_model_alias,
    upsert_model_config_with_session,
)
from goofish_insight.models import Category, CategoryModelCatalog, ProductAttrAuditLog


class _FakeScalarRows:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeExecuteResult:
    def __init__(self, rows=None) -> None:
        self._rows = rows or []

    def scalars(self):
        return _FakeScalarRows(self._rows)


class _FakeSession:
    def __init__(self, *, execute_results=None, categories=None, models=None) -> None:
        self.execute_results = list(execute_results or [])
        self.categories = categories or {}
        self.models = models or {}
        self.added = []
        self.deleted = []
        self._id_counter = 997

    def execute(self, stmt):
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeExecuteResult(rows=[])

    def get(self, model, key):
        if getattr(model, "__name__", "") == "Category":
            return self.categories.get(key)
        if getattr(model, "__name__", "") == "CategoryModelCatalog":
            return self.models.get(key)
        return None

    def add(self, obj) -> None:
        self.added.append(obj)

    def delete(self, obj) -> None:
        self.deleted.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                setattr(obj, "id", f"00000000-0000-0000-0000-{self._id_counter:012d}")
                self._id_counter += 1
            if getattr(obj, "__class__", None).__name__ == "CategoryModelCatalog":
                self.models[obj.id] = obj

    def rollback(self) -> None:
        return None


class ModelConfigServiceTests(unittest.TestCase):
    def test_normalize_model_alias_collapses_noise(self) -> None:
        self.assertEqual(normalize_model_alias(" Nikon Z 50/1.2 S "), "nikonz5012s")

    def test_list_model_configs_with_session_returns_rows(self) -> None:
        row = CategoryModelCatalog(
            id="model-1",
            category_id="cat-lens",
            brand_name="Nikon",
            series_name="Z",
            model_code="nikon_z_50_f12_s",
            model_name="NIKKOR Z 50mm f/1.2 S",
            status="ACTIVE",
        )
        session = _FakeSession(execute_results=[_FakeExecuteResult(rows=[row])])

        result = list_model_configs_with_session(session)

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["modelCode"], "nikon_z_50_f12_s")

    def test_upsert_model_config_with_session_creates_row(self) -> None:
        category = Category(
            id="cat-lens",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="camera/lens",
            level=2,
            status="ACTIVE",
        )
        session = _FakeSession(
            execute_results=[_FakeExecuteResult(rows=[]), _FakeExecuteResult(rows=[])],
            categories={"cat-lens": category},
        )

        with patch(
            "goofish_insight.application.services.model_config.sync_category_model_catalog_to_tasks_with_session",
            return_value={"taskCount": 1, "queryCount": 3, "brandLexiconCount": 1, "modelLexiconCount": 2},
        ):
            result = upsert_model_config_with_session(
                session,
                payload={
                    "categoryId": "cat-lens",
                    "brandName": "Nikon",
                    "seriesName": "Z",
                    "modelCode": "nikon_z_50_f12_s",
                    "modelName": "NIKKOR Z 50mm f/1.2 S",
                    "aliases": [
                        {"aliasText": "尼康 Z50 1.2S", "aliasType": "TITLE"},
                        {"aliasText": "Z 50 1.2 S", "aliasType": "TITLE"},
                    ],
                },
                operator_id="ops-bot",
                dry_run=False,
            )

        self.assertEqual(result["model"]["brandName"], "Nikon")
        self.assertEqual(result["model"]["aliasCount"], 2)
        self.assertEqual(result["sync"]["queryCount"], 3)
        self.assertTrue(any(isinstance(obj, ProductAttrAuditLog) for obj in session.added))


if __name__ == "__main__":
    unittest.main()
