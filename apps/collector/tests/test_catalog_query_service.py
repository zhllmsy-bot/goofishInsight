from __future__ import annotations

import unittest
from datetime import datetime

from goofish_insight.application.services.catalog_queries import (
    CatalogQueryError,
    build_catalog_sku_page,
    build_catalog_spu_page,
)
from goofish_insight.compat import UTC
from goofish_insight.models import ProductSku, ProductSpu, ProductStatus


class _FakeExecuteResult:
    def __init__(self, *, scalar_value=None, rows=None) -> None:
        self._scalar_value = scalar_value
        self._rows = rows or []

    def scalar_one(self):
        return self._scalar_value

    def scalars(self):
        return self._rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, *, total: int, rows: list[ProductSpu]) -> None:
        self.total = total
        self.rows = rows
        self.offset_values: list[int | None] = []
        self.limit_values: list[int | None] = []
        self.statement_count = 0

    def execute(self, stmt):
        self.statement_count += 1
        self.offset_values.append(getattr(getattr(stmt, "_offset_clause", None), "value", None))
        self.limit_values.append(getattr(getattr(stmt, "_limit_clause", None), "value", None))
        if self.statement_count == 1:
            return _FakeExecuteResult(scalar_value=self.total)
        return _FakeExecuteResult(rows=self.rows)


class CatalogQueryServiceTests(unittest.TestCase):
    def test_build_catalog_spu_page_returns_summary_rows(self) -> None:
        session = _FakeSession(
            total=3,
            rows=[
                ProductSpu(
                    id="spu-1",
                    category_id="cat-1",
                    template_id="tpl-1",
                    merchant_id="merchant-1",
                    brand_id="brand-1",
                    title="小米 15 Pro",
                    status=ProductStatus.ACTIVE,
                    attr_snapshot_json={
                        "saleAttributeCodes": ["color", "memory_size"],
                        "skus": [{"skuCode": "sku-1"}, {"skuCode": "sku-2"}],
                    },
                    created_at=datetime(2026, 4, 5, 6, 0, tzinfo=UTC),
                    updated_at=datetime(2026, 4, 5, 6, 30, tzinfo=UTC),
                )
            ],
        )

        result = build_catalog_spu_page(
            session,
            page=2,
            page_size=1,
            category_id="cat-1",
            status="active",
        )

        self.assertEqual(result["page"], 2)
        self.assertEqual(result["pageSize"], 1)
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["items"][0]["id"], "spu-1")
        self.assertEqual(result["items"][0]["skuCount"], 2)
        self.assertEqual(result["items"][0]["saleAttributeCodes"], ["color", "memory_size"])
        self.assertEqual(session.offset_values[-1], 1)
        self.assertEqual(session.limit_values[-1], 1)

    def test_build_catalog_spu_page_rejects_invalid_status(self) -> None:
        session = _FakeSession(total=0, rows=[])

        with self.assertRaises(CatalogQueryError):
            build_catalog_spu_page(
                session,
                status="UNKNOWN",
            )

    def test_build_catalog_spu_page_clamps_page_size(self) -> None:
        session = _FakeSession(total=0, rows=[])

        result = build_catalog_spu_page(
            session,
            page=1,
            page_size=500,
        )

        self.assertEqual(result["pageSize"], 100)
        self.assertEqual(session.limit_values[-1], 100)

    def test_build_catalog_sku_page_returns_summary_rows(self) -> None:
        spu = ProductSpu(
            id="spu-1",
            category_id="cat-1",
            template_id="tpl-3",
            merchant_id="merchant-1",
            brand_id="brand-1",
            title="小米 15 Pro",
            status=ProductStatus.ACTIVE,
            attr_snapshot_json={},
            created_at=datetime(2026, 4, 5, 6, 0, tzinfo=UTC),
            updated_at=datetime(2026, 4, 5, 6, 30, tzinfo=UTC),
        )
        sku = ProductSku(
            id="sku-1",
            spu_id="spu-1",
            sku_code="MI15P-BLK-12G",
            sales_signature_raw="raw-1",
            sales_signature_hash="hash-1",
            price=4999,
            stock=50,
            barcode="690000000011",
            status=ProductStatus.ACTIVE,
            attr_snapshot_json={
                "saleAttributes": [
                    {"attributeCode": "color"},
                    {"attributeCode": "memory_size"},
                ]
            },
            created_at=datetime(2026, 4, 5, 6, 10, tzinfo=UTC),
            updated_at=datetime(2026, 4, 5, 6, 40, tzinfo=UTC),
        )
        session = _FakeSession(total=2, rows=[(sku, spu)])

        result = build_catalog_sku_page(
            session,
            page=1,
            page_size=20,
            template_id="tpl-3",
            status="ACTIVE",
        )

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["items"][0]["id"], "sku-1")
        self.assertEqual(result["items"][0]["templateId"], "tpl-3")
        self.assertEqual(result["items"][0]["saleAttributeCodes"], ["color", "memory_size"])

    def test_build_catalog_sku_page_rejects_invalid_status(self) -> None:
        session = _FakeSession(total=0, rows=[])

        with self.assertRaises(CatalogQueryError):
            build_catalog_sku_page(
                session,
                status="BROKEN",
            )


if __name__ == "__main__":
    unittest.main()
