import unittest
from decimal import Decimal

from goofish_insight.domain.review.contracts import (
    INVALID_FIELD_VALUE,
    normalize_invalid_reason,
    to_storage_value,
    validate_field_value,
)


class ReviewContractTests(unittest.TestCase):
    def test_validate_field_value_enforces_enum(self) -> None:
        self.assertEqual(
            validate_field_value(field_key="spec.display_type", value="amoled"),
            "AMOLED",
        )
        self.assertIs(
            validate_field_value(field_key="spec.display_type", value="lcd"),
            INVALID_FIELD_VALUE,
        )

    def test_validate_field_value_rejects_bad_int(self) -> None:
        self.assertIs(
            validate_field_value(field_key="spec.case_size_mm", value="47mm"),
            INVALID_FIELD_VALUE,
        )
        self.assertEqual(
            validate_field_value(field_key="spec.case_size_mm", value=47),
            47,
        )

    def test_normalize_invalid_reason_and_storage_value(self) -> None:
        self.assertEqual(normalize_invalid_reason("electronic-parts"), "electronic_parts")
        self.assertEqual(normalize_invalid_reason("garbage"), "garbage")
        self.assertEqual(
            to_storage_value(field_key="spec.screen_size_in", value=14.2),
            Decimal("14.2"),
        )


if __name__ == "__main__":
    unittest.main()
