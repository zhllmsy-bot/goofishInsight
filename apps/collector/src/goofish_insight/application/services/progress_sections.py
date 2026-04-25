from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from ...category_compat import is_analytics_scope, resolve_category_code
from ...models import Item
from .review_progress_page import (
    build_invalid_reason_breakdown,
    build_llm_review_audit_queue,
    build_llm_review_overview,
    build_llm_review_progress,
    build_usage_summary,
    build_worker_run_cards,
)
from .web_section_cache import get_ttl_cached_payload


@dataclass(frozen=True, slots=True)
class ProgressSectionOptions:
    business_domain: str | None

    def cache_key(self) -> tuple[str | None]:
        return (self.business_domain,)


def load_available_domains(session) -> list[str | None]:
    raw_values = list(
        session.execute(select(Item.business_domain).distinct().order_by(Item.business_domain)).scalars()
    )
    values: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        if not is_analytics_scope(raw_value):
            continue
        resolved = resolve_category_code(raw_value)
        if resolved and resolved not in seen:
            seen.add(resolved)
            values.append(resolved)
    return values


def build_progress_header_section_data(
    session,
    *,
    options: ProgressSectionOptions,
    current_ai_provider: str,
    current_ai_model: str,
) -> dict[str, object]:
    selected_scope = resolve_category_code(options.business_domain) or options.business_domain
    progress_rows = build_llm_review_progress(session, business_domain=selected_scope)
    available_domains = load_available_domains(session)
    return {
        "selected_domain": selected_scope,
        "selected_category_code": selected_scope,
        "available_domains": available_domains,
        "available_categories": available_domains,
        "review_overview": build_llm_review_overview(progress_rows),
        "current_ai_provider": current_ai_provider,
        "current_ai_model": current_ai_model,
    }


def build_progress_overview_section_data(session, *, options: ProgressSectionOptions) -> dict[str, object]:
    def builder() -> dict[str, object]:
        selected_scope = resolve_category_code(options.business_domain) or options.business_domain
        progress_rows = build_llm_review_progress(session, business_domain=selected_scope)
        return {
            "review_overview": build_llm_review_overview(progress_rows),
            "review_progress_rows": progress_rows,
        }

    return get_ttl_cached_payload(
        namespace="progress-overview",
        key=options.cache_key(),
        ttl_seconds=5.0,
        builder=builder,
    )


def build_progress_usage_workers_section_data(session, *, options: ProgressSectionOptions) -> dict[str, object]:
    selected_scope = resolve_category_code(options.business_domain) or options.business_domain
    return {
        "usage_summary": build_usage_summary(business_domain=selected_scope),
        "worker_runs": build_worker_run_cards(business_domain=selected_scope),
    }


def build_progress_audits_section_data(session, *, options: ProgressSectionOptions) -> dict[str, object]:
    def builder() -> dict[str, object]:
        selected_scope = resolve_category_code(options.business_domain) or options.business_domain
        return {
            "audit_queue_rows": build_llm_review_audit_queue(
                session,
                business_domain=selected_scope,
            ),
            "invalid_reason_rows": build_invalid_reason_breakdown(
                session,
                business_domain=selected_scope,
            ),
        }

    return get_ttl_cached_payload(
        namespace="progress-audits",
        key=options.cache_key(),
        ttl_seconds=5.0,
        builder=builder,
    )
