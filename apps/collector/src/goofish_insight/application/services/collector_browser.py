from __future__ import annotations

import json
from typing import Any

from ...logging import get_logger

logger = get_logger(__name__)

RISK_CONTROL_IFRAME_URL_MARKERS = (
    "executecaptcha",
    "baxia",
    "nocaptcha",
    "punish",
)
RISK_CONTROL_DOM_TEXT_HINTS = (
    "请依次连出",
    "安全验证",
)
BROWSER_DISCONNECT_ERROR_MARKERS = (
    "target page, context or browser has been closed",
    "browsertype.connect_over_cdp",
    "connect econnrefused 127.0.0.1:",
    "connection closed while reading from the driver",
)


def classify_payload_status(payload: dict[str, Any]) -> str:
    returns = payload.get("ret") or []
    if not returns:
        return "ok"
    joined = " ".join(returns)
    payload_text = json.dumps(payload, ensure_ascii=False)
    if "RGV587_ERROR" in joined or "baxia" in payload_text:
        return "risk_control"
    if "登录" in joined:
        return "login_required"
    return "other"


def detect_page_risk_control_signal(*, frame_urls: list[str], page_text: str | None) -> str | None:
    for raw_url in frame_urls:
        resolved_url = str(raw_url or "").strip()
        if not resolved_url:
            continue
        lowered_url = resolved_url.lower()
        if any(marker in lowered_url for marker in RISK_CONTROL_IFRAME_URL_MARKERS):
            return f"iframe:{resolved_url}"

    resolved_page_text = str(page_text or "").strip()
    if not resolved_page_text:
        return None
    for hint in RISK_CONTROL_DOM_TEXT_HINTS:
        if hint in resolved_page_text:
            return f"dom:{hint}"
    return None


def detect_page_risk_control_signal_from_page(page) -> str | None:
    frame_urls: list[str] = []
    try:
        frame_urls = [str(getattr(frame, "url", "") or "") for frame in page.frames]
    except Exception:
        logger.debug("failed to inspect page frames for risk-control signals", exc_info=True)
        frame_urls = []

    page_text: str | None = None
    try:
        page_text = page.inner_text("body", timeout=600)
    except Exception:
        logger.debug("failed to inspect page body for risk-control signals", exc_info=True)
        page_text = None

    return detect_page_risk_control_signal(
        frame_urls=frame_urls,
        page_text=page_text,
    )


def is_browser_disconnect_error(error_message: str | None) -> bool:
    resolved = str(error_message or "").strip().lower()
    if not resolved:
        return False
    return any(marker in resolved for marker in BROWSER_DISCONNECT_ERROR_MARKERS)


def infer_auth_state_from_error_message(error_message: str | None) -> str | None:
    resolved = str(error_message or "").strip().lower()
    if not resolved:
        return None
    if any(token in resolved for token in ("risk control", "rgv587_error", "baxia", "executecaptcha", "风控")):
        return "risk_control"
    if any(token in resolved for token in ("login is still required", "需要登录", "login required")):
        return "login_required"
    return None


def extract_payload_error(payload: dict[str, Any]) -> str | None:
    returns = payload.get("ret") or []
    return " | ".join(str(item) for item in returns) if returns else None


def is_manual_verification_state(auth_state: str | None) -> bool:
    return str(auth_state or "").strip() in {"risk_control", "login_required"}


def should_keep_manual_verification_page_open(auth_state: str | None) -> bool:
    return str(auth_state or "").strip() == "login_required"


def build_search_capture_failure_message(*, auth_state: str | None, last_error: str | None) -> str:
    if auth_state == "risk_control":
        return f"No valid search payload captured. Risk control blocked the search: {last_error or 'unknown'}"
    if auth_state == "login_required":
        return f"No valid search payload captured. Login is still required: {last_error or 'unknown'}"
    return "No valid search payload captured."


def build_manual_verification_transport_message(
    *,
    auth_state: str | None,
    last_error: str | None,
    transport_error: str | None,
) -> str:
    base_message = build_search_capture_failure_message(
        auth_state=auth_state,
        last_error=last_error or transport_error,
    )
    resolved_transport = str(transport_error or "").strip()
    if not resolved_transport or resolved_transport in base_message:
        return base_message
    return f"{base_message} | transport_error={resolved_transport}"
