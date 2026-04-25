from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from .application.services.rule_alias_matcher import match_rule_alias
from .category_compat import is_apple_computer_scope, is_garmin_watch_scope, resolve_category_code
from .compat import UTC

DEFAULT_PRICE_SANITY_RANGES_PATH = Path(__file__).resolve().parents[2] / "configs" / "price_sanity_ranges.yaml"
PRICE_SANITY_MIN_SAMPLE_COUNT = 100

FORERUNNER_MODEL_RE = re.compile(
    r"(?:forerunner\s*)?(965|955|945|265s?|255s?|245m?|165|55)(?!\d)",
    re.IGNORECASE,
)
MARQ_VARIANT_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Athlete", ("athlete", "\u9886\u8dd1\u8005")),
    ("Golfer", ("golfer", "\u9ad8\u5c14\u592b")),
    ("Aviator", ("aviator", "\u98de\u884c\u5bb6")),
    ("Captain", ("captain", "\u822a\u6d77\u5bb6")),
    ("Adventurer", ("adventurer", "\u63a2\u9669\u5bb6")),
    ("Driver", ("driver", "\u9a7e\u9a76\u8005")),
    ("Commander", ("commander", "\u6307\u6325\u5b98")),
)

PRICE_FEN_THRESHOLD = Decimal("100000")
PRICE_FEN_DIVISOR = Decimal("100")
DOMAIN_PRICE_CAPS: dict[str, Decimal] = {
    "apple_computer": Decimal("60000"),
    "garmin_watch": Decimal("10000"),
}
APPLE_FAMILY_PRICE_CAPS: dict[str, Decimal] = {
    "Mac Studio": Decimal("60000"),
    "MacBook Pro": Decimal("50000"),
    "MacBook Air": Decimal("30000"),
    "Mac mini": Decimal("30000"),
    "iMac": Decimal("30000"),
}
GARMIN_FAMILY_PRICE_CAPS: dict[str, Decimal] = {
    "MARQ": Decimal("30000"),
    "Tactix": Decimal("15000"),
    "Descent": Decimal("15000"),
    "Fenix": Decimal("8000"),
    "Epix": Decimal("8000"),
    "Enduro": Decimal("8000"),
    "Forerunner": Decimal("6000"),
    "Instinct": Decimal("6000"),
    "Venu": Decimal("6000"),
    "Approach": Decimal("6000"),
}


@dataclass(slots=True)
class ExtractedItem:
    item_id: str
    title: str
    price: Decimal | None
    pic_url: str | None
    seller_name: str | None
    seller_avatar_url: str | None
    area: str | None
    publish_time: datetime | None
    tags: list[str]
    seller_id: str | None
    c_cat_id: str | None
    cat_id: str | None
    tb_cat_id: str | None
    is_auction: bool
    is_ad: bool
    has_video: bool
    listing_url: str | None
    normalized_brand: str | None
    normalized_model_family: str | None
    normalized_model: str | None
    normalized_chip: str | None
    normalized_memory_gb: int | None
    normalized_storage_gb: int | None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def compact_watch_text(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def pick_unique_marq_variant(title: str, lowered: str) -> str | None:
    compact_title = compact_watch_text(title)
    compact_lowered = compact_watch_text(lowered)
    matches: list[str] = []
    for label, tokens in MARQ_VARIANT_ALIASES:
        if any(compact_watch_text(token) in compact_title or compact_watch_text(token) in compact_lowered for token in tokens):
            matches.append(label)
    unique_matches = list(dict.fromkeys(matches))
    if len(unique_matches) == 1:
        return unique_matches[0]
    return None


def pick_garmin_family_v2(title: str, lowered: str) -> str | None:
    compact_title = compact_watch_text(title)
    compact_lowered = compact_watch_text(lowered)
    if "fenix" in lowered or "椋炶€愭椂" in title:
        return "Fenix"
    if "epix" in lowered:
        return "Epix"
    if "instinct" in lowered or "鏈兘" in title:
        return "Instinct"
    if "marq" in compact_lowered or "\u9a6c\u514b" in compact_title:
        return "MARQ"
    if "forerunner" in lowered or "\u9886\u8dd1\u8005" in compact_title:
        return "Forerunner"
    if "venu" in lowered:
        return "Venu"
    if "approach" in lowered:
        return "Approach"
    if re.search(r"\bmk\s*[12]\b", lowered) or re.search(r"\bmk[12]\b", lowered):
        return "Descent"
    if re.search(r"(?:浣虫槑|garmin)\s*(965|955|945|265s?|255s?|245m?|165|55)(?!\d)", title, re.IGNORECASE):
        return "Forerunner"
    return None


def pick_garmin_model_v2(title: str, lowered: str, family: str | None) -> str | None:
    if family == "Fenix":
        return pick_garmin_model(title, lowered, family)
    if family == "Epix":
        return pick_garmin_model(title, lowered, family)
    if family == "Instinct":
        return pick_garmin_model(title, lowered, family)
    if family == "Forerunner":
        match = FORERUNNER_MODEL_RE.search(lowered)
        if match:
            return f"Forerunner {match.group(1).upper()}"
        return "Forerunner"
    if family == "Approach":
        return pick_garmin_model(title, lowered, family)
    if family == "MARQ":
        variant = pick_unique_marq_variant(title, lowered)
        if variant:
            return f"MARQ {variant}"
        return "MARQ"
    if family == "Descent":
        return pick_garmin_model(title, lowered, family)
    if family == "Venu":
        return pick_garmin_model(title, lowered, family)
    return pick_garmin_model(title, lowered, family)


def pick_garmin_family_v3(title: str, lowered: str) -> str | None:
    compact_title = compact_watch_text(title)
    compact_lowered = compact_watch_text(lowered)
    if "fenix" in compact_lowered or "\u98de\u8010\u65f6" in compact_title:
        return "Fenix"
    if "epix" in compact_lowered:
        return "Epix"
    if "instinct" in compact_lowered or "\u672c\u80fd" in compact_title:
        return "Instinct"
    if "marq" in compact_lowered:
        return "MARQ"
    if "forerunner" in compact_lowered or "\u9886\u8dd1\u8005" in compact_title:
        return "Forerunner"
    if "venu" in compact_lowered:
        return "Venu"
    if "approach" in compact_lowered:
        return "Approach"
    if re.search(r"\bmk\s*[12]\b", compact_lowered) or re.search(r"\bmk[12]\b", compact_lowered):
        return "Descent"
    if re.search(r"(?:\u4f73\u660e|garmin)\s*(965|955|945|265s?|255s?|245m?|165|55)(?!\d)", compact_title, re.IGNORECASE):
        return "Forerunner"
    return None


def pick_garmin_model_v3(title: str, lowered: str, family: str | None) -> str | None:
    if family == "Forerunner":
        match = FORERUNNER_MODEL_RE.search(lowered)
        if match:
            return f"Forerunner {match.group(1).upper()}"
        return "Forerunner"
    if family == "MARQ":
        variant = pick_unique_marq_variant(title, lowered)
        if variant:
            return f"MARQ {variant}"
        return "MARQ"
    return pick_garmin_model(title, lowered, family)


def extract_items_from_response(response: dict[str, Any]) -> list[ExtractedItem]:
    result_list = response.get("data", {}).get("resultList", [])
    items: list[ExtractedItem] = []

    for result in result_list:
        main = result.get("data", {}).get("item", {}).get("main", {})
        ex_content = main.get("exContent", {})
        click_param = main.get("clickParam", {})
        args = click_param.get("args", {})

        item_id = ex_content.get("itemId") or args.get("id")
        if not item_id:
            continue

        title = ex_content.get("title", "").strip()
        normalized = normalize_title(title)

        items.append(
            ExtractedItem(
                item_id=item_id,
                title=title,
                price=extract_price(ex_content.get("price")),
                pic_url=ex_content.get("picUrl"),
                seller_name=ex_content.get("userNickName"),
                seller_avatar_url=ex_content.get("userAvatarUrl"),
                area=ex_content.get("area"),
                publish_time=parse_publish_time(args.get("publishTime")),
                tags=extract_tags(ex_content.get("fishTags", {})),
                seller_id=args.get("seller_id"),
                c_cat_id=args.get("cCatId"),
                cat_id=args.get("catId"),
                tb_cat_id=args.get("tbCatId"),
                is_auction=bool(ex_content.get("isAuction")),
                is_ad=bool(ex_content.get("isAliMaMaAD")),
                has_video=bool(ex_content.get("showVideoIcon")),
                listing_url=build_listing_url(item_id, args),
                normalized_brand=normalized["brand"],
                normalized_model_family=normalized["model_family"],
                normalized_model=normalized["model"],
                normalized_chip=normalized["chip"],
                normalized_memory_gb=normalized["memory_gb"],
                normalized_storage_gb=normalized["storage_gb"],
            )
        )

    return items


def extract_metadata(response: dict[str, Any]) -> dict[str, Any]:
    result_info = response.get("data", {}).get("resultInfo", {})
    control = result_info.get("searchResControlFields", {})
    return {
        "has_next_page": bool(result_info.get("hasNextPage") or control.get("nextPage")),
        "num_found": control.get("numFound"),
        "max_price": control.get("maxPrice"),
        "min_price": control.get("minPrice"),
    }


def extract_price(price_array: list[dict[str, Any]] | None) -> Decimal | None:
    if not price_array:
        return None

    integer_part = next(
        (item.get("text") for item in price_array if item.get("type") == "integer"),
        None,
    )
    if integer_part is None:
        return None

    try:
        return normalize_market_price(Decimal(str(integer_part)))
    except InvalidOperation:
        return None


def normalize_market_price(
    value: Decimal | None,
    *,
    business_domain: str | None = None,
    model_family: str | None = None,
) -> Decimal | None:
    if value is None:
        return None
    normalized = value
    if normalized >= PRICE_FEN_THRESHOLD:
        normalized = (normalized / PRICE_FEN_DIVISOR).quantize(Decimal("0.01"))

    price_cap = infer_price_cap(
        business_domain=business_domain,
        model_family=model_family,
    )
    if price_cap is not None:
        while normalized > price_cap and normalized >= Decimal("1000"):
            normalized = (normalized / Decimal("10")).quantize(Decimal("0.01"))
    return normalized


def infer_price_cap(*, business_domain: str | None, model_family: str | None) -> Decimal | None:
    category_code = resolve_category_code(business_domain)
    if is_apple_computer_scope(category_code):
        if model_family in APPLE_FAMILY_PRICE_CAPS:
            return APPLE_FAMILY_PRICE_CAPS[model_family]
        return DOMAIN_PRICE_CAPS[category_code]
    if is_garmin_watch_scope(category_code):
        if model_family in GARMIN_FAMILY_PRICE_CAPS:
            return GARMIN_FAMILY_PRICE_CAPS[model_family]
        return DOMAIN_PRICE_CAPS[category_code]
    return None


def compute_price_sanity_score(
    *,
    price: Decimal | float | int | str | None,
    category_code: str | None,
    historical_prices: list[Decimal | float | int | str] | None = None,
    ranges_path: Path | None = None,
) -> dict[str, Any]:
    numeric_price = _to_float_price(price)
    if numeric_price is None:
        return {
            "score": 0.0,
            "verdict": "invalid_price",
            "reason": "price_unavailable",
            "method": "manual_fallback",
            "sample_count": int(len(historical_prices or [])),
            "range_low": None,
            "range_high": None,
        }

    scoped_category = resolve_category_code(category_code)
    historical_series = _normalize_historical_prices(historical_prices or [])
    if len(historical_series) >= PRICE_SANITY_MIN_SAMPLE_COUNT:
        low, high = _historical_price_band(historical_series)
        method = "historical_quantile"
    else:
        low, high = _manual_price_band(
            category_code=scoped_category,
            ranges_path=ranges_path,
        )
        method = "manual_fallback"

    score, verdict, reason = _evaluate_price_against_band(
        price=numeric_price,
        low=low,
        high=high,
    )
    return {
        "score": round(score, 4),
        "verdict": verdict,
        "reason": reason,
        "method": method,
        "sample_count": len(historical_series),
        "range_low": low,
        "range_high": high,
    }


def _to_float_price(value: Decimal | float | int | str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_historical_prices(values: list[Decimal | float | int | str]) -> list[float]:
    normalized: list[float] = []
    for value in values:
        numeric = _to_float_price(value)
        if numeric is None or numeric <= 0:
            continue
        normalized.append(numeric)
    normalized.sort()
    return normalized


def _historical_price_band(values: list[float]) -> tuple[float, float]:
    lower_quantile = statistics.quantiles(values, n=100, method="inclusive")[4]
    upper_quantile = statistics.quantiles(values, n=100, method="inclusive")[94]
    if upper_quantile < lower_quantile:
        lower_quantile, upper_quantile = upper_quantile, lower_quantile
    return float(lower_quantile), float(upper_quantile)


def _evaluate_price_against_band(*, price: float, low: float, high: float) -> tuple[float, str, str]:
    if low <= price <= high:
        width = max(high - low, 1.0)
        center = (low + high) / 2.0
        distance = abs(price - center)
        score = max(0.0, 1.0 - (distance / (width / 2.0 + 1.0)))
        return score, "normal", "within_expected_band"

    if price < low:
        gap_ratio = (low - price) / max(low, 1.0)
        score = max(0.0, 0.7 - gap_ratio)
        return score, "low_outlier", "below_expected_band"

    gap_ratio = (price - high) / max(high, 1.0)
    score = max(0.0, 0.7 - gap_ratio)
    return score, "high_outlier", "above_expected_band"


def _manual_price_band(*, category_code: str | None, ranges_path: Path | None = None) -> tuple[float, float]:
    ranges = _load_price_sanity_ranges(str((ranges_path or DEFAULT_PRICE_SANITY_RANGES_PATH).resolve()))
    key = resolve_category_code(category_code)
    entry = ranges.get(key) or ranges.get("default")
    if not isinstance(entry, dict):
        return 0.0, 999999.0
    low = _to_float_price(entry.get("min_price")) or 0.0
    high = _to_float_price(entry.get("max_price")) or 999999.0
    if high < low:
        low, high = high, low
    return low, high


@lru_cache(maxsize=4)
def _load_price_sanity_ranges(path_str: str) -> dict[str, dict[str, Any]]:
    path = Path(path_str)
    if not path.exists():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    current_key: str | None = None
    current_payload: dict[str, Any] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not raw_line.startswith(" ") and line.endswith(":"):
            if current_key is not None:
                rows[current_key] = dict(current_payload)
            current_key = line[:-1].strip()
            current_payload = {}
            continue
        if current_key is None or ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        value = raw_value.strip()
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            value = value[1:-1]
        else:
            parsed = _parse_numeric(value)
            if parsed is not None:
                current_payload[key.strip()] = parsed
                continue
        current_payload[key.strip()] = value
    if current_key is not None:
        rows[current_key] = dict(current_payload)
    return rows


def _parse_numeric(value: str) -> int | float | None:
    if not value:
        return None
    if re.fullmatch(r"-?\d+", value):
        try:
            return int(value)
        except ValueError:
            return None
    if re.fullmatch(r"-?\d+\.\d+", value):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def extract_tags(fish_tags: dict[str, Any]) -> list[str]:
    values: list[str] = []
    tag_list = fish_tags.get("r2", {}).get("tagList", [])
    for tag in tag_list:
        content = tag.get("data", {}).get("content")
        if content:
            values.append(content)
    return values


def parse_publish_time(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        timestamp_ms = int(value)
    except ValueError:
        return None

    return datetime.fromtimestamp(timestamp_ms / 1000, tz=UTC)


def build_listing_url(item_id: str, args: dict[str, Any]) -> str:
    query = {"id": item_id}
    if args.get("catId"):
        query["categoryId"] = args["catId"]
    return f"https://www.goofish.com/item?{urlencode(query)}"


def normalize_title(title: str) -> dict[str, Any]:
    lowered = title.lower()
    garmin_family_alias = match_rule_alias(
        title=title,
        category_code="garmin_watch",
        field="model_family",
    )
    apple_family_alias = match_rule_alias(
        title=title,
        category_code="apple_computer",
        field="model_family",
    )

    brand = None
    model_family = None
    model = None
    chip = None
    memory_gb = None
    storage_gb = None

    if is_garmin_watch_title(title, lowered) or garmin_family_alias is not None:
        brand = "Garmin"
        model_family = (
            garmin_family_alias.value
            if garmin_family_alias is not None and garmin_family_alias.confidence >= 0.6
            else None
        ) or pick_garmin_family_v3(title, lowered)
        model = pick_garmin_model_v3(title, lowered, model_family)
    elif is_apple_computer_title(title, lowered) or apple_family_alias is not None:
        brand = "Apple"
        model_family = (
            apple_family_alias.value
            if apple_family_alias is not None and apple_family_alias.confidence >= 0.6
            else None
        ) or pick_apple_family(lowered)
        chip = pick_chip(lowered)
        memory_gb, storage_gb = pick_apple_specs(lowered)

    memory_gb = memory_gb or pick_memory_gb(lowered)
    storage_gb = storage_gb or pick_storage_gb(lowered)

    if brand == "Apple":
        model = pick_apple_model(
            lowered=lowered,
            family=model_family,
            chip=chip,
            memory_gb=memory_gb,
            storage_gb=storage_gb,
        )

    if model is None:
        model = pick_model(title)

    return {
        "brand": brand,
        "model_family": model_family,
        "model": model,
        "chip": chip,
        "memory_gb": memory_gb,
        "storage_gb": storage_gb,
    }


def pick_model(title: str) -> str | None:
    tokens = [token.strip() for token in title.replace("/", " ").split() if token.strip()]
    if not tokens:
        return None
    return " ".join(tokens[:4])[:128]


def pick_chip(text: str) -> str | None:
    for candidate in ("m4", "m3", "m2", "m1"):
        if candidate in text:
            return candidate.upper()
    return None


def pick_memory_gb(text: str) -> int | None:
    for value in (8, 16, 18, 24, 32, 36, 48, 64, 96, 128):
        if f"{value}g" in text and any(token in text for token in ("内存", "ram", "运存", "unified")):
            return value
    return None


def pick_storage_gb(text: str) -> int | None:
    tb_map = {"1tb": 1024, "2tb": 2048, "4tb": 4096, "8tb": 8192}
    for marker, value in tb_map.items():
        if marker in text:
            return value

    for value in (128, 256, 512):
        if f"{value}g" in text and any(token in text for token in ("硬盘", "存储", "ssd")):
            return value

    return None


def pick_apple_specs(text: str) -> tuple[int | None, int | None]:
    compact = re.sub(r"\s+", " ", text)
    match = re.search(
        r"(?:m[1-4]\s+)?(8|16|18|24|32|36|48|64|96|128)g(?:\s+|/|-)(128|256|512)g",
        compact,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1)), int(match.group(2))

    match = re.search(
        r"(?:m[1-4]\s+)?(8|16|18|24|32|36|48|64|96|128)g(?:\s+|/|-)(1|2|4|8)tb",
        compact,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1)), int(match.group(2)) * 1024

    return None, None


def is_garmin_watch_title(title: str, lowered: str) -> bool:
    if "garmin" not in lowered and "佳明" not in title:
        return False

    accessory_terms = (
        "表带",
        "表链",
        "表壳",
        "保护壳",
        "保护膜",
        "贴膜",
        "充电线",
        "配件",
        "码表架",
        "支架",
        "手持导航",
        "导航仪",
        "码表",
    )
    watch_terms = (
        "手表",
        "腕表",
        "表盘",
        "fenix",
        "epix",
        "instinct",
        "forerunner",
        "venu",
        "approach",
        "marq",
        "飞耐时",
        "本能",
        "领跑者",
        "高尔夫",
        "潜水",
    )
    has_watch_signal = any(term in lowered for term in watch_terms) or any(term in title for term in watch_terms)
    has_model_signal = bool(
        re.search(r"(?:佳明|garmin)\s*(965|955|945|265s?|255s?|245m?|165|55)\b", title, re.IGNORECASE)
    )
    if any(term in title for term in accessory_terms) and not (has_watch_signal or has_model_signal):
        return False

    return has_watch_signal or has_model_signal


def pick_garmin_family(title: str, lowered: str) -> str | None:
    if "fenix" in lowered or "飞耐时" in title:
        return "Fenix"
    if "epix" in lowered:
        return "Epix"
    if "instinct" in lowered or "本能" in title:
        return "Instinct"
    if "forerunner" in lowered or "领跑者" in title:
        return "Forerunner"
    if "venu" in lowered:
        return "Venu"
    if "approach" in lowered:
        return "Approach"
    if "marq" in lowered or "马克" in title:
        return "MARQ"
    if re.search(r"\bmk\s*[12]\b", lowered) or re.search(r"\bmk[12]\b", lowered):
        return "Descent"
    if re.search(r"(?:佳明|garmin)\s*(965|955|945|265s?|255s?|245m?|165|55)\b", title, re.IGNORECASE):
        return "Forerunner"
    return None


def pick_garmin_model(title: str, lowered: str, family: str | None) -> str | None:
    if family == "Fenix":
        match = re.search(
            r"fenix\s*(\d{1,2})(x|s)?(?:\s*(pro|plus))?(?:\s*(solar|sapphire|amoled))?(?:\s*(\d{2}mm))?",
            lowered,
            re.IGNORECASE,
        )
        if match:
            parts = ["Fenix", match.group(1)]
            if match.group(2):
                parts[-1] = f"{parts[-1]}{match.group(2).upper()}"
            for extra in (match.group(3), match.group(4), match.group(5)):
                if extra:
                    if extra.lower() == "amoled":
                        parts.append("AMOLED")
                    elif extra.lower().endswith("mm"):
                        parts.append(extra.lower())
                    else:
                        parts.append(extra.title())
            return " ".join(parts)
        return "Fenix"

    if family == "Epix":
        match = re.search(r"epix(?:\s*(pro))?(?:\s*(gen\s*2|2))?", lowered, re.IGNORECASE)
        if match:
            parts = ["Epix"]
            if match.group(1):
                parts.append("Pro")
            if match.group(2):
                parts.append("Gen 2")
            return " ".join(parts)
        return "Epix"

    if family == "Instinct":
        match = re.search(r"instinct(?:\s*(2x?|crossover))?(?:\s*(solar))?", lowered, re.IGNORECASE)
        if match:
            parts = ["Instinct"]
            if match.group(1):
                value = match.group(1)
                parts.append(value.upper() if value.lower().startswith("2") else value.title())
            if match.group(2):
                parts.append("Solar")
            return " ".join(parts)
        if "太阳能" in title:
            return "Instinct Solar"
        return "Instinct"

    if family == "Forerunner":
        match = re.search(r"(?:forerunner\s*)?(965|955|945|265s?|255s?|245m?|165|55)\b", lowered, re.IGNORECASE)
        if match:
            return f"Forerunner {match.group(1).upper()}"
        return "Forerunner"

    if family == "Approach":
        match = re.search(r"approach\s*([sgx]?\d{2,3})", lowered, re.IGNORECASE)
        if match:
            return f"Approach {match.group(1).upper()}"
        return "Approach"

    if family == "MARQ":
        match = re.search(r"marq\s*(golfer|athlete|aviator|captain|driver|adventurer)", lowered, re.IGNORECASE)
        if match:
            return f"MARQ {match.group(1).title()}"
        if "高尔夫" in title:
            return "MARQ Golfer"
        return "MARQ"

    if family == "Descent":
        match = re.search(r"\bmk\s*([12])\b", lowered, re.IGNORECASE) or re.search(r"\bmk([12])\b", lowered, re.IGNORECASE)
        if match:
            return f"Descent MK{match.group(1)}"
        return "Descent"

    if family == "Venu":
        match = re.search(r"venu\s*(\d+|sq|x1)?", lowered, re.IGNORECASE)
        if match and match.group(1):
            return f"Venu {match.group(1).upper()}"
        return "Venu"

    return None


def is_apple_computer_title(title: str, lowered: str) -> bool:
    families = ("macbook air", "macbook pro", "mac mini", "mac studio", "imac")
    if not any(term in lowered for term in families) and "苹果" not in title:
        return False

    accessory_terms = (
        "保护壳",
        "保护套",
        "贴膜",
        "键盘膜",
        "电脑包",
        "扩展坞",
        "充电器",
        "数据线",
        "外壳",
    )
    return not any(term in title for term in accessory_terms)


def pick_apple_family(lowered: str) -> str | None:
    if "macbook air" in lowered:
        return "MacBook Air"
    if "macbook pro" in lowered:
        return "MacBook Pro"
    if "mac mini" in lowered:
        return "Mac mini"
    if "mac studio" in lowered:
        return "Mac Studio"
    if "imac" in lowered:
        return "iMac"
    return None


def pick_apple_model(
    *,
    lowered: str,
    family: str | None,
    chip: str | None,
    memory_gb: int | None,
    storage_gb: int | None,
) -> str | None:
    if family is None:
        return None

    size = None
    if family in {"MacBook Air", "MacBook Pro", "iMac"}:
        size_match = re.search(r"\b(13(?:\.\d)?|14(?:\.\d)?|15(?:\.\d)?|16|24)\b", lowered)
        if size_match:
            size = size_match.group(1).split(".")[0]

    parts = [family]
    if size:
        parts.append(size)
    if chip:
        parts.append(chip)
    if memory_gb:
        parts.append(f"{memory_gb}G")
    if storage_gb:
        parts.append(f"{storage_gb}G")
    return " ".join(parts)
