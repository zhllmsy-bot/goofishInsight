from __future__ import annotations

import re
from typing import Any


def normalize_storage_gb(value: int | None) -> int | None:
    if value is None:
        return None
    mapping = {250: 256, 500: 512, 1000: 1024, 2000: 2048, 4000: 4096, 8000: 8192}
    return mapping.get(value, value)


def normalize_chip_family(
    *,
    chip_family: Any,
    cpu_model: Any,
    model_name: Any,
) -> str | None:
    base = str(chip_family).strip() if chip_family else ""
    cpu_text = str(cpu_model).strip() if cpu_model else ""
    model_text = str(model_name).strip() if model_name else ""
    suffix_source = f"{cpu_text} {model_text}".lower()

    if not base and cpu_text:
        return cpu_text

    if base and re.fullmatch(r"M[1-4]", base, re.IGNORECASE):
        for suffix in ("Ultra", "Max", "Pro"):
            if suffix.lower() in suffix_source:
                return f"{base.upper()} {suffix}"
        return base.upper()

    return base or cpu_text or None
