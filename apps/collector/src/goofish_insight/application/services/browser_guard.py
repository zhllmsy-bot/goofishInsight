from __future__ import annotations

import json
import shlex
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select

from ...db import session_scope
from ...models import BrowserSession
from .browser_guard_analytics import persist_browser_guard_event
from .collector_browser import infer_auth_state_from_error_message

DEFAULT_BROWSER_GUARD_STATE_PATH = Path("reports/runtime/browser_guard_state.json")
DEFAULT_BROWSER_GUARD_EVENT_LOG_PATH = Path("reports/runtime/browser_guard_events.jsonl")
DEFAULT_BROWSER_GUARD_BASE_SECONDS = 600
DEFAULT_BROWSER_GUARD_MAX_SECONDS = 21600
MANUAL_INTERVENTION_AUTH_STATES = {"login_required"}
COOLDOWN_AUTH_STATES = {"risk_control"}


def default_browser_guard_state_path() -> Path:
    return DEFAULT_BROWSER_GUARD_STATE_PATH


def default_browser_guard_event_log_path() -> Path:
    return DEFAULT_BROWSER_GUARD_EVENT_LOG_PATH


def _normalize_auth_state(value: str | None) -> str | None:
    resolved = str(value or "").strip().lower()
    return resolved or None


def _parse_iso_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _normalize_guard_entry(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "auth_state": _normalize_auth_state(value.get("auth_state")),
        "consecutive_hits": max(int(value.get("consecutive_hits") or 0), 0),
        "cooldown_started_at": _serialize_datetime(_parse_iso_datetime(value.get("cooldown_started_at"))),
        "next_retry_at": _serialize_datetime(_parse_iso_datetime(value.get("next_retry_at"))),
        "last_error": str(value.get("last_error") or "").strip() or None,
        "last_feature": str(value.get("last_feature") or "").strip() or None,
        "last_scope_key": str(value.get("last_scope_key") or "").strip() or None,
        "last_event_at": _serialize_datetime(_parse_iso_datetime(value.get("last_event_at"))),
        "last_success_at": _serialize_datetime(_parse_iso_datetime(value.get("last_success_at"))),
        "updated_at": _serialize_datetime(_parse_iso_datetime(value.get("updated_at"))),
    }


def load_browser_guard_state(path: Path | None = None) -> dict[str, Any]:
    resolved_path = Path(path or default_browser_guard_state_path())
    if not resolved_path.exists():
        return {"profiles": {}, "scopes": {}, "updated_at": None}
    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"profiles": {}, "scopes": {}, "updated_at": None}

    profiles_payload = payload.get("profiles")
    scopes_payload = payload.get("scopes")
    profiles = {
        str(key): normalized
        for key, value in (profiles_payload.items() if isinstance(profiles_payload, dict) else [])
        if (normalized := _normalize_guard_entry(value)) is not None
    }
    scopes = {
        str(key): normalized
        for key, value in (scopes_payload.items() if isinstance(scopes_payload, dict) else [])
        if (normalized := _normalize_guard_entry(value)) is not None
    }
    return {
        "profiles": profiles,
        "scopes": scopes,
        "updated_at": _serialize_datetime(_parse_iso_datetime(payload.get("updated_at"))),
    }


def save_browser_guard_state(payload: dict[str, Any], path: Path | None = None) -> None:
    resolved_path = Path(path or default_browser_guard_state_path())
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_payload = {
        "profiles": {
            str(key): normalized
            for key, value in (payload.get("profiles") or {}).items()
            if (normalized := _normalize_guard_entry(value)) is not None
        },
        "scopes": {
            str(key): normalized
            for key, value in (payload.get("scopes") or {}).items()
            if (normalized := _normalize_guard_entry(value)) is not None
        },
        "updated_at": _serialize_datetime(_parse_iso_datetime(payload.get("updated_at"))),
    }
    resolved_path.write_text(
        json.dumps(normalized_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def build_browser_guard_scope_id(*, profile_key: str, feature: str, scope_key: str | None = None) -> str:
    resolved_profile = str(profile_key or "").strip() or "default"
    resolved_feature = str(feature or "").strip() or "unknown"
    resolved_scope = str(scope_key or "").strip() or "*"
    return f"{resolved_profile}|{resolved_feature}|{resolved_scope}"


def compute_browser_guard_cooldown_seconds(
    *,
    consecutive_hits: int,
    base_seconds: int = DEFAULT_BROWSER_GUARD_BASE_SECONDS,
    max_seconds: int = DEFAULT_BROWSER_GUARD_MAX_SECONDS,
) -> int:
    resolved_base = max(int(base_seconds), 1)
    resolved_max = max(int(max_seconds), resolved_base)
    exponent = max(int(consecutive_hits) - 1, 0)
    wait_seconds = resolved_base * (2**exponent)
    return min(wait_seconds, resolved_max)


def _append_guard_event(payload: dict[str, Any], path: Path | None = None) -> None:
    resolved_path = Path(path or default_browser_guard_event_log_path())
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_browser_session_snapshot(*, profile_key: str) -> dict[str, Any] | None:
    try:
        with session_scope() as session:
            row = session.execute(
                select(BrowserSession)
                .where(BrowserSession.profile_key == profile_key)
                .limit(1)
            ).scalar_one_or_none()
    except Exception:
        return None

    if row is None:
        return None

    return {
        "profile_key": row.profile_key,
        "auth_state": row.auth_state,
        "last_login_required_at": _serialize_datetime(row.last_login_required_at),
        "last_authenticated_at": _serialize_datetime(row.last_authenticated_at),
        "last_error": row.last_error,
        "updated_at": _serialize_datetime(row.updated_at),
    }


def _build_preflight_decision(
    *,
    allowed: bool,
    decision: str,
    profile_key: str,
    feature: str,
    scope_key: str | None,
    auth_state: str | None,
    source: str,
    reason: str,
    wait_seconds: int = 0,
    recommended_sleep_seconds: int = 0,
    next_retry_at: str | None = None,
    cooldown_started_at: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "allowed": bool(allowed),
        "decision": decision,
        "profile_key": profile_key,
        "feature": feature,
        "scope_key": scope_key,
        "auth_state": auth_state,
        "source": source,
        "reason": reason,
        "wait_seconds": max(int(wait_seconds or 0), 0),
        "recommended_sleep_seconds": max(int(recommended_sleep_seconds or 0), 0),
        "next_retry_at": next_retry_at,
        "cooldown_started_at": cooldown_started_at,
        "error_message": error_message,
    }


def evaluate_browser_guard_preflight(
    *,
    profile_key: str,
    feature: str,
    scope_key: str | None = None,
    state_path: Path | None = None,
    now: datetime | None = None,
    browser_session: dict[str, Any] | None = None,
    base_seconds: int = DEFAULT_BROWSER_GUARD_BASE_SECONDS,
) -> dict[str, Any]:
    resolved_now = now or datetime.now(UTC)
    state = load_browser_guard_state(state_path)
    profiles = state.get("profiles") or {}
    scopes = state.get("scopes") or {}

    profile_entry = _normalize_guard_entry(profiles.get(profile_key))
    if profile_entry is not None and profile_entry.get("auth_state") in MANUAL_INTERVENTION_AUTH_STATES:
        return _build_preflight_decision(
            allowed=False,
            decision="manual_intervention_required",
            profile_key=profile_key,
            feature=feature,
            scope_key=scope_key,
            auth_state=profile_entry.get("auth_state"),
            source="guard_state_profile",
            reason="profile_manual_intervention_required",
            recommended_sleep_seconds=60,
            error_message=profile_entry.get("last_error"),
            cooldown_started_at=profile_entry.get("cooldown_started_at"),
        )

    if profile_entry is not None:
        next_retry_at = _parse_iso_datetime(profile_entry.get("next_retry_at"))
        if next_retry_at is not None and next_retry_at > resolved_now:
            wait_seconds = max(int((next_retry_at - resolved_now).total_seconds()), 1)
            return _build_preflight_decision(
                allowed=False,
                decision="cooldown",
                profile_key=profile_key,
                feature=feature,
                scope_key=scope_key,
                auth_state=profile_entry.get("auth_state"),
                source="guard_state_profile",
                reason="profile_cooldown_active",
                wait_seconds=wait_seconds,
                recommended_sleep_seconds=wait_seconds,
                next_retry_at=next_retry_at.isoformat(),
                cooldown_started_at=profile_entry.get("cooldown_started_at"),
                error_message=profile_entry.get("last_error"),
            )

    scope_entry = _normalize_guard_entry(scopes.get(build_browser_guard_scope_id(
        profile_key=profile_key,
        feature=feature,
        scope_key=scope_key,
    )))
    if scope_entry is not None:
        next_retry_at = _parse_iso_datetime(scope_entry.get("next_retry_at"))
        if next_retry_at is not None and next_retry_at > resolved_now:
            wait_seconds = max(int((next_retry_at - resolved_now).total_seconds()), 1)
            return _build_preflight_decision(
                allowed=False,
                decision="cooldown",
                profile_key=profile_key,
                feature=feature,
                scope_key=scope_key,
                auth_state=scope_entry.get("auth_state"),
                source="guard_state_scope",
                reason="scope_cooldown_active",
                wait_seconds=wait_seconds,
                recommended_sleep_seconds=wait_seconds,
                next_retry_at=next_retry_at.isoformat(),
                cooldown_started_at=scope_entry.get("cooldown_started_at"),
                error_message=scope_entry.get("last_error"),
            )

    snapshot = browser_session if browser_session is not None else load_browser_session_snapshot(profile_key=profile_key)
    if isinstance(snapshot, dict):
        auth_state = _normalize_auth_state(snapshot.get("auth_state"))
        last_error = str(snapshot.get("last_error") or "").strip() or None
        if auth_state == "login_required":
            last_login_required_at = _parse_iso_datetime(snapshot.get("last_login_required_at"))
            last_authenticated_at = _parse_iso_datetime(snapshot.get("last_authenticated_at"))
            if last_login_required_at is None or last_authenticated_at is None or last_login_required_at >= last_authenticated_at:
                return _build_preflight_decision(
                    allowed=False,
                    decision="manual_intervention_required",
                    profile_key=profile_key,
                    feature=feature,
                    scope_key=scope_key,
                    auth_state=auth_state,
                    source="browser_session",
                    reason="browser_session_login_required",
                    recommended_sleep_seconds=60,
                    error_message=last_error,
                )
        if auth_state == "risk_control":
            updated_at = _parse_iso_datetime(snapshot.get("updated_at"))
            if updated_at is not None:
                next_retry_at = updated_at + timedelta(seconds=max(int(base_seconds), 1))
                if next_retry_at > resolved_now:
                    wait_seconds = max(int((next_retry_at - resolved_now).total_seconds()), 1)
                    return _build_preflight_decision(
                        allowed=False,
                        decision="cooldown",
                        profile_key=profile_key,
                        feature=feature,
                        scope_key=scope_key,
                        auth_state=auth_state,
                        source="browser_session",
                        reason="browser_session_risk_control",
                        wait_seconds=wait_seconds,
                        recommended_sleep_seconds=wait_seconds,
                        next_retry_at=next_retry_at.isoformat(),
                        cooldown_started_at=_serialize_datetime(updated_at),
                        error_message=last_error,
                    )

    return _build_preflight_decision(
        allowed=True,
        decision="run",
        profile_key=profile_key,
        feature=feature,
        scope_key=scope_key,
        auth_state="authenticated",
        source="browser_guard",
        reason="ready",
    )


def format_browser_guard_preflight_message(decision: dict[str, Any]) -> str:
    feature = str(decision.get("feature") or "unknown")
    profile_key = str(decision.get("profile_key") or "default")
    auth_state = str(decision.get("auth_state") or "unknown")
    if bool(decision.get("allowed")):
        return f"Browser guard ready for {feature} on profile {profile_key}."
    decision_type = str(decision.get("decision") or "").strip().lower()
    if decision_type == "browser_unavailable":
        cdp_url = str(decision.get("cdp_url") or "").strip()
        if str(decision.get("reason") or "") == "cdp_url_missing":
            return f"Browser guard blocked {feature} on profile {profile_key}: attached browser CDP URL is not configured."
        if cdp_url:
            return f"Browser guard blocked {feature} on profile {profile_key}: attached browser unavailable at {cdp_url}."
        return f"Browser guard blocked {feature} on profile {profile_key}: attached browser unavailable."
    if str(decision.get("decision") or "") == "manual_intervention_required":
        return (
            f"Browser guard blocked {feature} on profile {profile_key}: "
            f"{auth_state} requires manual intervention."
        )
    wait_seconds = max(int(decision.get("wait_seconds") or 0), 0)
    next_retry_at = str(decision.get("next_retry_at") or "").strip()
    if next_retry_at:
        return (
            f"Browser guard blocked {feature} on profile {profile_key}: "
            f"{auth_state} cooldown {wait_seconds}s remaining until {next_retry_at}."
        )
    return f"Browser guard blocked {feature} on profile {profile_key}: {auth_state} cooldown active."


def build_browser_guard_metadata(decision: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(decision, dict):
        return {}
    metadata = {
        "browser_guard_allowed": bool(decision.get("allowed")),
        "browser_guard_decision": str(decision.get("decision") or "").strip() or None,
        "browser_guard_auth_state": str(decision.get("auth_state") or "").strip() or None,
        "browser_guard_source": str(decision.get("source") or "").strip() or None,
        "browser_guard_reason": str(decision.get("reason") or "").strip() or None,
        "browser_guard_wait_seconds": max(int(decision.get("wait_seconds") or 0), 0),
        "browser_guard_recommended_sleep_seconds": max(
            int(decision.get("recommended_sleep_seconds") or 0),
            0,
        ),
        "browser_guard_next_retry_at": str(decision.get("next_retry_at") or "").strip() or None,
        "browser_guard_cooldown_started_at": str(decision.get("cooldown_started_at") or "").strip() or None,
        "browser_guard_error_message": str(decision.get("error_message") or "").strip() or None,
        "browser_guard_cdp_url": str(decision.get("cdp_url") or "").strip() or None,
    }
    return {key: value for key, value in metadata.items() if value is not None}


def render_browser_guard_shell_exports(decision: dict[str, Any]) -> str:
    payload = {
        "GUARD_ALLOWED": "1" if bool(decision.get("allowed")) else "0",
        "GUARD_DECISION": str(decision.get("decision") or ""),
        "GUARD_PROFILE_KEY": str(decision.get("profile_key") or ""),
        "GUARD_FEATURE": str(decision.get("feature") or ""),
        "GUARD_SCOPE_KEY": str(decision.get("scope_key") or ""),
        "GUARD_AUTH_STATE": str(decision.get("auth_state") or ""),
        "GUARD_SOURCE": str(decision.get("source") or ""),
        "GUARD_REASON": str(decision.get("reason") or ""),
        "GUARD_WAIT_SECONDS": str(max(int(decision.get("wait_seconds") or 0), 0)),
        "GUARD_RECOMMENDED_SLEEP_SECONDS": str(
            max(int(decision.get("recommended_sleep_seconds") or 0), 0)
        ),
        "GUARD_NEXT_RETRY_AT": str(decision.get("next_retry_at") or ""),
        "GUARD_COOLDOWN_STARTED_AT": str(decision.get("cooldown_started_at") or ""),
        "GUARD_ERROR_MESSAGE": str(decision.get("error_message") or ""),
        "GUARD_CDP_URL": str(decision.get("cdp_url") or ""),
        "GUARD_MESSAGE": format_browser_guard_preflight_message(decision),
    }
    return "\n".join(
        f"{key}={shlex.quote(value)}"
        for key, value in payload.items()
    )


def record_browser_guard_observation(
    *,
    profile_key: str,
    feature: str,
    auth_state: str | None = None,
    error_message: str | None = None,
    scope_key: str | None = None,
    keep_page_open: bool | None = None,
    state_path: Path | None = None,
    event_log_path: Path | None = None,
    now: datetime | None = None,
    base_seconds: int = DEFAULT_BROWSER_GUARD_BASE_SECONDS,
    max_seconds: int = DEFAULT_BROWSER_GUARD_MAX_SECONDS,
) -> dict[str, Any]:
    resolved_auth_state = _normalize_auth_state(auth_state) or infer_auth_state_from_error_message(error_message)
    if resolved_auth_state not in {"authenticated", *MANUAL_INTERVENTION_AUTH_STATES, *COOLDOWN_AUTH_STATES}:
        return {}

    resolved_now = now or datetime.now(UTC)
    state = load_browser_guard_state(state_path)
    profiles = state.setdefault("profiles", {})
    scopes = state.setdefault("scopes", {})
    profile_entry = _normalize_guard_entry(profiles.get(profile_key)) or {}
    scope_id = build_browser_guard_scope_id(
        profile_key=profile_key,
        feature=feature,
        scope_key=scope_key,
    )
    scope_entry = _normalize_guard_entry(scopes.get(scope_id)) or {}

    if resolved_auth_state == "authenticated":
        had_guard_state = (
            _normalize_auth_state(profile_entry.get("auth_state")) in {
                *MANUAL_INTERVENTION_AUTH_STATES,
                *COOLDOWN_AUTH_STATES,
            }
            or max(int(profile_entry.get("consecutive_hits") or 0), 0) > 0
            or _normalize_auth_state(scope_entry.get("auth_state")) in {
                *MANUAL_INTERVENTION_AUTH_STATES,
                *COOLDOWN_AUTH_STATES,
            }
            or max(int(scope_entry.get("consecutive_hits") or 0), 0) > 0
        )
        profile_entry.update(
            {
                "auth_state": "authenticated",
                "consecutive_hits": 0,
                "cooldown_started_at": None,
                "next_retry_at": None,
                "last_error": None,
                "last_feature": feature,
                "last_scope_key": scope_key,
                "last_event_at": profile_entry.get("last_event_at"),
                "last_success_at": resolved_now.isoformat(),
                "updated_at": resolved_now.isoformat(),
            }
        )
        profiles[profile_key] = profile_entry
        if scope_key is not None:
            scope_entry.update(
                {
                    "auth_state": "authenticated",
                    "consecutive_hits": 0,
                    "cooldown_started_at": None,
                    "next_retry_at": None,
                    "last_error": None,
                    "last_feature": feature,
                    "last_scope_key": scope_key,
                    "last_event_at": scope_entry.get("last_event_at"),
                    "last_success_at": resolved_now.isoformat(),
                    "updated_at": resolved_now.isoformat(),
                }
            )
            scopes[scope_id] = scope_entry
        state["updated_at"] = resolved_now.isoformat()
        save_browser_guard_state(state, state_path)
        if had_guard_state:
            persist_browser_guard_event(
                profile_key=profile_key,
                feature=feature,
                scope_key=scope_key,
                event_type="recovered",
                auth_state="authenticated",
                consecutive_hits=0,
                keep_page_open=keep_page_open,
                occurred_at=resolved_now,
            )
        return _build_preflight_decision(
            allowed=True,
            decision="run",
            profile_key=profile_key,
            feature=feature,
            scope_key=scope_key,
            auth_state="authenticated",
            source="browser_guard",
            reason="authenticated",
        )

    if resolved_auth_state in MANUAL_INTERVENTION_AUTH_STATES:
        entry_payload = {
            "auth_state": resolved_auth_state,
            "consecutive_hits": 0,
            "cooldown_started_at": resolved_now.isoformat(),
            "next_retry_at": None,
            "last_error": str(error_message or "").strip() or None,
            "last_feature": feature,
            "last_scope_key": scope_key,
            "last_event_at": resolved_now.isoformat(),
            "last_success_at": profile_entry.get("last_success_at"),
            "updated_at": resolved_now.isoformat(),
        }
        profile_entry.update(entry_payload)
        profiles[profile_key] = profile_entry
        if scope_key is not None:
            scope_entry.update(entry_payload)
            scopes[scope_id] = scope_entry
        state["updated_at"] = resolved_now.isoformat()
        save_browser_guard_state(state, state_path)
        _append_guard_event(
            {
                "occurred_at": resolved_now.isoformat(),
                "event_type": resolved_auth_state,
                "profile_key": profile_key,
                "feature": feature,
                "scope_key": scope_key,
                "auth_state": resolved_auth_state,
                "keep_page_open": bool(keep_page_open),
                "error_message": str(error_message or "").strip() or None,
            },
            event_log_path,
        )
        persist_browser_guard_event(
            profile_key=profile_key,
            feature=feature,
            scope_key=scope_key,
            event_type=resolved_auth_state,
            auth_state=resolved_auth_state,
            consecutive_hits=0,
            keep_page_open=keep_page_open,
            error_message=str(error_message or "").strip() or None,
            occurred_at=resolved_now,
        )
        return _build_preflight_decision(
            allowed=False,
            decision="manual_intervention_required",
            profile_key=profile_key,
            feature=feature,
            scope_key=scope_key,
            auth_state=resolved_auth_state,
            source="browser_guard_event",
            reason="manual_intervention_required",
            recommended_sleep_seconds=60,
            cooldown_started_at=resolved_now.isoformat(),
            error_message=str(error_message or "").strip() or None,
        )

    profile_hits = max(int(profile_entry.get("consecutive_hits") or 0), 0) + 1
    profile_wait_seconds = compute_browser_guard_cooldown_seconds(
        consecutive_hits=profile_hits,
        base_seconds=base_seconds,
        max_seconds=max_seconds,
    )
    profile_next_retry_at = resolved_now + timedelta(seconds=profile_wait_seconds)
    profile_entry.update(
        {
            "auth_state": resolved_auth_state,
            "consecutive_hits": profile_hits,
            "cooldown_started_at": resolved_now.isoformat(),
            "next_retry_at": profile_next_retry_at.isoformat(),
            "last_error": str(error_message or "").strip() or None,
            "last_feature": feature,
            "last_scope_key": scope_key,
            "last_event_at": resolved_now.isoformat(),
            "last_success_at": profile_entry.get("last_success_at"),
            "updated_at": resolved_now.isoformat(),
        }
    )
    profiles[profile_key] = profile_entry

    if scope_key is not None:
        scope_hits = max(int(scope_entry.get("consecutive_hits") or 0), 0) + 1
        scope_wait_seconds = compute_browser_guard_cooldown_seconds(
            consecutive_hits=scope_hits,
            base_seconds=base_seconds,
            max_seconds=max_seconds,
        )
        scope_next_retry_at = resolved_now + timedelta(seconds=scope_wait_seconds)
        scope_entry.update(
            {
                "auth_state": resolved_auth_state,
                "consecutive_hits": scope_hits,
                "cooldown_started_at": resolved_now.isoformat(),
                "next_retry_at": scope_next_retry_at.isoformat(),
                "last_error": str(error_message or "").strip() or None,
                "last_feature": feature,
                "last_scope_key": scope_key,
                "last_event_at": resolved_now.isoformat(),
                "last_success_at": scope_entry.get("last_success_at"),
                "updated_at": resolved_now.isoformat(),
            }
        )
        scopes[scope_id] = scope_entry

    state["updated_at"] = resolved_now.isoformat()
    save_browser_guard_state(state, state_path)
    _append_guard_event(
        {
            "occurred_at": resolved_now.isoformat(),
            "event_type": resolved_auth_state,
            "profile_key": profile_key,
            "feature": feature,
            "scope_key": scope_key,
            "auth_state": resolved_auth_state,
            "consecutive_hits": profile_hits,
            "backoff_seconds": profile_wait_seconds,
            "next_retry_at": profile_next_retry_at.isoformat(),
            "keep_page_open": bool(keep_page_open),
            "error_message": str(error_message or "").strip() or None,
        },
        event_log_path,
    )
    persist_browser_guard_event(
        profile_key=profile_key,
        feature=feature,
        scope_key=scope_key,
        event_type=resolved_auth_state,
        auth_state=resolved_auth_state,
        consecutive_hits=profile_hits,
        backoff_seconds=profile_wait_seconds,
        next_retry_at=profile_next_retry_at,
        keep_page_open=keep_page_open,
        error_message=str(error_message or "").strip() or None,
        occurred_at=resolved_now,
    )
    return _build_preflight_decision(
        allowed=False,
        decision="cooldown",
        profile_key=profile_key,
        feature=feature,
        scope_key=scope_key,
        auth_state=resolved_auth_state,
        source="browser_guard_event",
        reason="risk_control",
        wait_seconds=profile_wait_seconds,
        recommended_sleep_seconds=profile_wait_seconds,
        next_retry_at=profile_next_retry_at.isoformat(),
        cooldown_started_at=resolved_now.isoformat(),
        error_message=str(error_message or "").strip() or None,
    )
