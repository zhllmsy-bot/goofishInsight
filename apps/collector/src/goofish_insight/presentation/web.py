from __future__ import annotations

from datetime import datetime
from ..compat import UTC
from decimal import Decimal

from fastapi.templating import Jinja2Templates
from ..category_compat import display_label_for_scope, token_aliases_for_scope

DOMAIN_LABELS = {
    "camera_interchangeable_lens": "可换镜头",
    "camera_body": "相机机身",
    "graphics_card": "显卡",
    "phone": "手机",
    "garmin": "Garmin手表",
    "garmin_watch": "Garmin手表",
    "apple_m_series": "Apple电脑",
    "apple_computer": "Apple电脑",
}

DOMAIN_TOKENS = {
    "camera_interchangeable_lens": list(token_aliases_for_scope("camera_interchangeable_lens")),
    "camera_body": list(token_aliases_for_scope("camera_body")),
    "graphics_card": list(token_aliases_for_scope("graphics_card")),
    "phone": list(token_aliases_for_scope("phone")),
    "garmin": list(token_aliases_for_scope("garmin")),
    "garmin_watch": list(token_aliases_for_scope("garmin_watch")),
    "apple_m_series": list(token_aliases_for_scope("apple_m_series")),
    "apple_computer": list(token_aliases_for_scope("apple_computer")),
}

PRICING_VIEW_LABELS = {
    "brand": "品牌",
    "product": "产品",
    "spec": "产品 + 规格",
}

FILTER_LABELS = {
    "product_label": "产品",
    "spec_label": "精确规格",
    "display_type": "屏幕类型",
    "case_size_mm": "表盘尺寸",
    "is_solar": "太阳能",
    "chip_family": "芯片",
    "screen_size_in": "屏幕尺寸",
    "memory_gb": "内存",
    "storage_gb": "硬盘",
}

STRUCTURED_FILTER_KEYS = (
    "product_label",
    "spec_label",
    "display_type",
    "case_size_mm",
    "is_solar",
    "chip_family",
    "screen_size_in",
    "memory_gb",
    "storage_gb",
)

FILTER_OPTION_KEYS = {
    "product_label": "product_options",
    "spec_label": "spec_options",
    "display_type": "display_type_options",
    "case_size_mm": "case_size_options",
    "is_solar": "is_solar_options",
    "chip_family": "chip_family_options",
    "screen_size_in": "screen_size_options",
    "memory_gb": "memory_options",
    "storage_gb": "storage_options",
}

FILTER_PLACEHOLDERS = {
    "product_label": "全部产品",
    "spec_label": "全部精确规格",
    "display_type": "全部",
    "case_size_mm": "全部",
    "is_solar": "全部",
    "chip_family": "全部",
    "screen_size_in": "全部",
    "memory_gb": "全部",
    "storage_gb": "全部",
}

FILTER_LAYOUT_MAP = {
    "product_label": "wide",
    "spec_label": "wide",
    "display_type": "narrow",
    "case_size_mm": "narrow",
    "is_solar": "narrow",
    "chip_family": "narrow",
    "screen_size_in": "narrow",
    "memory_gb": "narrow",
    "storage_gb": "narrow",
}

DOMAIN_FILTER_LAYOUTS = {
    None: ("product_label", "spec_label"),
    "camera_interchangeable_lens": ("product_label", "spec_label"),
    "camera_body": ("product_label", "spec_label"),
    "graphics_card": ("product_label", "spec_label"),
    "phone": ("product_label", "spec_label"),
    "garmin": ("product_label", "spec_label", "display_type", "case_size_mm", "is_solar"),
    "garmin_watch": ("product_label", "spec_label", "display_type", "case_size_mm", "is_solar"),
    "apple_m_series": ("product_label", "spec_label", "chip_family", "screen_size_in", "memory_gb", "storage_gb"),
    "apple_computer": ("product_label", "spec_label", "chip_family", "screen_size_in", "memory_gb", "storage_gb"),
}

NOISY_FILTER_TERMS = (
    "功能正常",
    "成色",
    "包邮",
    "看上直接拍",
    "不议价",
    "售出不退",
    "所见即所得",
    "原装",
    "支持",
    "实拍",
    "国行正品",
    "无拆修",
    "充电线",
    "闲置",
    "置换",
    "快递",
)


def domain_label(value: str | None) -> str:
    if not value:
        return "Unknown"
    return DOMAIN_LABELS.get(value, display_label_for_scope(value))


def format_number(value: int | float | Decimal | None) -> str:
    if value is None:
        return "-"
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f"{value:,}"


def format_currency(value: Decimal | float | int | None) -> str:
    if value is None:
        return "-"
    decimal_value = Decimal(value)
    if decimal_value >= Decimal("10000"):
        return f"¥{decimal_value / Decimal('10000'):.2f}w"
    return f"¥{decimal_value:,.0f}"


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def format_relative(value: datetime | None) -> str:
    if value is None:
        return "-"
    delta = datetime.now(UTC) - value.astimezone(UTC)
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}秒前"
    if seconds < 3600:
        return f"{seconds // 60}分钟前"
    if seconds < 86400:
        return f"{seconds // 3600}小时前"
    return f"{seconds // 86400}天前"


def format_percent(value: Decimal | float | int | None, digits: int = 0) -> str:
    if value is None:
        return "-"
    return f"{float(value):.{digits}f}%"


def pricing_view_label(value: str | None) -> str:
    if not value:
        return "-"
    return PRICING_VIEW_LABELS.get(value, value)


def format_storage_label(storage_gb: int | None) -> str:
    if storage_gb is None:
        return "-"
    if storage_gb >= 1024 and storage_gb % 1024 == 0:
        return f"{storage_gb // 1024}TB"
    return f"{storage_gb}G"


def format_screen_label(screen_size_in: float | Decimal | None) -> str:
    if screen_size_in is None:
        return "-"
    return f"{screen_size_in:g}英寸"


def reliability_tier_label(value: str | None) -> str:
    mapping = {
        "high": "高",
        "medium": "中",
        "watch": "观察",
        "low": "低",
    }
    if not value:
        return "-"
    return mapping.get(value, value)


def actionable_state_label(value: bool) -> str:
    return "机会成立" if value else "仅观察"


def auth_state_label(value: str | None) -> str:
    mapping = {
        "authenticated": "已登录",
        "login_required": "需要登录",
        "unknown": "未知",
        "error": "异常",
    }
    if not value:
        return "未知"
    return mapping.get(value, value)


def run_status_label(value: str | None) -> str:
    mapping = {
        "completed": "完成",
        "running": "运行中",
        "failed": "失败",
        "cancelled": "已取消",
        "pending": "等待中",
    }
    if not value:
        return "-"
    return mapping.get(value, value)


def register_template_filters(templates: Jinja2Templates) -> None:
    templates.env.filters["currency"] = format_currency
    templates.env.filters["number"] = format_number
    templates.env.filters["datetime"] = format_datetime
    templates.env.filters["relative"] = format_relative
    templates.env.filters["percent"] = format_percent
    templates.env.filters["domain_label"] = domain_label
    templates.env.filters["pricing_view_label"] = pricing_view_label
    templates.env.filters["reliability_tier_label"] = reliability_tier_label
    templates.env.filters["actionable_state_label"] = actionable_state_label
    templates.env.filters["auth_state_label"] = auth_state_label
    templates.env.filters["run_status_label"] = run_status_label
