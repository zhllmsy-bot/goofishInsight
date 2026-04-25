from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CategoryRuntimeDefault:
    category_code: str
    prompt_profile: str
    extractor_profile: str | None = None
    validator_profile: str | None = None


CATEGORY_RUNTIME_DEFAULTS: dict[str, CategoryRuntimeDefault] = {
    "apple_computer": CategoryRuntimeDefault(
        category_code="apple_computer",
        prompt_profile="apple_computer_extract_v1",
        extractor_profile="default",
        validator_profile="apple_computer_basic_v1",
    ),
    "garmin_watch": CategoryRuntimeDefault(
        category_code="garmin_watch",
        prompt_profile="garmin_watch_extract_v1",
        extractor_profile="default",
        validator_profile="garmin_watch_basic_v1",
    ),
    "camera_interchangeable_lens": CategoryRuntimeDefault(
        category_code="camera_interchangeable_lens",
        prompt_profile="camera_interchangeable_lens_extract_v1",
        extractor_profile="default",
        validator_profile="lens_basic_v1",
    ),
    "camera_body": CategoryRuntimeDefault(
        category_code="camera_body",
        prompt_profile="camera_body_extract_v1",
        extractor_profile="default",
        validator_profile=None,
    ),
    "phone": CategoryRuntimeDefault(
        category_code="phone",
        prompt_profile="smartphone_extract_v1",
        extractor_profile="default",
        validator_profile="smartphone_basic_v1",
    ),
    "apple_airpods": CategoryRuntimeDefault(
        category_code="apple_airpods",
        prompt_profile="apple_airpods_extract_v1",
        extractor_profile="default",
        validator_profile="apple_airpods_basic_v1",
    ),
}


def get_category_runtime_default(category_code: str | None) -> CategoryRuntimeDefault | None:
    normalized = str(category_code or "").strip()
    if not normalized:
        return None
    return CATEGORY_RUNTIME_DEFAULTS.get(normalized)


def recommended_prompt_profile_for_category(category_code: str | None) -> str | None:
    default = get_category_runtime_default(category_code)
    if default is None:
        return None
    return default.prompt_profile
