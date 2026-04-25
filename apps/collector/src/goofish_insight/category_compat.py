from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryScopeProfile:
    category_code: str
    display_name: str
    legacy_business_domains: tuple[str, ...]
    token_aliases: tuple[str, ...]
    prompt_profile: str


CATEGORY_SCOPE_PROFILES: dict[str, CategoryScopeProfile] = {
    "camera_interchangeable_lens": CategoryScopeProfile(
        category_code="camera_interchangeable_lens",
        display_name="可换镜头",
        legacy_business_domains=("camera_interchangeable_lens",),
        token_aliases=("镜头", "尼康", "佳能", "索尼", "富士", "腾龙", "适马", "s line", "gm", "art", "xf", "rf", "fe"),
        prompt_profile="lens_extract_v1",
    ),
    "camera_body": CategoryScopeProfile(
        category_code="camera_body",
        display_name="相机机身",
        legacy_business_domains=("camera_body",),
        token_aliases=("机身", "相机", "尼康", "佳能", "索尼", "富士", "zf", "z8", "a7", "r6", "xt5"),
        prompt_profile="camera_body_extract_v1",
    ),
    "graphics_card": CategoryScopeProfile(
        category_code="graphics_card",
        display_name="显卡",
        legacy_business_domains=("graphics_card",),
        token_aliases=("显卡", "rtx", "rx", "英伟达", "nvidia", "amd", "华硕", "七彩虹", "微星", "技嘉"),
        prompt_profile="graphics_card_extract_v1",
    ),
    "phone": CategoryScopeProfile(
        category_code="phone",
        display_name="手机",
        legacy_business_domains=("phone",),
        token_aliases=("手机", "iphone", "苹果", "华为", "小米", "vivo", "oppo", "荣耀"),
        prompt_profile="phone_extract_v1",
    ),
    "garmin_watch": CategoryScopeProfile(
        category_code="garmin_watch",
        display_name="Garmin手表",
        legacy_business_domains=("garmin", "garmin_watch"),
        token_aliases=("garmin", "佳明", "fenix", "epix", "forerunner", "instinct", "marq", "venu", "approach"),
        prompt_profile="garmin_watch_extract_v1",
    ),
    "apple_computer": CategoryScopeProfile(
        category_code="apple_computer",
        display_name="Apple电脑",
        legacy_business_domains=("apple_m_series", "apple_computer"),
        token_aliases=("apple", "苹果", "macbook", "mac mini", "mac studio", "imac", "m1", "m2", "m3", "m4"),
        prompt_profile="apple_computer_extract_v1",
    ),
    "apple_airpods": CategoryScopeProfile(
        category_code="apple_airpods",
        display_name="Apple耳机",
        legacy_business_domains=("apple_airpods",),
        token_aliases=("airpods", "airpodspro", "airpods max", "pro2", "pro 2", "充电盒", "耳机", "耳塞"),
        prompt_profile="apple_airpods_extract_v1",
    ),
}

_SCOPE_TO_CANONICAL: dict[str, str] = {}
for _category_code, _profile in CATEGORY_SCOPE_PROFILES.items():
    for _alias in (_category_code, *_profile.legacy_business_domains):
        _SCOPE_TO_CANONICAL[str(_alias).strip()] = _category_code


NON_ANALYTICS_SCOPE_CODES: frozenset[str] = frozenset(
    {
        "xianyu_onboarding",
    }
)

CATEGORY_COMPAT_RETIREMENT_PLAN: tuple[dict[str, str], ...] = (
    {
        "phase": "phase_2",
        "scope": "admin/backfill entrypoints",
        "goal": "Prefer category_code input and keep business_domain as compatibility alias only.",
    },
    {
        "phase": "phase_3_pre_cutover",
        "scope": "dashboard/pricing/review parity checks",
        "goal": "Validate category-first contract parity for 7 consecutive days before removing legacy aliases.",
    },
    {
        "phase": "phase_3_cutover",
        "scope": "service boundary cleanup",
        "goal": "Drop business_domain-only public parameters after compatibility consumers are migrated.",
    },
)

CATEGORY_COMPAT_RETIREMENT_STOP_CONDITIONS: tuple[str, ...] = (
    "At least one week of dashboard and pricing category-first parity with no P1 regression.",
    "Admin/backfill automation no longer calls business_domain-only arguments.",
    "Catalog dual-read contract and rollback checks stay green after category-first cutover.",
)


def normalize_scope_key(value: str | None) -> str:
    return str(value or "").strip()


def resolve_category_code(value: str | None) -> str:
    normalized = normalize_scope_key(value)
    if not normalized:
        return ""
    return _SCOPE_TO_CANONICAL.get(normalized, normalized)


def is_analytics_scope(value: str | None) -> bool:
    normalized = normalize_scope_key(value)
    if not normalized:
        return False
    canonical = resolve_category_code(normalized)
    return canonical not in NON_ANALYTICS_SCOPE_CODES and normalized not in NON_ANALYTICS_SCOPE_CODES


def non_analytics_scope_codes() -> tuple[str, ...]:
    return tuple(sorted(NON_ANALYTICS_SCOPE_CODES))


def get_category_scope_profile(value: str | None) -> CategoryScopeProfile | None:
    canonical_code = resolve_category_code(value)
    if not canonical_code:
        return None
    return CATEGORY_SCOPE_PROFILES.get(canonical_code)


def compatible_scope_keys(value: str | None) -> tuple[str, ...]:
    normalized = normalize_scope_key(value)
    profile = get_category_scope_profile(normalized)
    ordered: list[str] = []
    for candidate in (
        normalized,
        resolve_category_code(normalized),
        *(profile.legacy_business_domains if profile is not None else ()),
    ):
        candidate_text = normalize_scope_key(candidate)
        if candidate_text and candidate_text not in ordered:
            ordered.append(candidate_text)
    return tuple(ordered)


def preferred_legacy_business_domain(value: str | None) -> str:
    profile = get_category_scope_profile(value)
    if profile is None:
        return normalize_scope_key(value)
    return profile.legacy_business_domains[0]


def display_label_for_scope(value: str | None) -> str:
    normalized = normalize_scope_key(value)
    if not normalized:
        return "Unknown"
    profile = get_category_scope_profile(normalized)
    if profile is None:
        return normalized.replace("_", " ").title()
    return profile.display_name


def token_aliases_for_scope(value: str | None) -> tuple[str, ...]:
    profile = get_category_scope_profile(value)
    if profile is None:
        return ()
    return profile.token_aliases


def is_garmin_watch_scope(value: str | None) -> bool:
    return resolve_category_code(value) == "garmin_watch"


def is_apple_computer_scope(value: str | None) -> bool:
    return resolve_category_code(value) == "apple_computer"


def category_compat_retirement_summary() -> dict[str, object]:
    return {
        "milestones": CATEGORY_COMPAT_RETIREMENT_PLAN,
        "stop_conditions": CATEGORY_COMPAT_RETIREMENT_STOP_CONDITIONS,
    }
