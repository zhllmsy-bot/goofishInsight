from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "collector" / "src"))

from sqlalchemy import desc, select

from goofish_insight.compat import UTC
from goofish_insight.db import SessionLocal
from goofish_insight.models import Item, ItemReviewV3
from goofish_insight.application.services.review_v3_pipeline import (
    run_review_v3_first_pass,
    run_review_v3_second_pass,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Run review v3 over top items and summarize outcomes.')
    parser.add_argument('--limit', type=int, default=1000)
    parser.add_argument('--first-pass-workers', type=int, default=6)
    parser.add_argument('--second-pass-workers', type=int, default=6)
    parser.add_argument('--output-prefix', type=str, default='review-v3-top-items-eval')
    return parser.parse_args()


def fetch_top_item_ids(limit: int) -> list[str]:
    with SessionLocal() as session:
        return list(
            session.execute(
                select(Item.item_id)
                .where(Item.is_active.is_(True))
                .order_by(desc(Item.last_seen_at), desc(Item.id))
                .limit(limit)
            ).scalars()
        )


def fetch_top_item_domains(item_ids: list[str]) -> dict[str, str]:
    with SessionLocal() as session:
        rows = session.execute(select(Item.item_id, Item.business_domain).where(Item.item_id.in_(item_ids))).all()
    return {row.item_id: row.business_domain for row in rows}


def run_first_pass_item(item_id: str) -> dict[str, Any]:
    results = run_review_v3_first_pass(business_domain=None, item_id=item_id, limit=1, force=True)
    if not results:
        return {'item_id': item_id, 'business_domain': None, 'resolution_status': 'NO_RESULT'}
    return dict(results[0])


def run_second_pass_item(item_id: str) -> dict[str, Any]:
    results = run_review_v3_second_pass(business_domain=None, item_id=item_id, limit=1, force=True)
    if not results:
        return {'item_id': item_id, 'business_domain': None, 'resolution_status': 'NO_RESULT'}
    return dict(results[0])


def run_item_pipeline(item_id: str) -> dict[str, Any]:
    first_result = run_first_pass_item(item_id)
    if str(first_result.get('resolution_status') or '') != 'PENDING_REVIEW':
        return {
            'item_id': item_id,
            'business_domain': first_result.get('business_domain'),
            'first_pass': first_result,
            'final_result': first_result,
        }
    second_result = run_second_pass_item(item_id)
    return {
        'item_id': item_id,
        'business_domain': first_result.get('business_domain') or second_result.get('business_domain'),
        'first_pass': first_result,
        'final_result': second_result,
    }


def execute_pool(item_ids: list[str], worker_fn, workers: int, phase: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    total = len(item_ids)
    if total == 0:
        return results
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(worker_fn, item_id): item_id for item_id in item_ids}
        for index, future in enumerate(as_completed(future_map), start=1):
            item_id = future_map[future]
            try:
                result = future.result()
            except Exception as exc:  # pragma: no cover - runtime guard
                result = {
                    'item_id': item_id,
                    'business_domain': None,
                    'resolution_status': 'EXECUTION_ERROR',
                    'error': repr(exc),
                }
            results.append(result)
            if index % 25 == 0 or index == total:
                print(json.dumps({
                    'event': f'{phase}_progress',
                    'completed': index,
                    'total': total,
                }, ensure_ascii=False), flush=True)
    return results


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_status = Counter(str(result.get('resolution_status') or ''))
    by_domain: dict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        domain = str(result.get('business_domain') or '') or 'unknown'
        by_domain[domain][str(result.get('resolution_status') or '')] += 1
    total_tokens = 0
    input_tokens = 0
    output_tokens = 0
    request_count = 0
    for result in results:
        usage = result.get('llm_usage') if isinstance(result.get('llm_usage'), dict) else {}
        input_tokens += int(usage.get('input_tokens') or 0)
        output_tokens += int(usage.get('output_tokens') or 0)
        total_tokens += int(usage.get('total_tokens') or 0)
        request_count += int(result.get('llm_request_count') or 0)
    return {
        'count': len(results),
        'statusCounts': dict(by_status),
        'domainStatusCounts': {domain: dict(counter) for domain, counter in sorted(by_domain.items())},
        'usage': {
            'requestCount': request_count,
            'inputTokens': input_tokens,
            'outputTokens': output_tokens,
            'totalTokens': total_tokens,
        },
    }


def fetch_final_rows(item_ids: list[str]) -> list[dict[str, Any]]:
    with SessionLocal() as session:
        rows = session.execute(
            select(
                Item.item_id,
                Item.business_domain,
                Item.llm_review_status,
                Item.llm_review_confidence,
                ItemReviewV3.stage_status,
                ItemReviewV3.resolution_status,
                ItemReviewV3.model_catalog_id,
                ItemReviewV3.first_pass_confidence,
                ItemReviewV3.second_pass_confidence,
            )
            .join(ItemReviewV3, ItemReviewV3.item_id_ref == Item.id, isouter=True)
            .where(Item.item_id.in_(item_ids))
            .order_by(Item.id)
        ).all()
    serialized = []
    for row in rows:
        serialized.append({
            'item_id': row.item_id,
            'business_domain': row.business_domain,
            'compat_status': row.llm_review_status,
            'compat_confidence': float(row.llm_review_confidence) if row.llm_review_confidence is not None else None,
            'stage_status': row.stage_status,
            'resolution_status': row.resolution_status,
            'model_catalog_id': row.model_catalog_id,
            'first_pass_confidence': float(row.first_pass_confidence) if row.first_pass_confidence is not None else None,
            'second_pass_confidence': float(row.second_pass_confidence) if row.second_pass_confidence is not None else None,
        })
    return serialized


def main() -> int:
    args = parse_args()
    started_at = datetime.now(UTC)
    item_ids = fetch_top_item_ids(args.limit)
    domains = fetch_top_item_domains(item_ids)
    cohort_counts = Counter(domains.values())
    print(json.dumps({
        'event': 'cohort_loaded',
        'limit': args.limit,
        'count': len(item_ids),
        'domainCounts': dict(cohort_counts),
    }, ensure_ascii=False), flush=True)

    pipeline_results = execute_pool(item_ids, run_item_pipeline, args.first_pass_workers, 'review_v3')
    first_pass_results = [dict(result.get('first_pass') or {}) for result in pipeline_results if result.get('first_pass')]
    second_pass_results = [
        dict(result.get('final_result') or {})
        for result in pipeline_results
        if result.get('final_result') and str((result.get('first_pass') or {}).get('resolution_status') or '') == 'PENDING_REVIEW'
    ]

    completed_at = datetime.now(UTC)
    output_dir = REPO_ROOT / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{args.output_prefix}-{started_at.strftime('%Y%m%d-%H%M%S')}"
    first_path = output_dir / f'{prefix}.first-pass.json'
    second_path = output_dir / f'{prefix}.second-pass.json'
    final_path = output_dir / f'{prefix}.final-summary.json'

    first_path.write_text(json.dumps(first_pass_results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    second_path.write_text(json.dumps(second_pass_results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    final_rows = fetch_final_rows(item_ids)
    final_summary = {
        'startedAt': started_at.isoformat(),
        'completedAt': completed_at.isoformat(),
        'cohort': {
            'count': len(item_ids),
            'domainCounts': dict(cohort_counts),
            'firstItemId': item_ids[0] if item_ids else None,
            'lastItemId': item_ids[-1] if item_ids else None,
        },
        'firstPass': summarize_results(first_pass_results),
        'secondPass': summarize_results(second_pass_results),
        'final': summarize_results(final_rows),
        'paths': {
            'firstPass': str(first_path),
            'secondPass': str(second_path),
        },
        'sample': final_rows[:25],
    }
    final_path.write_text(json.dumps(final_summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'event': 'completed', 'summaryPath': str(final_path)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
