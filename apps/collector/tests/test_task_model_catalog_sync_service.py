from __future__ import annotations

import unittest

from goofish_insight.application.services.task_model_catalog_sync import (
    SYNC_SOURCE,
    _build_desired_queries,
    sync_category_model_catalog_to_tasks_with_session,
)
from goofish_insight.models import (
    Category,
    CategoryModelAlias,
    CategoryModelCatalog,
    CrawlTask,
    CrawlTaskLexicon,
    CrawlTaskQuery,
)


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
    def __init__(self, *, execute_results=None) -> None:
        self.execute_results = list(execute_results or [])
        self.added = []
        self._id_counter = 401

    def execute(self, stmt):
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeExecuteResult(rows=[])

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is not None:
                continue
            if getattr(obj, "__class__", None).__name__ in {"CrawlTask", "CrawlTaskQuery", "CrawlTaskLexicon"}:
                setattr(obj, "id", self._id_counter)
            else:
                setattr(obj, "id", f"00000000-0000-0000-0000-{self._id_counter:012d}")
            self._id_counter += 1


class TaskModelCatalogSyncServiceTests(unittest.TestCase):
    def test_sync_excludes_cross_category_models_from_search_terms(self) -> None:
        category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple",
            level=2,
            status="ACTIVE",
        )
        watch_model = CategoryModelCatalog(
            id="model-watch",
            category_id="cat-apple",
            brand_name="Apple",
            series_name="Watch",
            model_code="apple_watch_ultra",
            model_name="Apple Watch Ultra 2",
            status="ACTIVE",
        )
        mac_model = CategoryModelCatalog(
            id="model-mac",
            category_id="cat-apple",
            brand_name="Apple",
            series_name="MacBook Pro",
            model_code="macbook_pro_m4",
            model_name="MacBook Pro M4",
            status="ACTIVE",
        )
        mac_model.aliases = [
            CategoryModelAlias(
                id="alias-watch",
                model_id="model-mac",
                alias_text="Apple Watch S10",
                alias_normalized="applewatchs10",
                alias_type="TITLE",
                status="ACTIVE",
            ),
            CategoryModelAlias(
                id="alias-mac",
                model_id="model-mac",
                alias_text="MacBook Pro M4",
                alias_normalized="macbookprom4",
                alias_type="TITLE",
                status="ACTIVE",
            ),
        ]
        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(rows=[watch_model, mac_model]),
                _FakeExecuteResult(rows=[]),
                _FakeExecuteResult(rows=[]),
            ]
        )

        sync_category_model_catalog_to_tasks_with_session(session, category=category)

        created_task = next(obj for obj in session.added if isinstance(obj, CrawlTask))
        self.assertIn("MacBook Pro M4", created_task.keywords)
        self.assertIn("MacBook Pro M4", created_task.model_lexicon)
        self.assertNotIn("Apple Watch Ultra 2", created_task.keywords)
        self.assertNotIn("Apple Watch S10", created_task.model_lexicon)

    def test_sync_creates_auto_managed_task_when_category_has_no_task(self) -> None:
        category = Category(
            id="cat-lens",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="camera/lens",
            level=2,
            status="ACTIVE",
        )
        model = CategoryModelCatalog(
            id="model-1",
            category_id="cat-lens",
            brand_name="Nikon",
            series_name="Z",
            model_code="nikon_z_50_f12_s",
            model_name="NIKKOR Z 50mm f/1.2 S",
            status="ACTIVE",
        )
        alias = CategoryModelAlias(
            id="alias-1",
            model_id="model-1",
            alias_text="尼康 Z50 1.2S",
            alias_normalized="nikonz5012s",
            alias_type="TITLE",
            status="ACTIVE",
        )
        model.aliases = [alias]
        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(rows=[model]),
                _FakeExecuteResult(rows=[]),
                _FakeExecuteResult(rows=[]),
            ]
        )

        result = sync_category_model_catalog_to_tasks_with_session(session, category=category)

        created_task = next(obj for obj in session.added if isinstance(obj, CrawlTask))
        self.assertEqual(result["taskCount"], 1)
        self.assertEqual(result["autoCreatedTaskCount"], 1)
        self.assertEqual(created_task.metadata_json["managedBy"], SYNC_SOURCE)
        self.assertEqual(created_task.keywords, ["尼康 Z 50 1.2"])
        self.assertIn("Nikon", created_task.brand_lexicon)
        self.assertIn("NIKKOR Z 50mm f/1.2 S", created_task.model_lexicon)

    def test_sync_preserves_manual_entries_and_disables_stale_auto_entries(self) -> None:
        category = Category(
            id="cat-lens",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="camera/lens",
            level=2,
            status="ACTIVE",
        )
        model = CategoryModelCatalog(
            id="model-1",
            category_id="cat-lens",
            brand_name="Nikon",
            series_name="Z",
            model_code="nikon_z_50_f12_s",
            model_name="NIKKOR Z 50mm f/1.2 S",
            status="ACTIVE",
        )
        alias = CategoryModelAlias(
            id="alias-1",
            model_id="model-1",
            alias_text="尼康 Z50 1.2S",
            alias_normalized="nikonz5012s",
            alias_type="TITLE",
            status="ACTIVE",
        )
        model.aliases = [alias]

        task = CrawlTask(
            id=21,
            task_key="lens-core",
            source_platform="xianyu",
            category_id="cat-lens",
            business_domain="camera_interchangeable_lens",
            task_type="PRODUCTION",
            display_name="Lens Core",
            keywords=[],
            brand_lexicon=[],
            model_lexicon=[],
            config_lexicon=[],
            paging_limit=3,
            status="active",
            metadata_json={},
        )
        manual_query = CrawlTaskQuery(
            id=501,
            task_id=21,
            query_text="手工限定查询",
            pages=1,
            priority=5,
            status="ACTIVE",
            metadata_json={"source": "manual"},
        )
        stale_auto_query = CrawlTaskQuery(
            id=502,
            task_id=21,
            query_text="old auto",
            pages=1,
            priority=10,
            status="ACTIVE",
            metadata_json={"source": SYNC_SOURCE, "managedBy": SYNC_SOURCE},
        )
        manual_model = CrawlTaskLexicon(
            id=601,
            task_id=21,
            lexicon_type="MODEL",
            term="手工型号",
            priority=5,
            status="ACTIVE",
            metadata_json={"source": "manual"},
        )
        stale_auto_model = CrawlTaskLexicon(
            id=602,
            task_id=21,
            lexicon_type="MODEL",
            term="旧自动型号",
            priority=10,
            status="ACTIVE",
            metadata_json={"source": SYNC_SOURCE, "managedBy": SYNC_SOURCE},
        )
        task.queries = [manual_query, stale_auto_query]
        task.lexicons = [manual_model, stale_auto_model]

        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(rows=[model]),
                _FakeExecuteResult(rows=[task]),
            ]
        )

        result = sync_category_model_catalog_to_tasks_with_session(session, category=category)

        self.assertEqual(result["taskCount"], 1)
        self.assertEqual(manual_query.status, "ACTIVE")
        self.assertEqual(stale_auto_query.status, "DISABLED")
        self.assertEqual(manual_model.status, "ACTIVE")
        self.assertEqual(stale_auto_model.status, "DISABLED")
        self.assertIn("手工限定查询", task.keywords)
        self.assertNotIn("old auto", task.keywords)
        self.assertIn("手工型号", task.model_lexicon)
        self.assertIn("NIKKOR Z 50mm f/1.2 S", task.model_lexicon)
        auto_queries = [
            row.query_text
            for row in list(task.queries or [])
            if isinstance(row, CrawlTaskQuery)
            and str(dict(row.metadata_json or {}).get("managedBy") or "") == SYNC_SOURCE
            and str(row.status or "").upper() == "ACTIVE"
        ]
        self.assertEqual(auto_queries, ["尼康 Z 50 1.2"])

    def test_build_desired_queries_uses_category_profile_templates(self) -> None:
        body_category = Category(
            id="cat-body",
            code="camera_body",
            name="相机机身",
            path="camera/body",
            level=2,
            status="ACTIVE",
        )
        lens_category = Category(
            id="cat-lens",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="camera/lens",
            level=2,
            status="ACTIVE",
        )
        body_model = CategoryModelCatalog(
            id="model-body",
            category_id="cat-body",
            brand_name="Canon",
            series_name="EOS R",
            model_code="canon_eos_r5",
            model_name="Canon EOS R5",
            status="ACTIVE",
        )
        body_model.aliases = [
            CategoryModelAlias(
                id="alias-body",
                model_id="model-body",
                alias_text="佳能 R5 机身",
                alias_normalized="佳能r5机身",
                alias_type="TITLE",
                status="ACTIVE",
            )
        ]
        lens_model = CategoryModelCatalog(
            id="model-lens",
            category_id="cat-lens",
            brand_name="Nikon",
            series_name="NIKKOR Z",
            model_code="nikon_z_24_70_f28_s",
            model_name="NIKKOR Z 24-70mm f/2.8 S",
            status="ACTIVE",
        )
        lens_model.aliases = [
            CategoryModelAlias(
                id="alias-lens",
                model_id="model-lens",
                alias_text="尼康 Z 24-70 2.8 S",
                alias_normalized="尼康z247028s",
                alias_type="TITLE",
                status="ACTIVE",
            )
        ]

        body_queries = _build_desired_queries(category=body_category, models=[body_model])
        lens_queries = _build_desired_queries(category=lens_category, models=[lens_model])

        self.assertEqual(
            [entry["query"] for entry in body_queries],
            [
                "佳能 R5",
            ],
        )
        self.assertEqual(
            [entry["query"] for entry in lens_queries],
            [
                "尼康 Z 24-70 2.8",
            ],
        )

    def test_build_desired_queries_strips_apple_memory_and_storage_specs(self) -> None:
        apple_category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )
        apple_model = CategoryModelCatalog(
            id="model-apple",
            category_id="cat-apple",
            brand_name="Apple",
            series_name="MacBook Pro",
            model_code="mbp_16_m1_max_32g_1024g",
            model_name="MacBook Pro 16 M1 Max 32G 1024G",
            status="ACTIVE",
        )
        apple_model.aliases = [
            CategoryModelAlias(
                id="alias-apple",
                model_id="model-apple",
                alias_text="2021 MacBook Pro 16 M1 Max 32G 1T",
                alias_normalized="2021macbookpro16m1max32g1t",
                alias_type="TITLE",
                status="ACTIVE",
            )
        ]

        apple_queries = _build_desired_queries(category=apple_category, models=[apple_model])

        self.assertEqual(
            [entry["query"] for entry in apple_queries],
            [
                "Apple MacBook Pro 16 M1 Max",
                "MacBook Pro 16 M1 Max",
                "2021 MacBook Pro 16 M1 Max",
            ],
        )

    def test_sync_picks_legacy_task_without_category_id_and_backfills_scope(self) -> None:
        category = Category(
            id="cat-apple",
            code="apple_computer",
            name="Apple电脑",
            path="computers/apple-computer",
            level=2,
            status="ACTIVE",
        )
        model = CategoryModelCatalog(
            id="model-apple",
            category_id="cat-apple",
            brand_name="Apple",
            series_name="MacBook Pro",
            model_code="mbp_14_m4_pro",
            model_name="MacBook Pro 14 M4 Pro",
            status="ACTIVE",
        )
        legacy_task = CrawlTask(
            id=31,
            task_key="apple-core",
            source_platform="xianyu",
            category_id=None,
            business_domain="apple_m_series",
            task_type="PRODUCTION",
            display_name="Apple Core",
            keywords=[],
            brand_lexicon=[],
            model_lexicon=[],
            config_lexicon=[],
            paging_limit=3,
            status="active",
            metadata_json={},
        )
        legacy_task.queries = []
        legacy_task.lexicons = []

        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(rows=[model]),
                _FakeExecuteResult(rows=[legacy_task]),
            ]
        )

        result = sync_category_model_catalog_to_tasks_with_session(session, category=category)

        self.assertEqual(result["taskCount"], 1)
        self.assertEqual(legacy_task.category_id, "cat-apple")
        self.assertEqual(legacy_task.business_domain, "apple_computer")
        self.assertIn("MacBook Pro 14 M4 Pro", legacy_task.model_lexicon)


if __name__ == "__main__":
    unittest.main()
