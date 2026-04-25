from __future__ import annotations

import copy
import threading
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_CACHE_LOCK = threading.Lock()
_SECTION_CACHE: dict[tuple[str, tuple[Any, ...]], tuple[float, Any]] = {}


def get_ttl_cached_payload(
    *,
    namespace: str,
    key: tuple[Any, ...],
    ttl_seconds: float,
    builder: Callable[[], T],
) -> T:
    full_key = (namespace, key)
    now = time.monotonic()

    with _CACHE_LOCK:
        cached = _SECTION_CACHE.get(full_key)
        if cached is not None:
            cached_at, cached_value = cached
            if (now - cached_at) <= ttl_seconds:
                return copy.deepcopy(cached_value)

    value = builder()
    cached_value = copy.deepcopy(value)

    with _CACHE_LOCK:
        _SECTION_CACHE[full_key] = (time.monotonic(), cached_value)

    return copy.deepcopy(cached_value)
