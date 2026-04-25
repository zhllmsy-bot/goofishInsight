from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Category, CategoryModelAlias, CategoryModelCatalog, Item
from .review_v3_profiles import ReviewV3Profile

V3_STATUS_REJECTED_STATIC_GUARD = "REJECTED_STATIC_GUARD"
V3_STATUS_REJECTED_ACCESSORY = "REJECTED_ACCESSORY"
V3_STATUS_PENDING_REVIEW = "PENDING_REVIEW"
V3_STATUS_VALID_READY_FOR_PRICING = "VALID_READY_FOR_PRICING"
V3_STATUS_MANUAL_AUDIT_REQUIRED = "MANUAL_AUDIT_REQUIRED"
V3_STATUS_INVALID_OR_NOT_SUPPORTED = "INVALID_OR_NOT_SUPPORTED"

BRAND_ALIASES = {
    "apple": "apple",
    "苹果": "apple",
    "garmin": "garmin",
    "佳明": "garmin",
    "nikon": "nikon",
    "尼康": "nikon",
    "canon": "canon",
    "佳能": "canon",
    "sony": "sony",
    "索尼": "sony",
    "sigma": "sigma",
    "适马": "sigma",
    "tamron": "tamron",
    "腾龙": "tamron",
    "viltrox": "viltrox",
    "唯卓仕": "viltrox",
}

ROMAN_NUMERAL_BY_DIGIT = {
    "2": "ii",
    "3": "iii",
    "4": "iv",
    "5": "v",
    "6": "vi",
    "7": "vii",
}


@dataclass(frozen=True)
class CatalogCandidate:
    model_catalog_id: str
    model_code: str
    model_name: str
    brand_name: str | None
    alias_text: str | None
    score: float
    reasons: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "model_catalog_id": self.model_catalog_id,
            "model_code": self.model_code,
            "name": self.model_name,
            "brand": self.brand_name,
            "alias": self.alias_text,
            "score": round(self.score, 4),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class MappingDecision:
    resolution_status: str
    model_catalog_id: str | None
    candidate_payload: list[dict[str, Any]]
    mapping_payload: dict[str, Any]


def normalize_brand(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    direct = BRAND_ALIASES.get(text)
    if direct is not None:
        return direct
    parts = [part.strip() for part in re.split(r"[\/|,，\s]+", text) if part.strip()]
    for part in parts:
        mapped = BRAND_ALIASES.get(part)
        if mapped is not None:
            return mapped
    for alias, mapped in BRAND_ALIASES.items():
        if alias and alias in text:
            return mapped
    return text


def normalize_text_token(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    text = text.replace("毫米", "mm").replace("卡口", "")
    text = text.replace("f ", "f/")
    text = re.sub(r"\s+", " ", text)
    return text


def compact_text(value: Any) -> str:
    text = normalize_text_token(value) or ""
    return re.sub(r"[^a-z0-9]+", "", text)


def _garmin_model_hint_bonus(model_hint: str | None, haystacks: list[str]) -> tuple[float, str | None]:
    if not model_hint:
        return 0.0, None
    if any(hay == model_hint or hay.endswith(model_hint) for hay in haystacks if hay):
        return 0.30, "model_hint_exact_match"
    if any(model_hint in hay for hay in haystacks if hay):
        return 0.20, "model_hint_match"
    return 0.0, None


def garmin_model_hint_tokens(value: Any) -> tuple[str, ...]:
    raw = normalize_text_token(value) or ""
    compact = compact_text(value)
    tokens: set[str] = {compact} if compact else set()
    patterns = (
        r"(forerunner)\s*(\d{3}s?)",
        r"(venu)\s*(\d(?:\s*plus|\s*s)?)",
        r"(fenix)\s*(\d(?:\s*pro)?)",
        r"(epix)\s*(pro)?",
        r"(tactix)\s*(\d(?:\s*amoled)?)",
        r"(instinct)\s*(2x|2|solar)?",
    )
    for pattern in patterns:
        match = re.search(pattern, raw, re.I)
        if not match:
            continue
        token = compact_text("".join(part for part in match.groups(default="") if part))
        if token:
            tokens.add(token)
        prefix = compact_text(match.group(1))
        suffix = compact_text("".join(match.groups(default="")[1:]))
        if prefix and suffix:
            tokens.add(f"{prefix}{suffix}")
    return tuple(sorted(token for token in tokens if token))


def camera_body_model_hint_tokens(value: Any) -> tuple[str, ...]:
    token = compact_text(value)
    if not token:
        return ()
    tokens: set[str] = {token}

    def _add(pattern: str, builder) -> None:
        match = re.fullmatch(pattern, token)
        if match:
            built = builder(match)
            if built:
                tokens.add(built)

    _add(r"a7m([2-7])(a?)", lambda m: f"a7{ROMAN_NUMERAL_BY_DIGIT.get(m.group(1), m.group(1))}{m.group(2)}")
    _add(r"a7r([2-7])(a?)", lambda m: f"a7r{ROMAN_NUMERAL_BY_DIGIT.get(m.group(1), m.group(1))}{m.group(2)}")
    _add(r"a7rm([2-7])(a?)", lambda m: f"a7r{ROMAN_NUMERAL_BY_DIGIT.get(m.group(1), m.group(1))}{m.group(2)}")
    return tuple(sorted(tokens))


def normalize_mount(value: Any) -> str | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if "z" in raw and ("卡口" in raw or raw in {"z", "zkou", "zmount"}):
        return "z"
    if "rf" in raw:
        return "rf"
    if "e" in raw and ("卡口" in raw or raw in {"e", "emount"}):
        return "e"
    if "f" in raw and ("卡口" in raw or raw in {"f", "fmount"}):
        return "f"
    if ("x" in raw and "卡口" in raw) or raw in {"x", "xmount"}:
        return "x"
    if "gfx" in raw:
        return "gfx"
    if ("l" in raw and "卡口" in raw) or raw in {"l", "lmount"}:
        return "l"
    if raw in {"m43", "m4/3", "mft"} or "m43" in compact_text(raw):
        return "m43"
    compact = compact_text(raw)
    if compact in {"z", "rf", "e", "f", "x", "gfx", "l", "m43"}:
        return compact
    return None


def infer_lens_mount(*, model_name: Any, alias_text: Any, model_code: Any) -> str | None:
    raw_values = [str(value or "").strip().lower() for value in (model_name, alias_text, model_code)]
    compact_values = [compact_text(value) for value in raw_values if value]
    if any(("z卡口" in value) or value.startswith("nikkor z") or "_z_" in value for value in raw_values):
        return "z"
    if any("rf卡口" in value or value.startswith("rf") or "_rf_" in value for value in raw_values):
        return "rf"
    if any("e卡口" in value or "_e_" in value for value in raw_values):
        return "e"
    if any("f卡口" in value or "_f_" in value for value in raw_values):
        return "f"
    if any(value.startswith("nikkorz") for value in compact_values):
        return "z"
    return None


def resolve_category(session: Session, *, item: Item, profile: ReviewV3Profile | None = None) -> Category | None:
    preferred_codes: list[str] = []
    if profile and profile.business_domain:
        preferred_codes.append(str(profile.business_domain))
    if item.business_domain and item.business_domain not in preferred_codes:
        preferred_codes.append(str(item.business_domain))
    for code in preferred_codes:
        stmt = select(Category).where(Category.code == code).limit(1)
        category = session.execute(stmt).scalar_one_or_none()
        if category is not None:
            return category
    if item.resolved_category_id:
        category = session.get(Category, item.resolved_category_id)
        if category is not None:
            return category
    return None


def build_catalog_candidates(
    session: Session,
    *,
    item: Item,
    profile: ReviewV3Profile,
    features: dict[str, Any],
) -> list[CatalogCandidate]:
    category = resolve_category(session, item=item, profile=profile)
    if category is None:
        return []

    rows = session.execute(
        select(CategoryModelCatalog, CategoryModelAlias)
        .outerjoin(CategoryModelAlias, CategoryModelAlias.model_id == CategoryModelCatalog.id)
        .where(CategoryModelCatalog.category_id == category.id)
        .where(CategoryModelCatalog.status == "ACTIVE")
    ).all()
    if not rows:
        return []

    normalized_brand = normalize_brand(features.get("brand"))
    focal = compact_text(features.get("focal_length"))
    aperture = compact_text(features.get("aperture"))
    mount = normalize_mount(features.get("mount"))
    product_line = compact_text(features.get("product_line") or features.get("model_hint"))
    model_hint = compact_text(features.get("model_hint"))
    garmin_hint_tokens = garmin_model_hint_tokens(features.get("model_hint"))
    camera_body_hint_tokens = camera_body_model_hint_tokens(features.get("model_hint"))
    chip_family = compact_text(features.get("chip_family"))
    memory_gb = features.get("memory_gb")
    storage_gb = features.get("storage_gb")
    screen_size_in = features.get("screen_size_in")
    case_size_mm = features.get("case_size_mm")
    display_type = compact_text(features.get("display_type"))
    sensor_format = compact_text(features.get("sensor_format"))
    is_solar = features.get("is_solar")
    has_anc = features.get("has_anc")

    candidates: list[CatalogCandidate] = []
    seen_ids: set[str] = set()
    for model, alias in rows:
        if model.id in seen_ids:
            alias_text = getattr(alias, "alias_text", None)
        else:
            alias_text = getattr(alias, "alias_text", None)
        haystacks = [
            compact_text(model.model_name),
            compact_text(model.model_code),
            compact_text(model.series_name),
            compact_text(alias_text),
        ]
        score = 0.0
        reasons: list[str] = []

        candidate_brand = normalize_brand(model.brand_name)
        if normalized_brand and candidate_brand == normalized_brand:
            score += 0.30
            reasons.append("brand_match")

        if profile.business_domain == "camera_interchangeable_lens":
            candidate_mount = infer_lens_mount(
                model_name=model.model_name,
                alias_text=alias_text,
                model_code=model.model_code,
            )
            if mount and candidate_mount and candidate_mount != mount:
                continue
            if focal and any(focal in hay for hay in haystacks if hay):
                score += 0.35
                reasons.append("focal_match")
            if aperture and any(aperture in hay for hay in haystacks if hay):
                score += 0.25
                reasons.append("aperture_match")
            if mount and candidate_mount == mount:
                score += 0.10
                reasons.append("mount_match")
        elif profile.business_domain == "apple_computer":
            if product_line and any(product_line in hay for hay in haystacks if hay):
                score += 0.32
                reasons.append("product_line_match")
            if chip_family and any(chip_family in hay for hay in haystacks if hay):
                score += 0.30
                reasons.append("chip_match")
            if memory_gb and str(memory_gb) in compact_text(model.model_name):
                score += 0.06
                reasons.append("memory_match")
            if storage_gb and str(storage_gb) in compact_text(model.model_name):
                score += 0.06
                reasons.append("storage_match")
            if screen_size_in and compact_text(screen_size_in) in compact_text(model.model_name):
                score += 0.06
                reasons.append("screen_match")
        elif profile.business_domain == "garmin_watch":
            if product_line and any(product_line in hay for hay in haystacks if hay):
                score += 0.32
                reasons.append("product_line_match")
            best_model_hint_bonus = 0.0
            best_model_hint_reason = None
            for token in garmin_hint_tokens or ((model_hint,) if model_hint else ()):
                model_hint_bonus, model_hint_reason = _garmin_model_hint_bonus(token, haystacks)
                if model_hint_bonus > best_model_hint_bonus:
                    best_model_hint_bonus = model_hint_bonus
                    best_model_hint_reason = model_hint_reason
            if best_model_hint_bonus > 0:
                score += best_model_hint_bonus
                if best_model_hint_reason:
                    reasons.append(best_model_hint_reason)
            if case_size_mm and str(case_size_mm) in compact_text(model.model_name):
                score += 0.16
                reasons.append("size_match")
            if display_type and display_type in compact_text(model.model_name):
                score += 0.12
                reasons.append("display_match")
            if is_solar is True and "solar" in compact_text(model.model_name):
                score += 0.12
                reasons.append("solar_match")
            candidate_join = " ".join(haystacks)
            if display_type == "amoled":
                if "amoled" in candidate_join:
                    score += 0.04
                elif "solar" in candidate_join or "mip" in candidate_join:
                    score -= 0.10
            elif display_type == "mip":
                if "amoled" in candidate_join:
                    score -= 0.14
                elif "solar" in candidate_join or "mip" in candidate_join:
                    score += 0.04
            if is_solar is True:
                if "solar" in candidate_join:
                    score += 0.04
                elif "amoled" in candidate_join:
                    score -= 0.08
            elif is_solar is False and "solar" in candidate_join:
                score -= 0.05
        elif profile.business_domain == "camera_body":
            if product_line and any(product_line in hay for hay in haystacks if hay):
                score += 0.25
                reasons.append("product_line_match")
            if camera_body_hint_tokens and any(
                token in hay
                for token in camera_body_hint_tokens
                for hay in haystacks
                if hay
            ):
                score += 0.45
                reasons.append("model_hint_match")
            if mount and any(mount in hay for hay in haystacks if hay):
                score += 0.08
                reasons.append("mount_match")
            if sensor_format and any(sensor_format in hay for hay in haystacks if hay):
                score += 0.08
                reasons.append("sensor_format_match")
        elif profile.business_domain == "phone":
            if product_line and any(product_line in hay for hay in haystacks if hay):
                score += 0.18
                reasons.append("product_line_match")
            if model_hint and any(model_hint in hay for hay in haystacks if hay):
                score += 0.50
                reasons.append("model_hint_match")
            if storage_gb and str(storage_gb) in compact_text(model.model_name):
                score += 0.12
                reasons.append("storage_match")
        elif profile.business_domain == "apple_airpods":
            if product_line and any(product_line in hay for hay in haystacks if hay):
                score += 0.22
                reasons.append("product_line_match")
            if model_hint and any(model_hint in hay for hay in haystacks if hay):
                score += 0.50
                reasons.append("model_hint_match")
            if has_anc is True and any(token in compact_text(model.model_name) for token in ("anc", "pro")):
                score += 0.08
                reasons.append("anc_match")

        if score <= 0:
            continue
        if model.id in seen_ids:
            continue
        seen_ids.add(model.id)
        candidates.append(
            CatalogCandidate(
                model_catalog_id=model.id,
                model_code=model.model_code,
                model_name=model.model_name,
                brand_name=model.brand_name,
                alias_text=alias_text,
                score=score,
                reasons=tuple(reasons),
            )
        )

    candidates.sort(key=lambda row: (-row.score, row.model_name))
    return candidates[: profile.second_pass_candidate_limit]


def map_flat_features(
    session: Session,
    *,
    item: Item,
    profile: ReviewV3Profile,
    features: dict[str, Any],
) -> MappingDecision:
    if not bool(features.get("is_main_product")):
        return MappingDecision(
            resolution_status=V3_STATUS_REJECTED_ACCESSORY,
            model_catalog_id=None,
            candidate_payload=[],
            mapping_payload={
                "mapped": False,
                "reason": "not_main_product",
                "item_type": features.get("item_type"),
            },
        )

    candidates = build_catalog_candidates(session, item=item, profile=profile, features=features)
    payload = [candidate.to_payload() for candidate in candidates]
    if not candidates:
        return MappingDecision(
            resolution_status=V3_STATUS_PENDING_REVIEW,
            model_catalog_id=None,
            candidate_payload=payload,
            mapping_payload={
                "mapped": False,
                "reason": "catalog_candidate_not_found",
            },
        )

    top_candidate = candidates[0]
    confidence = float(features.get("confidence_score") or 0.0)
    if _should_direct_map(
        top_candidate=top_candidate,
        candidates=candidates,
        profile=profile,
        features=features,
        confidence=confidence,
    ):
        return MappingDecision(
            resolution_status=V3_STATUS_VALID_READY_FOR_PRICING,
            model_catalog_id=top_candidate.model_catalog_id,
            candidate_payload=payload,
            mapping_payload={
                "mapped": True,
                "reason": "direct_catalog_match",
                "top_candidate": top_candidate.to_payload(),
                "first_pass_confidence": confidence,
            },
        )

    return MappingDecision(
        resolution_status=V3_STATUS_PENDING_REVIEW,
        model_catalog_id=None,
        candidate_payload=payload,
        mapping_payload={
            "mapped": False,
            "reason": "low_confidence_or_ambiguous",
            "top_candidate": top_candidate.to_payload(),
            "first_pass_confidence": confidence,
        },
    )


def _should_direct_map(
    *,
    top_candidate: CatalogCandidate,
    candidates: list[CatalogCandidate],
    profile: ReviewV3Profile,
    features: dict[str, Any],
    confidence: float,
) -> bool:
    reasons = set(top_candidate.reasons)
    second_score = candidates[1].score if len(candidates) > 1 else 0.0
    if top_candidate.score >= 0.85 and confidence >= profile.direct_map_confidence_threshold:
        return True
    if profile.business_domain == "garmin_watch":
        return (
            top_candidate.score >= 0.82
            and confidence >= 0.7
            and "brand_match" in reasons
            and (
                (
                    "model_hint_exact_match" in reasons
                    and (top_candidate.score - second_score) >= 0.08
                )
                or (
                    {"model_hint_match"} <= reasons
                    and (top_candidate.score - second_score) >= 0.15
                )
            )
        )
    if profile.business_domain == "camera_body":
        return (
            top_candidate.score >= 0.78
            and confidence >= 0.85
            and {"brand_match", "model_hint_match"} <= reasons
        )
    if profile.business_domain == "apple_computer":
        exactish_matches = sum(
            reason in reasons
            for reason in ("memory_match", "storage_match", "screen_match")
        )
        return (
            top_candidate.score >= 0.78
            and confidence >= 0.85
            and {"brand_match", "chip_match"} <= reasons
            and (
                (
                    "product_line_match" in reasons
                    and exactish_matches >= 2
                    and confidence >= 0.9
                )
                or (
                    exactish_matches >= 3
                    and (
                        "product_line_match" in reasons
                        or (top_candidate.score - second_score) >= 0.12
                    )
                )
            )
        )
    return False


def apply_second_pass_resolution(
    *,
    candidate_payload: list[dict[str, Any]],
    review_payload: dict[str, Any],
    features: dict[str, Any],
    profile: ReviewV3Profile,
) -> tuple[str, str | None, dict[str, Any]]:
    if review_payload.get("needs_human"):
        return V3_STATUS_MANUAL_AUDIT_REQUIRED, None, {
            "accepted": False,
            "reason": "model_requested_human",
        }

    resolved_model_code = str(review_payload.get("resolved_model_code") or "").strip()
    if not review_payload.get("is_resolved") or not resolved_model_code:
        return V3_STATUS_INVALID_OR_NOT_SUPPORTED, None, {
            "accepted": False,
            "reason": "missing_resolved_model_code",
        }

    for candidate in candidate_payload:
        if str(candidate.get("model_code") or "").strip() == resolved_model_code:
            conflicts = _validate_second_pass_candidate(candidate=candidate, features=features, profile=profile)
            if conflicts:
                return V3_STATUS_MANUAL_AUDIT_REQUIRED, None, {
                    "accepted": False,
                    "reason": "feature_conflict",
                    "conflicts": conflicts,
                    "candidate": candidate,
                }
            return V3_STATUS_VALID_READY_FOR_PRICING, str(candidate.get("model_catalog_id") or "") or None, {
                "accepted": True,
                "candidate": candidate,
            }

    return V3_STATUS_INVALID_OR_NOT_SUPPORTED, None, {
        "accepted": False,
        "reason": "resolved_model_code_not_in_candidates",
    }


def _validate_second_pass_candidate(
    *,
    candidate: dict[str, Any],
    features: dict[str, Any],
    profile: ReviewV3Profile,
) -> list[str]:
    haystack = " ".join(
        part for part in (
            compact_text(candidate.get("name")),
            compact_text(candidate.get("alias")),
            compact_text(candidate.get("model_code")),
        )
        if part
    )
    conflicts: list[str] = []

    def require_token(value: Any, reason: str) -> None:
        token = compact_text(value)
        if token and token not in haystack:
            conflicts.append(reason)

    if profile.business_domain == "apple_computer":
        require_token(features.get("product_line"), "product_line_conflict")
        require_token(features.get("chip_family"), "chip_family_conflict")
        if features.get("memory_gb") and str(features.get("memory_gb")) not in haystack:
            conflicts.append("memory_conflict")
        if features.get("storage_gb") and str(features.get("storage_gb")) not in haystack:
            conflicts.append("storage_conflict")
        if features.get("screen_size_in") and compact_text(features.get("screen_size_in")) not in haystack:
            conflicts.append("screen_size_conflict")
    elif profile.business_domain == "garmin_watch":
        require_token(features.get("product_line"), "product_line_conflict")
        require_token(features.get("model_hint"), "model_hint_conflict")
        if features.get("case_size_mm") and str(features.get("case_size_mm")) not in haystack:
            conflicts.append("case_size_conflict")
        require_token(features.get("display_type"), "display_type_conflict")
        if features.get("is_solar") is True and "solar" not in haystack:
            conflicts.append("solar_conflict")
    elif profile.business_domain == "camera_body":
        require_token(features.get("model_hint"), "model_hint_conflict")
    elif profile.business_domain == "phone":
        require_token(features.get("product_line"), "product_line_conflict")
        require_token(features.get("model_hint"), "model_hint_conflict")
        if features.get("storage_gb") and str(features.get("storage_gb")) not in haystack:
            conflicts.append("storage_conflict")
    elif profile.business_domain == "apple_airpods":
        require_token(features.get("product_line"), "product_line_conflict")
        require_token(features.get("model_hint"), "model_hint_conflict")
        if features.get("has_anc") is True and "anc" not in haystack and "pro" not in haystack:
            conflicts.append("anc_conflict")
    elif profile.business_domain == "camera_interchangeable_lens":
        require_token(features.get("mount"), "mount_conflict")
        require_token(features.get("focal_length"), "focal_length_conflict")
        require_token(features.get("aperture"), "aperture_conflict")

    deduped: list[str] = []
    for reason in conflicts:
        if reason not in deduped:
            deduped.append(reason)
    return deduped
