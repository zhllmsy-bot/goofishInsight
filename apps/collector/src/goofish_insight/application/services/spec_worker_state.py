from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

FREEZE_REASON_REPEAT_RESULT = "repeat_same_result"



def load_worker_state(*, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"frozen_items": {}, "repeat_tracker": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"frozen_items": {}, "repeat_tracker": {}}
    frozen_items = payload.get("frozen_items")
    repeat_tracker = payload.get("repeat_tracker")
    return {
        "frozen_items": dict(frozen_items or {}),
        "repeat_tracker": dict(repeat_tracker or {}),
    }



def save_worker_state(*, path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "frozen_items": dict(state.get("frozen_items") or {}),
        "repeat_tracker": dict(state.get("repeat_tracker") or {}),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")



def frozen_db_ids_from_state(state: dict[str, Any]) -> set[int]:
    return {int(key) for key in (state.get("frozen_items") or {}).keys()}



def result_signature(entry: dict[str, Any]) -> str | None:
    item_id = entry.get("item_id")
    status = entry.get("status")
    if not item_id or not status:
        return None
    confidence = entry.get("confidence")
    confidence_text = "null" if confidence is None else f"{float(confidence):.2f}"
    model_name = entry.get("model_name") or ""
    extractor_type = entry.get("extractor_type") or ""
    return "|".join((str(status), confidence_text, str(model_name), str(extractor_type)))



def update_worker_state_from_batch(
    *,
    state: dict[str, Any],
    batch_items: list[dict[str, Any]],
    repeat_threshold: int,
) -> list[dict[str, Any]]:
    frozen_events: list[dict[str, Any]] = []
    repeat_tracker = state.setdefault("repeat_tracker", {})
    frozen_items = state.setdefault("frozen_items", {})
    for entry in batch_items:
        db_item_id = entry.get("db_item_id")
        signature = result_signature(entry)
        if db_item_id is None or signature is None:
            continue
        db_item_key = str(db_item_id)
        status = str(entry.get("status") or "")
        if status == "complete":
            repeat_tracker.pop(db_item_key, None)
            frozen_items.pop(db_item_key, None)
            continue
        previous = repeat_tracker.get(db_item_key) or {}
        previous_signature = previous.get("signature")
        repeat_count = int(previous.get("repeat_count") or 0)
        if previous_signature == signature:
            repeat_count += 1
        else:
            repeat_count = 1
        tracker_entry = {
            "signature": signature,
            "repeat_count": repeat_count,
            "updated_at": datetime.now().isoformat(),
        }
        repeat_tracker[db_item_key] = tracker_entry
        if repeat_count >= repeat_threshold:
            frozen_items[db_item_key] = {
                "reason": FREEZE_REASON_REPEAT_RESULT,
                "signature": signature,
                "repeat_count": repeat_count,
                "frozen_at": datetime.now().isoformat(),
                "status": status,
                "item_id": entry.get("item_id"),
            }
            frozen_events.append(
                {
                    "db_item_id": db_item_id,
                    "item_id": entry.get("item_id"),
                    "reason": FREEZE_REASON_REPEAT_RESULT,
                    "repeat_count": repeat_count,
                    "signature": signature,
                }
            )
    return frozen_events
