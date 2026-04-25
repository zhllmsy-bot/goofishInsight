from __future__ import annotations

import json

import typer


def register_maintenance_commands(
    app: typer.Typer,
    *,
    backfill_spec_confidence,
    backfill_item_category_resolution,
    backfill_task_category_bindings,
    preprocess_apple_items,
    backfill_normalized_prices,
    cleanup_historical_data,
    enrich_single_item,
    get_settings,
    classify_seller_types,
    llm_is_configured,
    load_items_for_enrichment,
) -> None:
    from ...category_compat import resolve_category_code

    def _cleanup_item_category_domain_mismatches(
        *,
        category_code: str | None = None,
        limit: int | None = None,
        dry_run: bool = True,
    ) -> dict[str, object]:
        from sqlalchemy import delete, select, update

        from ...db import session_scope
        from ...models import Category, CrawlTask, CrawlTaskQuery, Item, ItemIngestRejection
        from ...pricing import resolve_domain_redirect_scope, title_domain_mismatch_reason, title_matches_domain

        resolved_category_code = resolve_category_code(category_code)
        if not resolved_category_code:
            raise typer.BadParameter("category_code is required")

        domain_query = (
            select(Item)
            .where(Item.business_domain == resolved_category_code)
            .order_by(Item.id.asc())
        )
        if limit is not None and limit > 0:
            domain_query = domain_query.limit(int(limit))

        with session_scope() as session:
            category_rows = session.execute(select(Category.id, Category.code)).all()
            category_id_by_code = {str(code): str(category_id) for category_id, code in category_rows if code}

            items = list(session.execute(domain_query).scalars())
            blocked_item_ids: list[str] = []
            redirected_item_ids: list[str] = []
            deleted_rejection_item_ids: list[str] = []
            disabled_query_ids: list[int] = []
            disabled_query_texts: list[str] = []
            item_updates: list[dict[str, object]] = []

            for item in items:
                title = str(getattr(item, "title", "") or "")
                if title_matches_domain(resolved_category_code, title):
                    continue

                redirect_scope = resolve_domain_redirect_scope(resolved_category_code, title)
                if redirect_scope:
                    redirected_category_id = category_id_by_code.get(redirect_scope)
                    item_updates.append(
                        {
                            "item_id": item.item_id,
                            "action": "redirect",
                            "from_domain": resolved_category_code,
                            "to_domain": redirect_scope,
                            "title": title,
                        }
                    )
                    redirected_item_ids.append(str(item.item_id))
                    if not dry_run:
                        item.business_domain = redirect_scope
                        item.resolved_category_id = redirected_category_id
                        item.resolved_template_id = None
                        item.category_validation_status = "OVERRIDE_CATEGORY"
                        item.category_validation_reason = (
                            f"title_scope_override:{resolved_category_code}_to_{redirect_scope}"
                        )
                    continue

                mismatch_reason = title_domain_mismatch_reason(resolved_category_code, title)
                action_reason = mismatch_reason or "domain_mismatch"
                item_updates.append(
                    {
                        "item_id": item.item_id,
                        "action": "block",
                        "from_domain": resolved_category_code,
                        "reason": action_reason,
                        "title": title,
                    }
                )
                blocked_item_ids.append(str(item.item_id))
                if not dry_run:
                    item.is_active = False
                    item.resolved_category_id = None
                    item.resolved_template_id = None
                    item.category_validation_status = "BLOCKED"
                    item.category_validation_reason = f"title_scope_blocked:{action_reason}"

            if not dry_run and blocked_item_ids:
                session.execute(
                    delete(ItemIngestRejection).where(
                        ItemIngestRejection.source_platform == "xianyu",
                        ItemIngestRejection.item_id.in_(tuple(blocked_item_ids)),
                    )
                )
                deleted_rejection_item_ids.extend(blocked_item_ids)

            if resolved_category_code == "apple_computer":
                query_rows = session.execute(
                    select(CrawlTaskQuery.id, CrawlTaskQuery.query_text)
                    .join(CrawlTask, CrawlTask.id == CrawlTaskQuery.task_id)
                    .where(CrawlTaskQuery.status == "ACTIVE")
                    .where(CrawlTask.business_domain == resolved_category_code)
                ).all()
                for query_id, query_text in query_rows:
                    normalized_query = str(query_text or "").strip().lower()
                    if normalized_query == "/" or "apple watch" in normalized_query:
                        disabled_query_ids.append(int(query_id))
                        disabled_query_texts.append(str(query_text))
                if disabled_query_ids and not dry_run:
                    session.execute(
                        update(CrawlTaskQuery)
                        .where(CrawlTaskQuery.id.in_(tuple(sorted(set(disabled_query_ids)))))
                        .values(status="DISABLED")
                    )

            if redirected_item_ids and not dry_run:
                session.execute(
                    delete(ItemIngestRejection).where(
                        ItemIngestRejection.source_platform == "xianyu",
                        ItemIngestRejection.item_id.in_(tuple(redirected_item_ids)),
                        ItemIngestRejection.rejection_stage.like("transient:%"),
                    )
                )
                deleted_rejection_item_ids.extend(redirected_item_ids)

            return {
                "category_code": resolved_category_code,
                "dry_run": bool(dry_run),
                "scanned": len(items),
                "blocked_count": len(blocked_item_ids),
                "redirected_count": len(redirected_item_ids),
                "disabled_query_count": len(sorted(set(disabled_query_ids))),
                "deleted_rejection_count": len(sorted(set(deleted_rejection_item_ids))),
                "disabled_queries": sorted(set(disabled_query_texts)),
                "sample": item_updates[:100],
            }

    def _reconcile_item_category_domain_state(
        *,
        category_code: str | None = None,
        limit: int | None = None,
        dry_run: bool = True,
    ) -> dict[str, object]:
        from ...db import session_scope
        from ...application.services.category_domain_reconcile import reconcile_item_category_domain_state

        resolved_category_code = resolve_category_code(category_code)
        if not resolved_category_code:
            raise typer.BadParameter("category_code is required")

        with session_scope() as session:
            return reconcile_item_category_domain_state(
                session,
                category_code=resolved_category_code,
                limit=limit,
                dry_run=dry_run,
            )

    def _audit_camera_listing_shapes(
        *,
        category_code: str | None = None,
        active_only: bool = True,
        limit: int | None = None,
        sample_limit: int = 20,
    ) -> dict[str, object]:
        from ...db import session_scope
        from ...application.services.camera_listing_shape import audit_camera_listing_shapes

        with session_scope() as session:
            return audit_camera_listing_shapes(
                session,
                category_code=category_code,
                active_only=active_only,
                limit=limit,
                sample_limit=sample_limit,
            )

    def _repair_camera_listing_shapes(
        *,
        category_code: str | None = None,
        active_only: bool = True,
        limit: int | None = None,
        sample_limit: int = 50,
        min_confidence: float = 0.9,
        dry_run: bool = True,
    ) -> dict[str, object]:
        from ...db import session_scope
        from ...application.services.camera_listing_shape import repair_camera_listing_shapes

        with session_scope() as session:
            return repair_camera_listing_shapes(
                session,
                category_code=category_code,
                active_only=active_only,
                limit=limit,
                sample_limit=sample_limit,
                min_confidence=min_confidence,
                dry_run=dry_run,
            )

    @app.command("audit-spec-enrichments")
    def audit_spec_enrichments(
        lookback_days: int = typer.Option(365, min=1, max=3650),
        limit: int = typer.Option(50, min=1, max=1000),
    ) -> None:
        """Audit spec enrichment rows for obvious garbage patterns."""
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import select

        from ...db import session_scope
        from ...models import Item, ItemSpecEnrichment

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=int(lookback_days))

        def _is_blank(value: str | None) -> bool:
            return not str(value or "").strip()

        def _is_empty_core(spec: ItemSpecEnrichment) -> bool:
            return (
                _is_blank(spec.brand)
                and _is_blank(spec.model_name)
                and _is_blank(spec.product_line)
                and _is_blank(spec.model_family)
                and _is_blank(spec.generation)
                and spec.case_size_mm is None
                and spec.screen_size_in is None
                and _is_blank(spec.chip_family)
                and spec.memory_gb is None
                and spec.storage_gb is None
            )

        report = {
            "generated_at": now.isoformat(),
            "lookback_days": int(lookback_days),
            "total": 0,
            "empty_core_fields": 0,
            "invalid_screen_size": 0,
            "samples": [],
        }

        with session_scope() as session:
            stmt = (
                select(ItemSpecEnrichment, Item)
                .join(Item, Item.id == ItemSpecEnrichment.item_id_ref)
                .where(ItemSpecEnrichment.updated_at >= cutoff)
                .order_by(ItemSpecEnrichment.updated_at.desc(), ItemSpecEnrichment.id.desc())
                .limit(int(limit) * 5)
            )
            rows = session.execute(stmt).all()

        report["total"] = len(rows)
        samples: list[dict[str, object]] = []
        for spec, item in rows:
            invalid_screen = spec.screen_size_in is not None and (
                float(spec.screen_size_in) <= 0 or float(spec.screen_size_in) > 30
            )
            empty_core = _is_empty_core(spec)

            if invalid_screen:
                report["invalid_screen_size"] += 1
            if empty_core:
                report["empty_core_fields"] += 1

            if (invalid_screen or empty_core) and len(samples) < int(limit):
                samples.append(
                    {
                        "spec_id": spec.id,
                        "item_id_ref": spec.item_id_ref,
                        "spec_domain": spec.business_domain,
                        "item_domain": item.business_domain,
                        "item_id": item.item_id,
                        "title": item.title,
                        "extractor_type": spec.extractor_type,
                        "extractor_version": spec.extractor_version,
                        "status": spec.status,
                        "confidence": float(spec.confidence) if spec.confidence is not None else None,
                        "model_name": spec.model_name,
                        "screen_size_in": float(spec.screen_size_in) if spec.screen_size_in is not None else None,
                        "updated_at": spec.updated_at.isoformat() if spec.updated_at else None,
                        "flags": {
                            "invalid_screen_size": invalid_screen,
                            "empty_core_fields": empty_core,
                        },
                    }
                )

        report["samples"] = samples
        typer.echo(json.dumps(report, ensure_ascii=False, indent=2))

    @app.command("cleanup-spec-enrichments")
    def cleanup_spec_enrichments(
        dry_run: bool = True,
        fix_only: bool = False,
        delete_empty_unresolved: bool = True,
        delete_invalid_screen_size: bool = True,
        lookback_days: int = typer.Option(3650, min=1, max=3650),
        limit: int = typer.Option(5000, min=1, max=200000),
    ) -> None:
        """Cleanup obvious garbage spec enrichment rows.

        Defaults to dry-run. Use --dry-run false to apply changes.
        """
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import delete, select, update

        from ...db import session_scope
        from ...models import Item, ItemSpecEnrichment

        now = datetime.now(UTC)
        cutoff = now - timedelta(days=int(lookback_days))

        def _is_blank(value: str | None) -> bool:
            return not str(value or "").strip()

        def _is_empty_core(spec: ItemSpecEnrichment) -> bool:
            return (
                _is_blank(spec.brand)
                and _is_blank(spec.model_name)
                and _is_blank(spec.product_line)
                and _is_blank(spec.model_family)
                and _is_blank(spec.generation)
                and spec.case_size_mm is None
                and spec.screen_size_in is None
                and _is_blank(spec.chip_family)
                and spec.memory_gb is None
                and spec.storage_gb is None
            )

        stmt = (
            select(ItemSpecEnrichment, Item)
            .join(Item, Item.id == ItemSpecEnrichment.item_id_ref)
            .where(ItemSpecEnrichment.updated_at >= cutoff)
            .order_by(ItemSpecEnrichment.updated_at.desc(), ItemSpecEnrichment.id.desc())
            .limit(int(limit))
        )
        with session_scope() as session:
            rows = session.execute(stmt).all()

            delete_ids: list[int] = []
            fix_ids: list[int] = []
            for spec, item in rows:
                invalid_screen = spec.screen_size_in is not None and (
                    float(spec.screen_size_in) <= 0 or float(spec.screen_size_in) > 30
                )
                empty_core = _is_empty_core(spec)

                if delete_invalid_screen_size and invalid_screen:
                    delete_ids.append(int(spec.id))
                    continue
                if delete_empty_unresolved and empty_core and str(spec.status or "").strip().lower() == "unresolved":
                    delete_ids.append(int(spec.id))
                    continue
                # Fix hook: currently only supports no-op placeholder for future field-level corrections.
                if invalid_screen:
                    fix_ids.append(int(spec.id))

            summary = {
                "generated_at": now.isoformat(),
                "dry_run": bool(dry_run),
                "fix_only": bool(fix_only),
                "lookback_days": int(lookback_days),
                "scanned": len(rows),
                "delete_candidates": len(delete_ids),
                "fix_candidates": len(fix_ids),
                "delete_sample": delete_ids[:20],
            }

            if dry_run:
                typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))
                return

            changed = {
                "deleted": 0,
                "fixed": 0,
            }

            if not fix_only and delete_ids:
                result = session.execute(delete(ItemSpecEnrichment).where(ItemSpecEnrichment.id.in_(delete_ids)))
                changed["deleted"] = int(result.rowcount or 0)

            if fix_only and fix_ids:
                result = session.execute(
                    update(ItemSpecEnrichment)
                    .where(ItemSpecEnrichment.id.in_(fix_ids))
                    .values(needs_review=True)
                )
                changed["fixed"] = int(result.rowcount or 0)

            typer.echo(json.dumps({**summary, **changed}, ensure_ascii=False, indent=2))

    @app.command("backfill-spec-confidence")
    def backfill_spec_confidence_command(
        dry_run: bool = False,
        limit: int | None = typer.Option(default=None, min=1),
        extractor_type: str | None = None,
    ) -> None:
        summary = backfill_spec_confidence(
            dry_run=dry_run,
            limit=limit,
            extractor_type=extractor_type,
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("enrich-specs")
    def enrich_specs(
        business_domain: str | None = None,
        item_id: str | None = None,
        limit: int = 50,
        force: bool = False,
        use_llm: bool = True,
    ) -> None:
        configured_llm = use_llm and llm_is_configured()
        if use_llm and not configured_llm:
            typer.echo("LLM fallback is not configured. Running rule-only enrichment.")

        item_ids = load_items_for_enrichment(
            business_domain=business_domain,
            item_id=item_id,
            limit=limit,
            force=force,
        )
        if not item_ids:
            typer.echo("No items matched the enrichment query.")
            return

        summary = {
            "processed": 0,
            "complete": 0,
            "partial": 0,
            "unresolved": 0,
            "failed": 0,
            "llm_used": 0,
        }

        for db_item_id in item_ids:
            summary["processed"] += 1
            try:
                result = enrich_single_item(db_item_id=db_item_id, allow_llm=configured_llm)
                status_key = result["status"] if result["status"] in summary else "failed"
                summary[status_key] += 1
                if result["extractor_type"] in {"llm", "hybrid"}:
                    summary["llm_used"] += 1
                typer.echo(
                    json.dumps(
                        {
                            "item_id": result["item_id"],
                            "status": result["status"],
                            "confidence": result["confidence"],
                            "model_name": result["model_name"],
                            "extractor_type": result["extractor_type"],
                        },
                        ensure_ascii=False,
                    )
                )
            except Exception as exc:
                summary["failed"] += 1
                typer.echo(json.dumps({"db_item_id": db_item_id, "error": str(exc)}, ensure_ascii=False))

        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("cleanup-history")
    def cleanup_history(
        dry_run: bool = False,
        prune_raw: bool | None = None,
        prune_snapshots: bool = True,
        max_passes: int = typer.Option(1, min=1, max=20),
    ) -> None:
        summary = cleanup_historical_data(
            dry_run=dry_run,
            prune_raw=get_settings().prune_raw_after_ingest if prune_raw is None else prune_raw,
            prune_snapshots=prune_snapshots,
            max_passes=max_passes,
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("normalize-prices")
    def normalize_prices(
        business_domain: str | None = None,
        dry_run: bool = False,
        item_limit: int | None = typer.Option(default=None, min=1),
        snapshot_limit: int | None = typer.Option(default=None, min=1),
    ) -> None:
        summary = backfill_normalized_prices(
            dry_run=dry_run,
            business_domain=business_domain,
            item_limit=item_limit,
            snapshot_limit=snapshot_limit,
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("classify-seller-types")
    def classify_seller_types_command(
        dry_run: bool = False,
        limit: int | None = typer.Option(default=None, min=1),
    ) -> None:
        summary = classify_seller_types(
            dry_run=dry_run,
            limit=limit,
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("preprocess-apple-items")
    def preprocess_apple_items_command(
        dry_run: bool = False,
        limit: int | None = typer.Option(default=None, min=1),
    ) -> None:
        summary = preprocess_apple_items(
            dry_run=dry_run,
            limit=limit,
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("backfill-item-category-resolution")
    def backfill_item_category_resolution_command(
        task_key: str | None = None,
        category_code: str | None = None,
        limit: int | None = typer.Option(default=None, min=1),
        dry_run: bool = False,
    ) -> None:
        summary = backfill_item_category_resolution(
            task_key=task_key,
            canonical_category_code=resolve_category_code(category_code) if category_code else None,
            limit=limit,
            dry_run=dry_run,
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("cleanup-item-category-domain-mismatches")
    def cleanup_item_category_domain_mismatches(
        category_code: str = typer.Option(..., help="Canonical category code to repair."),
        dry_run: bool = True,
        limit: int | None = typer.Option(default=None, min=1),
    ) -> None:
        """Repair historical item/category-domain mismatches within one canonical category."""
        summary = _cleanup_item_category_domain_mismatches(
            category_code=category_code,
            dry_run=dry_run,
            limit=limit,
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("reconcile-item-category-domain-state")
    def reconcile_item_category_domain_state_command(
        category_code: str = typer.Option(..., help="Canonical category code to reconcile."),
        dry_run: bool = True,
        limit: int | None = typer.Option(default=None, min=1),
    ) -> None:
        """Reconcile historical category-domain state, including restore, redirect, and block actions."""
        summary = _reconcile_item_category_domain_state(
            category_code=category_code,
            dry_run=dry_run,
            limit=limit,
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("audit-camera-listing-shapes")
    def audit_camera_listing_shapes_command(
        category_code: str | None = typer.Option(
            default=None,
            help="Optional camera category filter: camera_body or camera_interchangeable_lens.",
        ),
        active_only: bool = typer.Option(
            True,
            "--active-only/--include-inactive",
            help="Audit only active items by default.",
        ),
        limit: int | None = typer.Option(default=None, min=1),
        sample_limit: int = typer.Option(default=20, min=1, max=200),
    ) -> None:
        """Audit camera listing shapes and suggest keep/redirect/block/review actions."""
        summary = _audit_camera_listing_shapes(
            category_code=category_code,
            active_only=active_only,
            limit=limit,
            sample_limit=sample_limit,
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("repair-camera-listing-shapes")
    def repair_camera_listing_shapes_command(
        category_code: str | None = typer.Option(
            default=None,
            help="Optional camera category filter: camera_body or camera_interchangeable_lens.",
        ),
        dry_run: bool = True,
        active_only: bool = typer.Option(
            True,
            "--active-only/--include-inactive",
            help="Repair only active items by default.",
        ),
        limit: int | None = typer.Option(default=None, min=1),
        sample_limit: int = typer.Option(default=50, min=1, max=500),
        min_confidence: float = typer.Option(default=0.9, min=0.5, max=1.0),
    ) -> None:
        """Repair high-confidence camera listing shape mismatches across body/lens domains."""
        summary = _repair_camera_listing_shapes(
            category_code=category_code,
            dry_run=dry_run,
            active_only=active_only,
            limit=limit,
            sample_limit=sample_limit,
            min_confidence=min_confidence,
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("backfill-task-categories")
    def backfill_task_categories_command(
        task_key: str | None = None,
        force: bool = False,
    ) -> None:
        summary = backfill_task_category_bindings(
            task_key=task_key,
            force=force,
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))
