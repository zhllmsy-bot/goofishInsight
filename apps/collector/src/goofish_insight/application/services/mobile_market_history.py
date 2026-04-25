from __future__ import annotations

import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from ...compat import UTC
from pathlib import Path
from typing import Any

from ...db import session_scope
from ...models import AnalysisReport
from ...settings import get_settings


ADB_DEFAULT_TIMEOUT_SEC = 10
IDLEFISH_PACKAGE = "com.taobao.idlefish"
LATIN_IME_ID = "com.huawei.ohos.inputmethod/com.android.inputmethod.latin.LatinIME"

USB_DIALOG_TITLE = "USB连接方式"
MARKET_MARKERS = ("近7日成交均价", "成交记录")
SEARCH_DISCOVERY_MARKERS = ("历史搜索", "猜你可能在找")
SEARCH_RESULT_MARKERS = ("行情", "查询宝贝成交价")
CAMERA_SEARCH_MARKERS = ("翻转", "闪光灯", "拍图搜")
KNOWN_DIALOG_DISMISS_TEXTS = ("取消",)

RECENT_QUERY_VERTICAL_CUTOFF = 920
RECORD_SECTION_FALLBACK_MIN_Y = 900
SEARCH_FIELD_FOCUS_X = 260
SEARCH_FIELD_FOCUS_Y = 170

PRICE_RANGE_PATTERN = re.compile(r"¥\s*(\d[\d,]*)\s*-\s*(\d[\d,]*)")
PRICE_VALUE_PATTERN = re.compile(r"¥\s*(\d[\d,]*)")
SOLD_AFTER_DAYS_PATTERN = re.compile(r"发布\s*(\d+)\s*天后成交")
PUBLISHED_PRICE_PATTERN = re.compile(r"发布价¥\s*(\d[\d,]*)")


@dataclass(slots=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)


@dataclass(slots=True)
class UiNode:
    text: str
    normalized_text: str
    resource_id: str
    class_name: str
    clickable: bool
    focused: bool
    bounds: Bounds | None


@dataclass(slots=True)
class StepResult:
    step: str
    status: str
    detail: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(slots=True)
class VisibleSaleRecord:
    title: str
    brand_hint: str | None = None
    condition_hint: str | None = None
    published_price: int | None = None
    sold_price: int | None = None
    sold_after_days: int | None = None


@dataclass(slots=True)
class MobileMarketSnapshot:
    captured_at: str
    activity: str | None
    state: str
    query: str | None
    xml_path: str
    screenshot_path: str
    recent_avg_price_7d: int | None = None
    sold_price_range_low: int | None = None
    sold_price_range_high: int | None = None
    visible_records: list[VisibleSaleRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    steps: list[StepResult] = field(default_factory=list)


def reports_dir() -> Path:
    path = get_settings().base_dir / "reports"
    path.mkdir(parents=True, exist_ok=True)
    return path


def device_reports_dir() -> Path:
    path = reports_dir() / "device"
    path.mkdir(parents=True, exist_ok=True)
    return path


def normalize_ui_text(value: str | None) -> str:
    if not value:
        return ""
    normalized = value
    for token in ("\u200b", "\u2006", "\ufeff", "\u00a0"):
        normalized = normalized.replace(token, "")
    return re.sub(r"\s+", "", normalized).strip()


def parse_price_value(value: str | None) -> int | None:
    if not value:
        return None
    match = PRICE_VALUE_PATTERN.search(value)
    if match:
        return int(match.group(1).replace(",", ""))
    normalized = normalize_ui_text(value)
    if re.fullmatch(r"\d[\d,]*", normalized):
        return int(normalized.replace(",", ""))
    return None


def parse_bounds(value: str | None) -> Bounds | None:
    if not value:
        return None
    match = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", value)
    if not match:
        return None
    return Bounds(*(int(match.group(index)) for index in range(1, 5)))


def encode_adb_text(value: str) -> str:
    sanitized = value.strip()
    replacements = {
        " ": "%s",
        "(": "\\(",
        ")": "\\)",
        "&": "\\&",
        "|": "\\|",
        "<": "\\<",
        ">": "\\>",
        ";": "\\;",
        "'": "\\'",
        '"': '\\"',
    }
    encoded = sanitized
    for source, target in replacements.items():
        encoded = encoded.replace(source, target)
    return encoded


def adb_command(
    *args: str,
    serial: str | None = None,
    timeout_sec: int = ADB_DEFAULT_TIMEOUT_SEC,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    command = ["adb"]
    if serial:
        command.extend(["-s", serial])
    command.extend(args)
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    if check and completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"ADB command failed ({' '.join(command)}): {stderr}")
    return completed


def get_current_input_method(*, serial: str | None = None) -> str | None:
    value = adb_command("shell", "settings", "get", "secure", "default_input_method", serial=serial).stdout.strip()
    return value or None


def set_input_method(ime_id: str, *, serial: str | None = None) -> None:
    adb_command("shell", "ime", "set", ime_id, serial=serial, timeout_sec=15)


def pull_ui_snapshot(*, tag: str, serial: str | None = None) -> tuple[Path, Path, str | None]:
    target_dir = device_reports_dir()
    xml_path = target_dir / f"{tag}.xml"
    png_path = target_dir / f"{tag}.png"

    remote_xml = f"/sdcard/{tag}.xml"
    remote_png = f"/sdcard/{tag}.png"

    last_error: RuntimeError | None = None
    for _ in range(3):
        try:
            adb_command("shell", "uiautomator", "dump", remote_xml, serial=serial, timeout_sec=15)
            adb_command("pull", remote_xml, str(xml_path), serial=serial, timeout_sec=15)
            adb_command("shell", "screencap", "-p", remote_png, serial=serial, timeout_sec=15)
            adb_command("pull", remote_png, str(png_path), serial=serial, timeout_sec=15)
            break
        except RuntimeError as exc:
            last_error = exc
            time.sleep(0.8)
    else:
        raise last_error or RuntimeError("Unable to capture Android UI snapshot.")

    focus_output = adb_command("shell", "dumpsys", "window", serial=serial, timeout_sec=15).stdout
    match = re.search(r"mCurrentFocus=Window\{[^\s]+\s+u\d+\s+([^}\s]+)\}", focus_output)
    activity = match.group(1) if match else None
    return xml_path, png_path, activity


def load_ui_nodes(xml_path: Path) -> list[UiNode]:
    root = ET.fromstring(xml_path.read_text(encoding="utf-8", errors="ignore"))
    nodes: list[UiNode] = []
    for node in root.iter("node"):
        raw_text = " ".join(
            part for part in (node.attrib.get("text"), node.attrib.get("content-desc")) if part
        )
        nodes.append(
            UiNode(
                text=raw_text.strip(),
                normalized_text=normalize_ui_text(raw_text),
                resource_id=node.attrib.get("resource-id", ""),
                class_name=node.attrib.get("class", ""),
                clickable=node.attrib.get("clickable") == "true",
                focused=node.attrib.get("focused") == "true",
                bounds=parse_bounds(node.attrib.get("bounds")),
            )
        )
    return nodes


def detect_screen_state(nodes: list[UiNode]) -> str:
    texts = {node.normalized_text for node in nodes if node.normalized_text}
    resource_ids = {node.resource_id for node in nodes if node.resource_id}
    if USB_DIALOG_TITLE in texts:
        return "usb_dialog"
    if all(marker in texts for marker in CAMERA_SEARCH_MARKERS):
        return "camera_search"
    if (
        any(resource_id.endswith("default_search") for resource_id in resource_ids)
        or any(resource_id.endswith("home_container") for resource_id in resource_ids)
    ):
        return "home"
    if all(marker in texts for marker in MARKET_MARKERS):
        return "market"
    if "成交记录" in texts and ("最近成交" in texts or "在售宝贝" in texts):
        return "market"
    if any("近7日成交均价" in text for text in texts):
        return "search_result"
    if any(text.endswith("行情") or "查询宝贝成交价" in text for text in texts):
        return "search_result"
    if any(marker in texts for marker in SEARCH_DISCOVERY_MARKERS):
        return "search_discovery"
    if any(marker in texts for marker in SEARCH_RESULT_MARKERS):
        return "search_result"
    return "unknown"


def extract_query(nodes: list[UiNode]) -> str | None:
    for node in nodes:
        if node.resource_id.endswith("keyword_text") and node.normalized_text:
            return node.normalized_text
    if any(node.resource_id.endswith("default_search") for node in nodes):
        return None

    candidates = [
        node
        for node in nodes
        if node.bounds
        and 100 <= node.bounds.top < 260
        and 80 <= node.bounds.left <= 980
        and node.normalized_text
        and node.normalized_text not in {USB_DIALOG_TITLE, "返回", "删除", "清除", "图片搜索", "更多"}
        and "搜索宝贝" not in node.normalized_text
    ]
    candidates.sort(key=lambda item: (item.bounds.top if item.bounds else 0, -(len(item.normalized_text))))
    return candidates[0].normalized_text if candidates else None


def tap_bounds(bounds: Bounds, *, serial: str | None = None) -> None:
    x, y = bounds.center
    adb_command("shell", "input", "tap", str(x), str(y), serial=serial, timeout_sec=10)


def dismiss_known_dialogs(nodes: list[UiNode], *, serial: str | None = None) -> bool:
    for text in KNOWN_DIALOG_DISMISS_TEXTS:
        for node in nodes:
            if node.normalized_text == text and node.bounds:
                tap_bounds(node.bounds, serial=serial)
                return True
    return False


def find_node_by_text(
    nodes: list[UiNode],
    text: str,
    *,
    max_top: int | None = None,
    max_bottom: int | None = None,
) -> UiNode | None:
    normalized_target = normalize_ui_text(text)
    candidates = []
    for node in nodes:
        if normalized_target and normalized_target == node.normalized_text:
            if node.bounds:
                if max_top is not None and node.bounds.top > max_top:
                    continue
                if max_bottom is not None and node.bounds.bottom > max_bottom:
                    continue
            candidates.append(node)
    candidates.sort(key=lambda item: (item.bounds.top if item.bounds else 10**9, item.bounds.left if item.bounds else 10**9))
    return candidates[0] if candidates else None


def find_recent_query_chip(nodes: list[UiNode], query: str) -> UiNode | None:
    normalized_query = normalize_ui_text(query)
    candidates = []
    for node in nodes:
        if node.bounds and node.normalized_text == normalized_query and node.bounds.top <= RECENT_QUERY_VERTICAL_CUTOFF:
            candidates.append(node)
    candidates.sort(key=lambda item: (item.bounds.top if item.bounds else 10**9, item.bounds.left if item.bounds else 10**9))
    return candidates[0] if candidates else None


def find_market_suggestion(nodes: list[UiNode], query: str) -> UiNode | None:
    normalized_query = normalize_ui_text(query)
    target = f"{normalized_query}行情"
    candidates = []
    for node in nodes:
        if not node.bounds:
            continue
        if node.normalized_text == target or (
            node.normalized_text.endswith("行情") and normalized_query in node.normalized_text
        ) or (
            normalized_query in node.normalized_text and "近7日成交均价" in node.normalized_text
        ) or (
            normalized_query in node.normalized_text and "查询宝贝成交价" in node.normalized_text
        ):
            candidates.append(node)
    candidates.sort(key=lambda item: (item.bounds.top if item.bounds else 10**9, item.bounds.left if item.bounds else 10**9))
    return candidates[0] if candidates else None


def find_home_search_entry(nodes: list[UiNode]) -> UiNode | None:
    for node in nodes:
        if not node.bounds:
            continue
        if node.resource_id.endswith("search_bar_layout"):
            return node
    return None


def find_market_tab(nodes: list[UiNode]) -> UiNode | None:
    return find_node_by_text(nodes, "行情", max_bottom=420)


def find_record_section_min_y(nodes: list[UiNode]) -> int:
    anchors: list[int] = []
    for text, offset in (("成交记录", 80), ("最近成交", 80), ("成交区间", 40)):
        anchor = find_node_by_text(nodes, text)
        if anchor and anchor.bounds:
            anchors.append(anchor.bounds.bottom + offset)
    return min(anchors) if anchors else RECORD_SECTION_FALLBACK_MIN_Y


def find_search_submit_button(nodes: list[UiNode]) -> UiNode | None:
    candidates = [
        node
        for node in nodes
        if node.bounds
        and node.clickable
        and node.bounds.top < 420
        and node.bounds.right > 820
        and node.bounds.left > 780
    ]
    candidates.sort(key=lambda item: (item.bounds.top, item.bounds.left))
    return candidates[-1] if candidates else None


def focus_search_field(*, serial: str | None = None) -> None:
    adb_command(
        "shell",
        "input",
        "tap",
        str(SEARCH_FIELD_FOCUS_X),
        str(SEARCH_FIELD_FOCUS_Y),
        serial=serial,
        timeout_sec=10,
    )


def clear_search_field(*, serial: str | None = None, backspaces: int = 32) -> None:
    adb_command("shell", "input", "keyevent", "123", serial=serial, timeout_sec=10)
    for _ in range(backspaces):
        adb_command("shell", "input", "keyevent", "67", serial=serial, timeout_sec=10)


def input_search_query(query: str, *, serial: str | None = None) -> None:
    previous_ime = get_current_input_method(serial=serial)
    try:
        if previous_ime != LATIN_IME_ID:
            set_input_method(LATIN_IME_ID, serial=serial)
            time.sleep(0.4)
        focus_search_field(serial=serial)
        time.sleep(0.2)
        clear_search_field(serial=serial)
        adb_command("shell", "input", "text", encode_adb_text(query), serial=serial, timeout_sec=10)
    finally:
        if previous_ime and previous_ime != LATIN_IME_ID:
            set_input_method(previous_ime, serial=serial)


def capture_snapshot(tag: str, *, serial: str | None = None) -> tuple[list[UiNode], MobileMarketSnapshot]:
    xml_path, png_path, activity = pull_ui_snapshot(tag=tag, serial=serial)
    nodes = load_ui_nodes(xml_path)
    snapshot = MobileMarketSnapshot(
        captured_at=datetime.now(UTC).isoformat(),
        activity=activity,
        state=detect_screen_state(nodes),
        query=extract_query(nodes),
        xml_path=str(xml_path),
        screenshot_path=str(png_path),
    )
    return nodes, snapshot


def launch_idlefish(*, serial: str | None = None, cold_start: bool = False) -> None:
    if cold_start:
        adb_command("shell", "am", "force-stop", IDLEFISH_PACKAGE, serial=serial, timeout_sec=15)
        time.sleep(0.8)
    adb_command(
        "shell",
        "monkey",
        "-p",
        IDLEFISH_PACKAGE,
        "-c",
        "android.intent.category.LAUNCHER",
        "1",
        serial=serial,
        timeout_sec=20,
    )
    time.sleep(1.8)


def ensure_idlefish_base_state(
    *,
    serial: str | None = None,
    cold_start: bool = True,
    max_steps: int = 6,
) -> MobileMarketSnapshot:
    launch_idlefish(serial=serial, cold_start=cold_start)

    for step_index in range(1, max_steps + 1):
        nodes, snapshot = capture_snapshot(f"mobile-market-base-{step_index}", serial=serial)
        snapshot.steps.append(
            StepResult(
                step="capture_base_snapshot",
                status="ok",
                detail=f"Captured base screen in state={snapshot.state}, activity={snapshot.activity or '-'}",
            )
        )

        if snapshot.state == "usb_dialog":
            handled = dismiss_known_dialogs(nodes, serial=serial)
            snapshot.steps.append(
                StepResult(
                    step="dismiss_usb_dialog",
                    status="ok" if handled else "failed",
                    detail="Dismissed USB mode dialog." if handled else "Unable to dismiss USB mode dialog.",
                )
            )
            if handled:
                time.sleep(1.0)
                continue
            raise RuntimeError("USB mode dialog blocked the workflow.")

        if snapshot.state == "camera_search":
            adb_command("shell", "input", "keyevent", "4", serial=serial, timeout_sec=10)
            time.sleep(1.0)
            continue

        if snapshot.state == "home":
            return snapshot

        if snapshot.state in {"search_discovery", "search_result", "market"}:
            adb_command("shell", "input", "keyevent", "4", serial=serial, timeout_sec=10)
            time.sleep(1.0)
            continue

        home_search_entry = find_home_search_entry(nodes)
        if home_search_entry and home_search_entry.bounds:
            snapshot.state = "home"
            snapshot.query = None
            return snapshot

        launch_idlefish(serial=serial, cold_start=False)

    raise RuntimeError("Unable to restore Idle Fish to a reusable home/search-entry baseline.")


def extract_market_summary(snapshot: MobileMarketSnapshot, nodes: list[UiNode]) -> None:
    texts = [node for node in nodes if node.normalized_text and node.bounds]
    texts.sort(key=lambda item: (item.bounds.top, item.bounds.left))

    price_range = None
    for node in texts:
        match = PRICE_RANGE_PATTERN.search(node.normalized_text)
        if match:
            price_range = (
                int(match.group(1).replace(",", "")),
                int(match.group(2).replace(",", "")),
            )
            break
    if price_range:
        snapshot.sold_price_range_low, snapshot.sold_price_range_high = price_range

    avg_anchor = find_node_by_text(nodes, "近7日成交均价")
    if avg_anchor and avg_anchor.bounds:
        nearby = [
            node
            for node in texts
            if node.bounds
            and avg_anchor.bounds.top - 20 <= node.bounds.top <= avg_anchor.bounds.bottom + 160
            and node.bounds.left <= avg_anchor.bounds.right + 120
        ]
        price_candidates = [parse_price_value(node.normalized_text) for node in nearby]
        price_candidates = [value for value in price_candidates if value is not None]
        if price_candidates:
            snapshot.recent_avg_price_7d = max(price_candidates)


def extract_visible_sale_records(snapshot: MobileMarketSnapshot, nodes: list[UiNode]) -> None:
    record_section_min_y = find_record_section_min_y(nodes)
    visible_nodes = [
        node
        for node in nodes
        if node.bounds and node.normalized_text and node.bounds.top >= record_section_min_y
    ]
    visible_nodes.sort(key=lambda item: (item.bounds.top, item.bounds.left))

    title_candidates = [
        node
        for node in visible_nodes
        if len(node.normalized_text) >= 8
        and "成交记录" not in node.normalized_text
        and "成交区间" not in node.normalized_text
        and "/" not in node.normalized_text
        and not node.normalized_text.startswith("¥")
        and not node.normalized_text.startswith("发布价")
        and not node.normalized_text.startswith("发布")
        and node.normalized_text not in {"Apple/苹果", "成交价", "最近成交", "在售宝贝"}
    ]

    records: list[VisibleSaleRecord] = []
    for title_node in title_candidates:
        if not title_node.bounds:
            continue
        row_nodes = [
            node
            for node in visible_nodes
            if node.bounds
            and title_node.bounds.top <= node.bounds.top <= title_node.bounds.top + 220
        ]
        if not row_nodes:
            continue

        published_price = None
        sold_price = None
        sold_after_days = None
        brand_hint = None
        condition_hint = None

        for node in row_nodes:
            text = node.normalized_text
            if not brand_hint and "/" in text:
                brand_hint = text
            elif (
                not condition_hint
                and len(text) <= 16
                and any(keyword in text for keyword in ("新", "使用", "痕迹", "成色"))
            ):
                condition_hint = text

            if published_price is None:
                published_match = PUBLISHED_PRICE_PATTERN.search(text)
                if published_match:
                    published_price = int(published_match.group(1).replace(",", ""))

            if sold_after_days is None:
                sold_days_match = SOLD_AFTER_DAYS_PATTERN.search(text)
                if sold_days_match:
                    sold_after_days = int(sold_days_match.group(1))
                elif "发布当天成交" in text:
                    sold_after_days = 0

            if sold_price is None and node.bounds.left >= 760:
                sold_price = parse_price_value(text)

        if sold_price is None:
            continue
        records.append(
            VisibleSaleRecord(
                title=title_node.normalized_text,
                brand_hint=brand_hint,
                condition_hint=condition_hint,
                published_price=published_price,
                sold_price=sold_price,
                sold_after_days=sold_after_days,
            )
        )

    deduped: list[VisibleSaleRecord] = []
    seen: set[tuple[str, int | None]] = set()
    for record in records:
        key = (record.title, record.sold_price)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
    snapshot.visible_records = deduped


def swipe_records_section(*, serial: str | None = None) -> None:
    adb_command("shell", "input", "swipe", "540", "2050", "540", "1280", "300", serial=serial, timeout_sec=10)


def ensure_market_page(
    *,
    query: str | None,
    serial: str | None = None,
    max_steps: int = 8,
) -> MobileMarketSnapshot:
    desired_query = normalize_ui_text(query) if query else None

    for step_index in range(1, max_steps + 1):
        nodes, snapshot = capture_snapshot(f"mobile-market-step-{step_index}", serial=serial)
        snapshot.steps.append(
            StepResult(
                step="capture_snapshot",
                status="ok",
                detail=f"Captured screen in state={snapshot.state}, activity={snapshot.activity or '-'}",
            )
        )

        if snapshot.state == "usb_dialog":
            handled = dismiss_known_dialogs(nodes, serial=serial)
            snapshot.steps.append(
                StepResult(
                    step="dismiss_usb_dialog",
                    status="ok" if handled else "failed",
                    detail="Dismissed USB mode dialog." if handled else "Unable to dismiss USB mode dialog.",
                )
            )
            if handled:
                time.sleep(1)
                continue
            raise RuntimeError("USB mode dialog blocked the workflow.")

        if snapshot.state == "camera_search":
            adb_command("shell", "input", "keyevent", "4", serial=serial, timeout_sec=10)
            snapshot.steps.append(
                StepResult(
                    step="dismiss_camera_search",
                    status="ok",
                    detail="Returned from camera/image-search screen.",
                )
            )
            time.sleep(1.0)
            continue

        if snapshot.state == "market":
            current_query = normalize_ui_text(snapshot.query) if snapshot.query else None
            if desired_query and current_query and desired_query != current_query:
                adb_command("shell", "input", "keyevent", "4", serial=serial, timeout_sec=10)
                time.sleep(1.0)
                continue
            extract_market_summary(snapshot, nodes)
            extract_visible_sale_records(snapshot, nodes)
            return snapshot
        search_button = find_search_submit_button(nodes)

        if desired_query and snapshot.query == desired_query:
            market_tab = find_market_tab(nodes)
            if market_tab and market_tab.bounds:
                tap_bounds(market_tab.bounds, serial=serial)
                time.sleep(1.5)
                continue
            if snapshot.state == "search_discovery" and search_button and search_button.bounds:
                tap_bounds(search_button.bounds, serial=serial)
                time.sleep(1.5)
                continue

        if desired_query:
            market_suggestion = find_market_suggestion(nodes, desired_query)
            if market_suggestion and market_suggestion.bounds:
                tap_bounds(market_suggestion.bounds, serial=serial)
                time.sleep(1.5)
                continue

        if desired_query:
            recent_chip = find_recent_query_chip(nodes, desired_query)
            if recent_chip and recent_chip.bounds:
                tap_bounds(recent_chip.bounds, serial=serial)
                time.sleep(1.8)
                continue

        home_search_entry = find_home_search_entry(nodes)
        if desired_query and home_search_entry and home_search_entry.bounds:
            tap_bounds(home_search_entry.bounds, serial=serial)
            time.sleep(1.2)
            continue

        if desired_query and snapshot.state in {"search_discovery", "search_result"}:
            input_search_query(desired_query, serial=serial)
            time.sleep(1.2)
            continue

        if (
            desired_query
            and snapshot.query == desired_query
            and snapshot.state == "search_discovery"
            and search_button
            and search_button.bounds
        ):
            tap_bounds(search_button.bounds, serial=serial)
            time.sleep(1.8)
            continue

        snapshot.warnings.append(
            "Unable to advance to the market page automatically. "
            "Current device state does not expose a reusable query chip or a submit action for the requested query."
        )
        raise RuntimeError(json.dumps(asdict(snapshot), ensure_ascii=False, indent=2))

    raise RuntimeError("Exceeded the maximum number of steps while trying to open the market page.")


def collect_mobile_market_history(
    *,
    query: str | None = None,
    serial: str | None = None,
    max_scrolls: int = 0,
    reset_to_home: bool = False,
) -> MobileMarketSnapshot:
    if reset_to_home:
        base_snapshot = ensure_idlefish_base_state(serial=serial, cold_start=True)
        base_snapshot.steps.append(
            StepResult(
                step="ensure_idlefish_base_state",
                status="ok",
                detail="Restored Idle Fish to a reusable home/search-entry baseline.",
            )
        )
    snapshot = ensure_market_page(query=query, serial=serial)
    snapshot.steps.append(
        StepResult(
            step="ensure_market_page",
            status="ok",
            detail=f"Reached market page for query={snapshot.query or '-'}",
        )
    )

    if max_scrolls <= 0:
        return snapshot

    all_records = {(record.title, record.sold_price): record for record in snapshot.visible_records}
    for scroll_index in range(1, max_scrolls + 1):
        swipe_records_section(serial=serial)
        time.sleep(1.2)
        nodes, current = capture_snapshot(f"mobile-market-scroll-{scroll_index}", serial=serial)
        if current.state != "market":
            snapshot.warnings.append(
                f"Scroll {scroll_index} left the market page; stopped scroll collection at state={current.state}."
            )
            break
        extract_market_summary(current, nodes)
        extract_visible_sale_records(current, nodes)
        new_count = 0
        for record in current.visible_records:
            key = (record.title, record.sold_price)
            if key not in all_records:
                all_records[key] = record
                new_count += 1
        snapshot.steps.append(
            StepResult(
                step="scroll_collect",
                status="ok",
                detail=f"Scroll {scroll_index} captured {new_count} new visible成交记录.",
            )
        )
        if new_count == 0:
            break

    snapshot.visible_records = list(all_records.values())
    return snapshot


def persist_mobile_market_history(
    snapshot: MobileMarketSnapshot,
    *,
    output: Path | None = None,
) -> Path:
    output_path = output or (
        reports_dir() / f"mobile-market-history-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    payload = json.dumps(asdict(snapshot), ensure_ascii=False, indent=2)
    output_path.write_text(payload, encoding="utf-8")
    return output_path


def save_mobile_market_history_report(snapshot: MobileMarketSnapshot) -> int:
    title_query = snapshot.query or "unknown-query"
    summary_bits = []
    if snapshot.recent_avg_price_7d is not None:
        summary_bits.append(f"近7日成交均价 ¥{snapshot.recent_avg_price_7d}")
    if snapshot.sold_price_range_low is not None and snapshot.sold_price_range_high is not None:
        summary_bits.append(
            f"成交区间 ¥{snapshot.sold_price_range_low}-{snapshot.sold_price_range_high}"
        )
    summary_bits.append(f"可见成交记录 {len(snapshot.visible_records)} 条")
    summary = "；".join(summary_bits)

    with session_scope() as session:
        report = AnalysisReport(
            report_type="mobile_market_history",
            business_domain=None,
            report_date=date.today(),
            title=f"Mobile market history {title_query}",
            summary=summary,
            payload=asdict(snapshot),
        )
        session.add(report)
        session.flush()
        return int(report.id)
