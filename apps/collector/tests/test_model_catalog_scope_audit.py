from __future__ import annotations

import unittest
from unittest.mock import patch

from goofish_insight.application.services.model_catalog_scope_audit import (
    build_model_catalog_scope_audit,
    cleanup_model_catalog_scope_mismatches,
)
from goofish_insight.models import Category, CategoryModelAlias, CategoryModelCatalog, ProductAttrAuditLog


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
        self.flush_count = 0

    def execute(self, stmt):
        if self.execute_results:
            return self.execute_results.pop(0)
        return _FakeExecuteResult(rows=[])

    def add(self, obj) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        self.flush_count += 1


class ModelCatalogScopeAuditTests(unittest.TestCase):
    def test_build_model_catalog_scope_audit_does_not_flag_valid_camera_body_short_models(self) -> None:
        camera_category = Category(
            id="cat-camera",
            code="camera_body",
            name="相机机身",
            path="camera/body",
            level=2,
            status="ACTIVE",
        )
        z50_model = CategoryModelCatalog(
            id="model-z50",
            category_id="cat-camera",
            brand_name="Nikon",
            series_name="Z",
            model_code="nikon_z50",
            model_name="Nikon Z50",
            status="ACTIVE",
        )
        z50_model.category = camera_category
        z50_model.aliases = [
            CategoryModelAlias(
                id="alias-z50",
                model_id="model-z50",
                alias_text="尼康 Z50 机身",
                alias_normalized="nikonz50body",
                alias_type="TITLE",
                status="ACTIVE",
            )
        ]

        lens_category = Category(
            id="cat-lens",
            code="camera_interchangeable_lens",
            name="可换镜头",
            path="camera/lens",
            level=2,
            status="ACTIVE",
        )
        tamron_model = CategoryModelCatalog(
            id="model-tamron",
            category_id="cat-lens",
            brand_name="Tamron",
            series_name="Di III",
            model_code="tamron_28_75_f28_di_iii_rxd",
            model_name="Tamron 28-75mm F2.8 Di III RXD",
            status="ACTIVE",
        )
        tamron_model.category = lens_category
        tamron_model.aliases = [
            CategoryModelAlias(
                id="alias-tamron",
                model_id="model-tamron",
                alias_text="腾龙 28-75 F2.8 RXD",
                alias_normalized="tamron2875f28rxd",
                alias_type="TITLE",
                status="ACTIVE",
            )
        ]

        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(rows=[z50_model, tamron_model]),
            ]
        )

        detail = build_model_catalog_scope_audit(session)

        self.assertEqual(detail["findingCount"], 0)

    def test_build_model_catalog_scope_audit_reports_model_and_alias_mismatches(self) -> None:
        apple_category = Category(
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
            model_code="apple_watch_ultra_2",
            model_name="Apple Watch Ultra 2",
            status="ACTIVE",
        )
        watch_model.category = apple_category
        watch_model.aliases = []

        mac_model = CategoryModelCatalog(
            id="model-mac",
            category_id="cat-apple",
            brand_name="Apple",
            series_name="MacBook Pro",
            model_code="macbook_pro_m4",
            model_name="MacBook Pro M4",
            status="ACTIVE",
        )
        mac_model.category = apple_category
        bad_alias = CategoryModelAlias(
            id="alias-watch",
            model_id="model-mac",
            alias_text="Apple Watch S10",
            alias_normalized="applewatchs10",
            alias_type="TITLE",
            status="ACTIVE",
        )
        bad_alias.model = mac_model
        good_alias = CategoryModelAlias(
            id="alias-mac",
            model_id="model-mac",
            alias_text="MacBook Pro M4",
            alias_normalized="macbookprom4",
            alias_type="TITLE",
            status="ACTIVE",
        )
        good_alias.model = mac_model
        mac_model.aliases = [bad_alias, good_alias]

        camera_category = Category(
            id="cat-camera",
            code="camera_body",
            name="相机机身",
            path="camera/body",
            level=2,
            status="ACTIVE",
        )
        lens_model = CategoryModelCatalog(
            id="model-lens",
            category_id="cat-camera",
            brand_name="Nikon",
            series_name="Z",
            model_code="nikkor_z_24_70_f28_s",
            model_name="NIKKOR Z 24-70mm f/2.8 S",
            status="ACTIVE",
        )
        lens_model.category = camera_category
        lens_model.aliases = []

        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(rows=[watch_model, mac_model, lens_model]),
            ]
        )

        detail = build_model_catalog_scope_audit(session)

        self.assertEqual(detail["findingCount"], 3)
        self.assertEqual(detail["resourceCounts"], {"alias": 1, "model": 2})
        reasons = {item["reason"] for item in detail["items"]}
        self.assertIn("apple_computer_contains_apple_watch", reasons)
        self.assertIn("camera_body_contains_camera_interchangeable_lens", reasons)

    def test_cleanup_model_catalog_scope_mismatches_inactivates_rows_and_syncs_tasks(self) -> None:
        apple_category = Category(
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
            model_code="apple_watch_ultra_2",
            model_name="Apple Watch Ultra 2",
            status="ACTIVE",
        )
        watch_model.category = apple_category
        watch_model.aliases = []

        mac_model = CategoryModelCatalog(
            id="model-mac",
            category_id="cat-apple",
            brand_name="Apple",
            series_name="MacBook Pro",
            model_code="macbook_pro_m4",
            model_name="MacBook Pro M4",
            status="ACTIVE",
        )
        mac_model.category = apple_category
        bad_alias = CategoryModelAlias(
            id="alias-watch",
            model_id="model-mac",
            alias_text="Apple Watch S10",
            alias_normalized="applewatchs10",
            alias_type="TITLE",
            status="ACTIVE",
        )
        bad_alias.model = mac_model
        good_alias = CategoryModelAlias(
            id="alias-mac",
            model_id="model-mac",
            alias_text="MacBook Pro M4",
            alias_normalized="macbookprom4",
            alias_type="TITLE",
            status="ACTIVE",
        )
        good_alias.model = mac_model
        mac_model.aliases = [bad_alias, good_alias]

        session = _FakeSession(
            execute_results=[
                _FakeExecuteResult(rows=[watch_model, mac_model]),
                _FakeExecuteResult(rows=[watch_model]),
                _FakeExecuteResult(rows=[bad_alias]),
            ]
        )

        with patch(
            "goofish_insight.application.services.model_catalog_scope_audit.sync_category_model_catalog_to_tasks_with_session",
            return_value={"categoryCode": "apple_computer", "queryCount": 1},
        ) as sync_mock:
            detail = cleanup_model_catalog_scope_mismatches(
                session,
                operator_id="ops-bot",
                dry_run=False,
            )

        self.assertEqual(detail["matchedModelCount"], 1)
        self.assertEqual(detail["matchedAliasCount"], 1)
        self.assertEqual(detail["cleanedModelCount"], 1)
        self.assertEqual(detail["cleanedAliasCount"], 1)
        self.assertEqual(detail["syncedCategoryCount"], 1)
        self.assertEqual(watch_model.status, "INACTIVE")
        self.assertEqual(bad_alias.status, "INACTIVE")
        self.assertEqual(good_alias.status, "ACTIVE")
        sync_mock.assert_called_once_with(session, category=apple_category)
        audit_logs = [obj for obj in session.added if isinstance(obj, ProductAttrAuditLog)]
        self.assertEqual(len(audit_logs), 2)
