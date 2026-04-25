from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...models import AttributeDefinition


def resolve_attribute_bindings(
    session: Session,
    *,
    items: list[dict[str, Any]],
    error_factory: Callable[[str], Exception],
) -> dict[str, AttributeDefinition]:
    requested_codes = {
        _normalize_optional_string(item.get("attributeCode"))
        for item in list(items or [])
    }
    requested_codes.discard(None)
    requested_ids = {
        _normalize_optional_string(item.get("attributeId"))
        for item in list(items or [])
    }
    requested_ids.discard(None)

    if not requested_codes and not requested_ids:
        return {}

    filters = []
    if requested_codes:
        filters.append(AttributeDefinition.code.in_(sorted(requested_codes)))
    if requested_ids:
        filters.append(AttributeDefinition.id.in_(sorted(requested_ids)))

    rows = list(
        session.execute(
            select(AttributeDefinition).where(or_(*filters))
        ).scalars().all()
    )
    rows_by_id = {str(row.id): row for row in rows}
    rows_by_code: dict[str, list[AttributeDefinition]] = defaultdict(list)
    for row in rows:
        rows_by_code[str(row.code)].append(row)

    resolved: dict[str, AttributeDefinition] = {}
    missing_codes: list[str] = []
    ambiguous_codes: dict[str, list[str]] = {}

    for item in list(items or []):
        attribute_code = _normalize_optional_string(item.get("attributeCode"))
        attribute_id = _normalize_optional_string(item.get("attributeId"))
        if not attribute_code:
            continue
        if attribute_id:
            row = rows_by_id.get(attribute_id)
            if row is None:
                raise error_factory(f"Unknown attributeId: {attribute_id}")
            if str(row.code) != attribute_code:
                raise error_factory(
                    f"attributeId {attribute_id} does not match attributeCode {attribute_code}."
                )
            resolved[attribute_code] = row
            continue

        candidates = rows_by_code.get(attribute_code, [])
        if not candidates:
            missing_codes.append(attribute_code)
            continue
        if len(candidates) > 1:
            ambiguous_codes[attribute_code] = [
                f"{getattr(getattr(row, 'scope_type', None), 'value', getattr(row, 'scope_type', None))}/{getattr(row, 'scope_id', None)}"
                for row in sorted(
                    candidates,
                    key=lambda row: (
                        str(getattr(getattr(row, "scope_type", None), "value", getattr(row, "scope_type", None)) or ""),
                        str(getattr(row, "scope_id", "") or ""),
                        str(getattr(row, "id", "") or ""),
                    ),
                )
            ]
            continue
        resolved[attribute_code] = candidates[0]

    if missing_codes:
        raise error_factory(
            f"Unknown attribute codes: {', '.join(sorted(set(missing_codes)))}"
        )
    if ambiguous_codes:
        details = ", ".join(
            f"{code} ({'; '.join(scopes)})"
            for code, scopes in sorted(ambiguous_codes.items())
        )
        raise error_factory(
            "Ambiguous attribute codes across scopes. Please bind by attributeId or clean duplicated scoped definitions: "
            f"{details}"
        )
    return resolved


def _normalize_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


### 比如在首页，我就是要看到每个品类的 价格相关的信息，以及趋势，目前展示的很垃圾