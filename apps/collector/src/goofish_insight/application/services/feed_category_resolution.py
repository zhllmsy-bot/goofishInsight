from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import json
from typing import Any, Iterable, Mapping

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...category_compat import (
    display_label_for_scope,
    get_category_scope_profile,
    is_analytics_scope,
    resolve_category_code,
    token_aliases_for_scope,
)
from ...models import (
    Category,
    CategoryRuntimeProfile,
    CrawlTask,
    Item,
    XianyuCategoryMapping,
    XianyuCategoryOnboardingQueue,
)
from ...settings import get_settings
from ...specs import (
    call_openai_compatible_chat,
    extract_json_object,
    extract_message_content,
    llm_is_configured,
)
from .category_resolution import ResolvedItemCategoryContext
from .xianyu_category_mapping import build_xianyu_category_match_candidates

TARGET_POOL_ONBOARDING_STATUSES = frozenset({"PENDING", "IN_PROGRESS", "RESOLVED"})
FEED_CATEGORY_ROUTER_MIN_CONFIDENCE = Decimal("0.7500")
FEED_CATEGORY_MAPPING_WEIGHT = 100
FEED_CATEGORY_ONBOARDING_WEIGHT = 20
FEED_CATEGORY_HISTORY_WEIGHT_CAP = 12


@dataclass(slots=True)
class FeedTargetPoolGate:
    is_target_pool: bool
    match_key: str | None
    match_scope: str | None
    candidate_business_domains: tuple[str, ...]
    active_candidate_business_domains: tuple[str, ...]
    decision_reason: str | None
    blocked_by_policy: bool
    signal_counts: dict[str, int]
    signal_sources: dict[str, list[dict[str, Any]]]


@dataclass(slots=True)
class FeedCategorySelection:
    is_target_pool: bool
    candidate_business_domains: tuple[str, ...]
    active_candidate_business_domains: tuple[str, ...]
    resolved_business_domain: str | None
    category_context: ResolvedItemCategoryContext | None
    decision_source: str
    decision_reason: str | None
    decision_payload: dict[str, Any]


def resolve_feed_category_selection_with_session(
    session: Session,
    *,
    title: str,
    raw_text: str | None,
    price: Decimal | None,
    xianyu_cat_id: str | None,
    xianyu_tb_cat_id: str | None,
    xianyu_c_cat_id: str | None,
    tasks_by_domain: Mapping[str, CrawlTask],
) -> FeedCategorySelection:
    # Home-feed raw xianyu category ids only decide whether a card is in our
    # target pool. Final internal category routing happens inside the candidate
    # domain set and must not fall back to a single raw-category mapping.
    active_domains = tuple(_normalize_domain_set(tasks_by_domain.keys()))
    gate = resolve_feed_target_pool_gate_with_session(
        session,
        xianyu_cat_id=xianyu_cat_id,
        xianyu_tb_cat_id=xianyu_tb_cat_id,
        xianyu_c_cat_id=xianyu_c_cat_id,
        active_business_domains=active_domains,
    )
    gate_payload = {
        "matchKey": gate.match_key,
        "matchScope": gate.match_scope,
        "candidateBusinessDomains": list(gate.candidate_business_domains),
        "activeCandidateBusinessDomains": list(gate.active_candidate_business_domains),
        "decisionReason": gate.decision_reason,
        "blockedByPolicy": gate.blocked_by_policy,
        "signalCounts": dict(gate.signal_counts),
        "signalSources": dict(gate.signal_sources),
    }
    if not gate.is_target_pool:
        return FeedCategorySelection(
            is_target_pool=False,
            candidate_business_domains=gate.candidate_business_domains,
            active_candidate_business_domains=gate.active_candidate_business_domains,
            resolved_business_domain=None,
            category_context=None,
            decision_source="raw_category_non_target",
            decision_reason=gate.decision_reason or "raw_category_non_target",
            decision_payload={"targetPoolGate": gate_payload},
        )

    active_candidates = gate.active_candidate_business_domains
    if not active_candidates:
        return FeedCategorySelection(
            is_target_pool=True,
            candidate_business_domains=gate.candidate_business_domains,
            active_candidate_business_domains=active_candidates,
            resolved_business_domain=None,
            category_context=None,
            decision_source="raw_category_missing_active_task",
            decision_reason="target_pool_without_active_task",
            decision_payload={"targetPoolGate": gate_payload},
        )

    if len(active_candidates) == 1:
        resolved_domain = active_candidates[0]
        context = _build_category_context_for_business_domain(
            session,
            business_domain=resolved_domain,
            task=tasks_by_domain.get(resolved_domain),
            validation_status="FEED_TARGET_POOL_SINGLE_CANDIDATE",
            validation_reason=f"feed_target_pool_single_candidate:{resolved_domain}",
            validation_confidence=Decimal("1.0000"),
        )
        return FeedCategorySelection(
            is_target_pool=True,
            candidate_business_domains=gate.candidate_business_domains,
            active_candidate_business_domains=active_candidates,
            resolved_business_domain=resolved_domain,
            category_context=context,
            decision_source="raw_category_single_candidate",
            decision_reason=f"single_candidate:{resolved_domain}",
            decision_payload={"targetPoolGate": gate_payload},
        )

    if not llm_is_configured():
        return FeedCategorySelection(
            is_target_pool=True,
            candidate_business_domains=gate.candidate_business_domains,
            active_candidate_business_domains=active_candidates,
            resolved_business_domain=None,
            category_context=None,
            decision_source="raw_category_llm_unavailable",
            decision_reason="candidate_router_llm_unavailable",
            decision_payload={"targetPoolGate": gate_payload},
        )

    try:
        llm_payload = _classify_feed_business_domain_with_llm(
            title=title,
            raw_text=raw_text,
            price=price,
            xianyu_cat_id=xianyu_cat_id,
            xianyu_tb_cat_id=xianyu_tb_cat_id,
            xianyu_c_cat_id=xianyu_c_cat_id,
            candidate_business_domains=active_candidates,
            tasks_by_domain=tasks_by_domain,
        )
    except Exception as exc:
        return FeedCategorySelection(
            is_target_pool=True,
            candidate_business_domains=gate.candidate_business_domains,
            active_candidate_business_domains=active_candidates,
            resolved_business_domain=None,
            category_context=None,
            decision_source="raw_category_llm_error",
            decision_reason=str(exc),
            decision_payload={"targetPoolGate": gate_payload},
        )
    selected_domain = resolve_category_code(
        llm_payload.get("selectedBusinessDomain")
        or llm_payload.get("resolvedBusinessDomain")
        or llm_payload.get("chosenBusinessDomain")
        or llm_payload.get("businessDomain")
    )
    confidence = _coerce_confidence(
        llm_payload.get("confidence"),
        default=Decimal("0.0000"),
    )
    if selected_domain not in active_candidates or confidence < FEED_CATEGORY_ROUTER_MIN_CONFIDENCE:
        return FeedCategorySelection(
            is_target_pool=True,
            candidate_business_domains=gate.candidate_business_domains,
            active_candidate_business_domains=active_candidates,
            resolved_business_domain=None,
            category_context=None,
            decision_source="raw_category_llm_unresolved",
            decision_reason=str(llm_payload.get("reason") or "candidate_router_unresolved"),
            decision_payload={
                "targetPoolGate": gate_payload,
                "llmDecision": llm_payload,
                "minConfidence": str(FEED_CATEGORY_ROUTER_MIN_CONFIDENCE),
            },
        )

    context = _build_category_context_for_business_domain(
        session,
        business_domain=selected_domain,
        task=tasks_by_domain.get(selected_domain),
        validation_status="FEED_TARGET_POOL_LLM",
        validation_reason=f"feed_target_pool_llm:{selected_domain}",
        validation_confidence=confidence,
    )
    return FeedCategorySelection(
        is_target_pool=True,
        candidate_business_domains=gate.candidate_business_domains,
        active_candidate_business_domains=active_candidates,
        resolved_business_domain=selected_domain,
        category_context=context,
        decision_source="raw_category_llm",
        decision_reason=str(llm_payload.get("reason") or f"llm:{selected_domain}"),
        decision_payload={
            "targetPoolGate": gate_payload,
            "llmDecision": llm_payload,
        },
    )


def resolve_feed_target_pool_gate_with_session(
    session: Session,
    *,
    xianyu_cat_id: str | None,
    xianyu_tb_cat_id: str | None,
    xianyu_c_cat_id: str | None,
    active_business_domains: Iterable[str] | None = None,
) -> FeedTargetPoolGate:
    candidates = build_xianyu_category_match_candidates(
        xianyu_cat_id=xianyu_cat_id,
        xianyu_tb_cat_id=xianyu_tb_cat_id,
        xianyu_c_cat_id=xianyu_c_cat_id,
    )
    if not candidates:
        return FeedTargetPoolGate(
            is_target_pool=False,
            match_key=None,
            match_scope=None,
            candidate_business_domains=(),
            active_candidate_business_domains=(),
            decision_reason="missing_raw_category_ids",
            blocked_by_policy=False,
            signal_counts={},
            signal_sources={},
        )

    active_domain_set = _normalize_domain_set(active_business_domains)
    match_keys = [str(candidate["matchKey"]) for candidate in candidates]
    mapping_rows = list(
        session.execute(
            select(XianyuCategoryMapping).where(XianyuCategoryMapping.match_key.in_(match_keys))
        ).scalars()
    )
    onboarding_rows = list(
        session.execute(
            select(XianyuCategoryOnboardingQueue).where(XianyuCategoryOnboardingQueue.match_key.in_(match_keys))
        ).scalars()
    )

    categories_by_id = _load_categories_by_id(
        session,
        category_ids=[
            str(row.category_id)
            for row in mapping_rows
            if getattr(row, "category_id", None)
        ],
    )
    mapping_by_key = {str(row.match_key): row for row in mapping_rows}
    onboarding_by_key: dict[str, list[XianyuCategoryOnboardingQueue]] = defaultdict(list)
    for row in onboarding_rows:
        onboarding_by_key[str(row.match_key)].append(row)

    for candidate in candidates:
        match_key = str(candidate["matchKey"])
        mapping = mapping_by_key.get(match_key)
        if mapping is not None and str(getattr(mapping, "status", "")).upper() == "ACTIVE":
            policy_mode = str(getattr(mapping, "policy_mode", "") or "").upper()
            if policy_mode == "BLOCK":
                return FeedTargetPoolGate(
                    is_target_pool=False,
                    match_key=match_key,
                    match_scope=str(candidate["matchScope"]),
                    candidate_business_domains=(),
                    active_candidate_business_domains=(),
                    decision_reason=f"raw_cate_blocked:{match_key}",
                    blocked_by_policy=True,
                    signal_counts={},
                    signal_sources={},
                )

        signal_counts: Counter[str] = Counter()
        signal_sources: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if mapping is not None and str(getattr(mapping, "status", "")).upper() == "ACTIVE":
            mapped_domain = _resolve_mapping_business_domain(mapping=mapping, categories_by_id=categories_by_id)
            if mapped_domain:
                signal_counts[mapped_domain] += FEED_CATEGORY_MAPPING_WEIGHT
                signal_sources[mapped_domain].append(
                    {
                        "source": "mapping",
                        "matchKey": match_key,
                        "policyMode": str(getattr(mapping, "policy_mode", "") or "FORCE_TEMPLATE"),
                    }
                )

        for row in onboarding_by_key.get(match_key, []):
            if str(getattr(row, "status", "")).upper() not in TARGET_POOL_ONBOARDING_STATUSES:
                continue
            for domain in _extract_onboarding_business_domains(row=row):
                signal_counts[domain] += FEED_CATEGORY_ONBOARDING_WEIGHT
                signal_sources[domain].append(
                    {
                        "source": "onboarding_queue",
                        "matchKey": match_key,
                        "status": str(getattr(row, "status", "") or ""),
                    }
                )

        for domain, count in _load_candidate_business_domain_counts_with_session(
            session,
            match_scope=str(candidate["matchScope"]),
            xianyu_cat_id=candidate.get("xianyuCatId"),
            xianyu_tb_cat_id=candidate.get("xianyuTbCatId"),
            xianyu_c_cat_id=candidate.get("xianyuCCatId"),
        ).items():
            weighted_count = min(int(count or 0), FEED_CATEGORY_HISTORY_WEIGHT_CAP)
            if weighted_count <= 0:
                continue
            signal_counts[domain] += weighted_count
            signal_sources[domain].append(
                {
                    "source": "historical_items",
                    "matchKey": match_key,
                    "count": int(count or 0),
                }
            )

        if not signal_counts:
            continue

        ranked_domains = tuple(
            domain
            for domain, _score in sorted(
                signal_counts.items(),
                key=lambda entry: (-entry[1], entry[0]),
            )
        )
        active_ranked_domains = tuple(
            domain
            for domain in ranked_domains
            if not active_domain_set or domain in active_domain_set
        )
        return FeedTargetPoolGate(
            is_target_pool=True,
            match_key=match_key,
            match_scope=str(candidate["matchScope"]),
            candidate_business_domains=ranked_domains,
            active_candidate_business_domains=active_ranked_domains,
            decision_reason=f"target_pool:{match_key}",
            blocked_by_policy=False,
            signal_counts={domain: signal_counts[domain] for domain in ranked_domains},
            signal_sources={domain: signal_sources[domain] for domain in ranked_domains},
        )

    return FeedTargetPoolGate(
        is_target_pool=False,
        match_key=None,
        match_scope=None,
        candidate_business_domains=(),
        active_candidate_business_domains=(),
        decision_reason="raw_category_not_in_target_pool",
        blocked_by_policy=False,
        signal_counts={},
        signal_sources={},
    )


def _classify_feed_business_domain_with_llm(
    *,
    title: str,
    raw_text: str | None,
    price: Decimal | None,
    xianyu_cat_id: str | None,
    xianyu_tb_cat_id: str | None,
    xianyu_c_cat_id: str | None,
    candidate_business_domains: tuple[str, ...],
    tasks_by_domain: Mapping[str, CrawlTask],
) -> dict[str, Any]:
    settings = get_settings()
    candidate_payload = [
        _serialize_candidate_domain(
            business_domain=domain,
            task=tasks_by_domain.get(domain),
        )
        for domain in candidate_business_domains
    ]
    response_payload = call_openai_compatible_chat(
        base_url=settings.ai_base_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout_sec=settings.ai_timeout_sec,
        enable_thinking=settings.ai_enable_thinking,
        max_tokens=300,
        messages=[
            {
                "role": "system",
                "content": (
                    "You classify Goofish home-feed listings into one internal business domain. "
                    "Choose only from the provided candidateBusinessDomains. "
                    "If the listing does not clearly fit a single candidate, return null. "
                    "Always return a JSON object with keys: selectedBusinessDomain, confidence, reason, evidence."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "listing": {
                            "title": title,
                            "rawText": raw_text or title,
                            "price": str(price) if price is not None else None,
                            "xianyuCategory": {
                                "catId": xianyu_cat_id,
                                "tbCatId": xianyu_tb_cat_id,
                                "cCatId": xianyu_c_cat_id,
                            },
                        },
                        "candidateBusinessDomains": candidate_payload,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            },
        ],
    )
    return extract_json_object(extract_message_content(response_payload))


def _serialize_candidate_domain(
    *,
    business_domain: str,
    task: CrawlTask | None,
) -> dict[str, Any]:
    profile = get_category_scope_profile(business_domain)
    scope_tokens = list(token_aliases_for_scope(business_domain)[:8])
    classifier_hint = _build_candidate_classifier_hint(
        business_domain=business_domain,
        task=task,
        token_aliases=scope_tokens,
    )
    return {
        "businessDomain": business_domain,
        "displayName": display_label_for_scope(business_domain),
        "promptProfile": getattr(profile, "prompt_profile", None),
        "tokenAliases": scope_tokens,
        "keywords": list(getattr(task, "keywords", [])[:6]) if task is not None else [],
        "brandLexicon": list(getattr(task, "brand_lexicon", [])[:6]) if task is not None else [],
        "modelLexicon": list(getattr(task, "model_lexicon", [])[:8]) if task is not None else [],
        "configLexicon": list(getattr(task, "config_lexicon", [])[:6]) if task is not None else [],
        "classifierHint": classifier_hint,
    }


def _build_candidate_classifier_hint(
    *,
    business_domain: str,
    task: CrawlTask | None,
    token_aliases: list[str],
) -> dict[str, Any]:
    positive_signals: list[str] = []
    negative_signals: list[str] = []
    if task is not None:
        positive_signals.extend(list(getattr(task, "keywords", [])[:4]))
        positive_signals.extend(list(getattr(task, "model_lexicon", [])[:4]))
    positive_signals.extend(token_aliases[:4])

    canonical_domain = resolve_category_code(business_domain)
    if canonical_domain == "apple_computer":
        negative_signals.extend(["airpods", "单耳", "充电盒", "耳机"])
    elif canonical_domain == "apple_airpods":
        negative_signals.extend(["macbook", "mac mini", "mac studio", "imac", "m1", "m2", "m3", "m4"])
    elif canonical_domain == "camera_body":
        negative_signals.extend(["镜头", "fe", "rf", "xf", "art", "gm"])
    elif canonical_domain == "camera_interchangeable_lens":
        negative_signals.extend(["机身", "单机", "快门", "微单", "单反"])

    return {
        "positiveSignals": _dedupe_texts(positive_signals)[:8],
        "negativeSignals": _dedupe_texts(negative_signals)[:8],
    }


def _build_category_context_for_business_domain(
    session: Session,
    *,
    business_domain: str,
    task: CrawlTask | None,
    validation_status: str,
    validation_reason: str,
    validation_confidence: Decimal | None,
) -> ResolvedItemCategoryContext:
    canonical_domain = resolve_category_code(business_domain)
    category_id = str(getattr(task, "category_id", "") or "").strip() or _resolve_category_id_by_code(
        session,
        category_code=canonical_domain,
    )
    template_id = _load_active_template_id(session, category_id=category_id)
    return ResolvedItemCategoryContext(
        target_category_id=category_id,
        resolved_category_id=category_id,
        resolved_template_id=template_id,
        category_validation_status=validation_status,
        category_validation_reason=validation_reason,
        category_validation_confidence=validation_confidence,
        resolved_business_domain=canonical_domain or business_domain,
    )


def _load_candidate_business_domain_counts_with_session(
    session: Session,
    *,
    match_scope: str,
    xianyu_cat_id: str | None,
    xianyu_tb_cat_id: str | None,
    xianyu_c_cat_id: str | None,
) -> dict[str, int]:
    stmt = (
        select(Item.business_domain, func.count())
        .where(Item.source_platform == "xianyu")
        .group_by(Item.business_domain)
    )
    normalized_scope = str(match_scope or "").strip().upper()
    if normalized_scope == "C_CAT":
        if not xianyu_c_cat_id:
            return {}
        stmt = stmt.where(Item.xianyu_c_cat_id == str(xianyu_c_cat_id))
    elif normalized_scope == "CAT_TB":
        if not xianyu_cat_id or not xianyu_tb_cat_id:
            return {}
        stmt = stmt.where(
            Item.xianyu_cat_id == str(xianyu_cat_id),
            Item.xianyu_tb_cat_id == str(xianyu_tb_cat_id),
        )
    elif normalized_scope == "TB_CAT":
        if not xianyu_tb_cat_id:
            return {}
        stmt = stmt.where(Item.xianyu_tb_cat_id == str(xianyu_tb_cat_id))
    elif normalized_scope == "CAT":
        if not xianyu_cat_id:
            return {}
        stmt = stmt.where(Item.xianyu_cat_id == str(xianyu_cat_id))
    else:
        return {}
    counts: Counter[str] = Counter()
    for domain, count in session.execute(stmt).all():
        canonical = resolve_category_code(domain)
        if not canonical or not is_analytics_scope(canonical):
            continue
        counts[canonical] += int(count or 0)
    return dict(sorted(counts.items()))


def _extract_onboarding_business_domains(
    *,
    row: XianyuCategoryOnboardingQueue,
) -> tuple[str, ...]:
    ordered: list[str] = []
    for value in list(getattr(row, "business_domains", []) or []):
        canonical = resolve_category_code(value)
        if canonical and is_analytics_scope(canonical) and canonical not in ordered:
            ordered.append(canonical)
    resolved_mapping_json = getattr(row, "resolved_mapping_json", None)
    if isinstance(resolved_mapping_json, dict):
        for value in (
            resolved_mapping_json.get("businessDomain"),
            resolved_mapping_json.get("categoryCode"),
        ):
            canonical = resolve_category_code(value)
            if canonical and is_analytics_scope(canonical) and canonical not in ordered:
                ordered.append(canonical)
    return tuple(ordered)


def _resolve_mapping_business_domain(
    *,
    mapping: XianyuCategoryMapping,
    categories_by_id: Mapping[str, Category],
) -> str | None:
    category_id = str(getattr(mapping, "category_id", "") or "").strip()
    if not category_id:
        return None
    category = categories_by_id.get(category_id)
    if category is None:
        return None
    canonical = resolve_category_code(getattr(category, "code", None))
    if not canonical or not is_analytics_scope(canonical):
        return None
    return canonical


def _load_categories_by_id(
    session: Session,
    *,
    category_ids: list[str],
) -> dict[str, Category]:
    normalized_ids = sorted({str(category_id).strip() for category_id in category_ids if str(category_id).strip()})
    if not normalized_ids:
        return {}
    rows = list(session.execute(select(Category).where(Category.id.in_(normalized_ids))).scalars())
    return {str(row.id): row for row in rows}


def _resolve_category_id_by_code(session: Session, *, category_code: str | None) -> str | None:
    canonical_code = resolve_category_code(category_code)
    if not canonical_code:
        return None
    row = session.execute(select(Category).where(Category.code == canonical_code)).scalar_one_or_none()
    if row is None:
        return None
    return str(getattr(row, "id", None) or "") or None


def _load_active_template_id(session: Session, *, category_id: str | None) -> str | None:
    if not category_id:
        return None
    runtime_profile = session.execute(
        select(CategoryRuntimeProfile).where(
            CategoryRuntimeProfile.category_id == str(category_id),
            CategoryRuntimeProfile.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    if runtime_profile is None or not getattr(runtime_profile, "active_template_id", None):
        return None
    return str(runtime_profile.active_template_id)


def _normalize_domain_set(values: Iterable[str] | None) -> set[str]:
    normalized: set[str] = set()
    for value in values or ():
        canonical = resolve_category_code(value)
        if canonical:
            normalized.add(canonical)
    return normalized


def _dedupe_texts(values: Iterable[str]) -> list[str]:
    ordered: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in ordered:
            ordered.append(normalized)
    return ordered


def _coerce_confidence(value: Any, *, default: Decimal) -> Decimal:
    if value is None:
        return default
    try:
        if isinstance(value, Decimal):
            return value.quantize(Decimal("0.0001"))
        return Decimal(str(value)).quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError, TypeError):
        return default


__all__ = [
    "FeedCategorySelection",
    "FeedTargetPoolGate",
    "resolve_feed_category_selection_with_session",
    "resolve_feed_target_pool_gate_with_session",
]
