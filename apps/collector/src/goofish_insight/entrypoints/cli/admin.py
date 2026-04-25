from __future__ import annotations

import json
from pathlib import Path

import typer
from sqlalchemy import select

try:
    from alembic import command as alembic_command
except ModuleNotFoundError:  # pragma: no cover - exercised in lightweight runtime environments
    alembic_command = None

from ...category_compat import (
    category_compat_retirement_summary,
    resolve_category_code,
)
from ...application.services.catalog_preview import (
    preview_catalog_signature,
    preview_catalog_snapshot,
)
from ...application.services.catalog_backfill import (
    build_catalog_backfill_reconciliation_report,
    CatalogBackfillPreviewError,
    build_catalog_backfill_template_payload,
    ensure_catalog_backfill_template,
    persist_catalog_backfill_batch,
    persist_catalog_backfill_item,
    persist_catalog_backfill_template,
    preview_catalog_backfill_batch,
    preview_catalog_backfill_item,
    run_catalog_backfill_migration,
)
from ...application.services.catalog_persistence import (
    persist_catalog_payload,
    replace_catalog_payload,
)
from ...application.services.catalog_queries import (
    build_catalog_category_templates,
    build_catalog_sku_page,
    build_catalog_spu_page,
    build_catalog_spu_detail,
    build_catalog_template_detail,
)
from ...application.services.catalog_outbox import (
    build_catalog_outbox_rows,
    process_catalog_outbox_events,
)
from ...application.services.catalog_migration_checks import (
    build_catalog_migration_report,
    build_catalog_pricing_dual_read_report,
    build_catalog_scoped_migration_report,
    run_catalog_pricing_dual_read_backfill,
)
from ...application.services.catalog_category_quality import (
    build_catalog_category_scope_audit,
    quarantine_catalog_category_scope_mismatches,
)
from ...application.services.feed_pre_ingest_reporting import (
    build_feed_pre_ingest_rejection_report,
)
from ...application.services.feed_decision_reporting import (
    build_home_feed_decision_report,
)
from ...application.services.catalog_template_version import (
    persist_catalog_template_version_payload,
)
from ...application.services.catalog_upgrade import (
    apply_catalog_template_upgrade,
    apply_catalog_template_replace_plan,
    preview_catalog_template_replace_plan,
    preview_catalog_template_upgrade,
)
from ...application.services.catalog_template import (
    CatalogTemplatePersistenceError,
    persist_catalog_template_payload,
)
from ...application.services.catalog_write import prepare_catalog_persist_plan
from ...application.services.model_catalog_bootstrap import (
    apply_model_catalog_bootstrap,
    ModelCatalogBootstrapError,
    preview_model_catalog_bootstrap,
)
from ...application.services.model_catalog_scope_audit import (
    build_model_catalog_scope_audit,
    cleanup_model_catalog_scope_mismatches,
)
from ...application.services.template_attribute_audit import (
    apply_template_attribute_supplements,
    build_template_attribute_audit,
)
from ...application.services.xianyu_category_mapping import (
    backfill_xianyu_raw_category_signals,
    build_xianyu_raw_category_coverage_report,
    build_xianyu_category_onboarding_draft,
    list_xianyu_category_onboarding_queue,
    sync_xianyu_category_onboarding_queue,
    update_xianyu_category_onboarding_queue_status,
    XianyuCategoryMappingError,
    build_xianyu_raw_category_summary,
    persist_xianyu_category_onboarding,
)
from ...application.services.xianyu_category_autofill import (
    apply_xianyu_category_auto_supplement,
    build_xianyu_category_auto_supplement_plan,
    XianyuCategoryAutoSupplementError,
)
from ...db import session_scope
from ...models import BrowserSession, CrawlRun


def _normalize_scope_text(value: str | None) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _resolve_admin_scope_category_code(
    *,
    category_code: str | None,
    business_domain: str | None,
) -> str:
    preferred_scope = _normalize_scope_text(category_code)
    legacy_scope = _normalize_scope_text(business_domain)
    if preferred_scope is None and legacy_scope is None:
        raise typer.BadParameter(
            "Provide category_code as argument (preferred) or --business-domain as legacy alias."
        )

    if preferred_scope is not None and legacy_scope is not None:
        preferred_canonical = resolve_category_code(preferred_scope)
        legacy_canonical = resolve_category_code(legacy_scope)
        if preferred_canonical != legacy_canonical:
            raise typer.BadParameter(
                f"category_code '{preferred_scope}' conflicts with --business-domain '{legacy_scope}'."
            )

    return resolve_category_code(preferred_scope or legacy_scope)


def register_admin_commands(
    app: typer.Typer,
    *,
    alembic_config,
    discover_attached_browsers,
) -> None:
    @app.command("show-category-compat-retirement")
    def show_category_compat_retirement_command() -> None:
        typer.echo(json.dumps(category_compat_retirement_summary(), ensure_ascii=False, indent=2))

    @app.command("db-upgrade")
    def db_upgrade(revision: str = "head") -> None:
        if alembic_command is None:
            raise typer.BadParameter("alembic is required for db-upgrade. Install project dependencies first.")
        alembic_command.upgrade(alembic_config(), revision)
        typer.echo(f"Database upgraded to {revision}.")

    @app.command("db-current")
    def db_current() -> None:
        if alembic_command is None:
            raise typer.BadParameter("alembic is required for db-current. Install project dependencies first.")
        alembic_command.current(alembic_config())

    @app.command("show-health")
    def show_health(limit: int = 5) -> None:
        with session_scope() as session:
            runs = session.execute(select(CrawlRun).order_by(CrawlRun.started_at.desc()).limit(limit)).scalars()
            for run in runs:
                typer.echo(
                    json.dumps(
                        {
                            "run_id": str(run.id),
                            "task_id": run.task_id,
                            "status": run.status,
                            "started_at": run.started_at.isoformat(),
                            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                            "pages_succeeded": run.pages_succeeded,
                            "error_message": run.error_message,
                        },
                        ensure_ascii=False,
                    )
                )

    @app.command("show-browser-sessions")
    def show_browser_sessions(limit: int = 5) -> None:
        with session_scope() as session:
            sessions = session.execute(
                select(BrowserSession).order_by(BrowserSession.updated_at.desc()).limit(limit)
            ).scalars()
            for item in sessions:
                typer.echo(
                    json.dumps(
                        {
                            "profile_key": item.profile_key,
                            "profile_dir": item.profile_dir,
                            "browser_channel": item.browser_channel,
                            "auth_state": item.auth_state,
                            "last_login_required_at": item.last_login_required_at.isoformat() if item.last_login_required_at else None,
                            "last_authenticated_at": item.last_authenticated_at.isoformat() if item.last_authenticated_at else None,
                            "last_error": item.last_error,
                        },
                        ensure_ascii=False,
                    )
                )

    @app.command("show-attached-browsers")
    def show_attached_browsers(only_goofish: bool = False) -> None:
        candidates = discover_attached_browsers()
        rows = []
        for candidate in candidates:
            tabs = candidate["tabs"]
            if only_goofish:
                tabs = [tab for tab in tabs if tab["is_goofish"]]
                if not tabs:
                    continue
            rows.append(
                {
                    "process_id": candidate["process_id"],
                    "cdp_url": candidate["cdp_url"],
                    "goofish_tab_count": candidate["goofish_tab_count"],
                    "tab_count": len(tabs),
                    "tabs": tabs,
                }
            )
        typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))

    @app.command("serve-web")
    def serve_web(
        host: str = "127.0.0.1",
        port: int = 8787,
        reload: bool = False,
    ) -> None:
        import uvicorn

        uvicorn.run(
            "goofish_insight.entrypoints.web.app:create_app",
            factory=True,
            host=host,
            port=port,
            reload=reload,
        )

    @app.command("preview-catalog-signature")
    def preview_catalog_signature_command(payload_path: Path) -> None:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        typer.echo(
            json.dumps(
                preview_catalog_signature(payload),
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("preview-catalog-snapshot")
    def preview_catalog_snapshot_command(payload_path: Path) -> None:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        typer.echo(
            json.dumps(
                preview_catalog_snapshot(payload),
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("preview-catalog-persist-plan")
    def preview_catalog_persist_plan_command(payload_path: Path) -> None:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        typer.echo(
            json.dumps(
                prepare_catalog_persist_plan(payload),
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("preview-catalog-backfill-item")
    def preview_catalog_backfill_item_command(
        item_id: str,
        category_id: str | None = None,
        template_id: str | None = None,
    ) -> None:
        try:
            detail = preview_catalog_backfill_item(
                item_id=item_id,
                category_id=category_id,
                template_id=template_id,
            )
        except CatalogBackfillPreviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("preview-catalog-backfill-batch")
    def preview_catalog_backfill_batch_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code (preferred).",
        ),
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
        limit: int = 20,
        offset: int = 0,
        enriched_only: bool = typer.Option(False, "--enriched-only/--include-unenriched"),
        category_id: str | None = None,
        template_id: str | None = None,
    ) -> None:
        resolved_category_code = _resolve_admin_scope_category_code(
            category_code=category_code,
            business_domain=business_domain,
        )
        try:
            detail = preview_catalog_backfill_batch(
                business_domain=resolved_category_code,
                limit=limit,
                offset=offset,
                enriched_only=enriched_only,
                category_id=category_id,
                template_id=template_id,
            )
        except CatalogBackfillPreviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("preview-catalog-backfill-template")
    def preview_catalog_backfill_template_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code (preferred).",
        ),
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
    ) -> None:
        resolved_category_code = _resolve_admin_scope_category_code(
            category_code=category_code,
            business_domain=business_domain,
        )
        try:
            detail = build_catalog_backfill_template_payload(
                business_domain=resolved_category_code,
            )
        except CatalogBackfillPreviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("persist-catalog-backfill-template")
    def persist_catalog_backfill_template_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code (preferred).",
        ),
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
        operator_id: str = "admin",
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        resolved_category_code = _resolve_admin_scope_category_code(
            category_code=category_code,
            business_domain=business_domain,
        )
        try:
            detail = persist_catalog_backfill_template(
                business_domain=resolved_category_code,
                operator_id=operator_id,
                dry_run=dry_run,
            )
        except CatalogBackfillPreviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("preview-model-catalog-bootstrap")
    def preview_model_catalog_bootstrap_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code (preferred).",
        ),
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
        min_sample_count: int = 20,
        limit: int = 0,
        active_only: bool = typer.Option(True, "--active-only/--include-inactive"),
        name_query: str | None = typer.Option(None, "--name-query"),
    ) -> None:
        resolved_category_code = _resolve_admin_scope_category_code(
            category_code=category_code,
            business_domain=business_domain,
        )
        try:
            detail = preview_model_catalog_bootstrap(
                business_domain=resolved_category_code,
                min_sample_count=min_sample_count,
                limit=limit,
                active_only=active_only,
                name_query=name_query,
            )
        except ModelCatalogBootstrapError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("apply-model-catalog-bootstrap")
    def apply_model_catalog_bootstrap_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code (preferred).",
        ),
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
        operator_id: str = "admin",
        min_sample_count: int = 20,
        limit: int = 0,
        active_only: bool = typer.Option(True, "--active-only/--include-inactive"),
        name_query: str | None = typer.Option(None, "--name-query"),
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        resolved_category_code = _resolve_admin_scope_category_code(
            category_code=category_code,
            business_domain=business_domain,
        )
        try:
            detail = apply_model_catalog_bootstrap(
                business_domain=resolved_category_code,
                operator_id=operator_id,
                min_sample_count=min_sample_count,
                limit=limit,
                active_only=active_only,
                name_query=name_query,
                dry_run=dry_run,
            )
        except ModelCatalogBootstrapError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("audit-template-attributes")
    def audit_template_attributes_command(
        category_code: list[str] | None = typer.Option(None, "--category-code"),
    ) -> None:
        detail = build_template_attribute_audit(
            category_codes=tuple(category_code) if category_code else None,
        )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("apply-template-attribute-supplements")
    def apply_template_attribute_supplements_command(
        operator_id: str = "admin",
        category_code: list[str] | None = typer.Option(None, "--category-code"),
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        detail = apply_template_attribute_supplements(
            operator_id=operator_id,
            category_codes=tuple(category_code) if category_code else None,
            dry_run=dry_run,
        )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("ensure-catalog-backfill-template")
    def ensure_catalog_backfill_template_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code (preferred).",
        ),
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
        operator_id: str = "admin",
        dry_run: bool = typer.Option(False, "--dry-run/--apply"),
    ) -> None:
        resolved_category_code = _resolve_admin_scope_category_code(
            category_code=category_code,
            business_domain=business_domain,
        )
        try:
            detail = ensure_catalog_backfill_template(
                business_domain=resolved_category_code,
                operator_id=operator_id,
                dry_run=dry_run,
            )
        except CatalogBackfillPreviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("persist-catalog-backfill-item")
    def persist_catalog_backfill_item_command(
        item_id: str,
        operator_id: str = "admin",
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
        allow_warnings: bool = typer.Option(False, "--allow-warnings/--strict"),
        category_id: str | None = None,
        template_id: str | None = None,
    ) -> None:
        try:
            detail = persist_catalog_backfill_item(
                item_id=item_id,
                operator_id=operator_id,
                dry_run=dry_run,
                allow_warnings=allow_warnings,
                category_id=category_id,
                template_id=template_id,
            )
        except CatalogBackfillPreviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("persist-catalog-backfill-batch")
    def persist_catalog_backfill_batch_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code (preferred).",
        ),
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
        operator_id: str = "admin",
        limit: int = 20,
        offset: int = 0,
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
        enriched_only: bool = typer.Option(True, "--enriched-only/--include-unenriched"),
        allow_warnings: bool = typer.Option(False, "--allow-warnings/--strict"),
        skip_existing: bool = typer.Option(True, "--skip-existing/--fail-existing"),
        category_id: str | None = None,
        template_id: str | None = None,
    ) -> None:
        resolved_category_code = _resolve_admin_scope_category_code(
            category_code=category_code,
            business_domain=business_domain,
        )
        try:
            detail = persist_catalog_backfill_batch(
                business_domain=resolved_category_code,
                operator_id=operator_id,
                limit=limit,
                offset=offset,
                dry_run=dry_run,
                enriched_only=enriched_only,
                allow_warnings=allow_warnings,
                skip_existing=skip_existing,
                category_id=category_id,
                template_id=template_id,
            )
        except CatalogBackfillPreviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("run-catalog-backfill-migration")
    def run_catalog_backfill_migration_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code (preferred).",
        ),
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
        operator_id: str = "admin",
        batch_size: int = 100,
        dry_run: bool = typer.Option(False, "--dry-run/--apply"),
        enriched_only: bool = typer.Option(True, "--enriched-only/--include-unenriched"),
        allow_warnings: bool = typer.Option(False, "--allow-warnings/--strict"),
        skip_existing: bool = typer.Option(True, "--skip-existing/--fail-existing"),
        process_outbox_after_batch: bool = typer.Option(True, "--process-outbox/--skip-outbox"),
        max_batches: int | None = None,
    ) -> None:
        resolved_category_code = _resolve_admin_scope_category_code(
            category_code=category_code,
            business_domain=business_domain,
        )
        try:
            detail = run_catalog_backfill_migration(
                business_domain=resolved_category_code,
                operator_id=operator_id,
                batch_size=batch_size,
                dry_run=dry_run,
                enriched_only=enriched_only,
                allow_warnings=allow_warnings,
                skip_existing=skip_existing,
                process_outbox_after_batch=process_outbox_after_batch,
                max_batches=max_batches,
            )
        except CatalogBackfillPreviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("report-catalog-backfill-reconciliation")
    def report_catalog_backfill_reconciliation_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code (preferred).",
        ),
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
    ) -> None:
        resolved_category_code = _resolve_admin_scope_category_code(
            category_code=category_code,
            business_domain=business_domain,
        )
        try:
            detail = build_catalog_backfill_reconciliation_report(
                business_domain=resolved_category_code,
            )
        except CatalogBackfillPreviewError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("audit-catalog-category-scope")
    def audit_catalog_category_scope_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code. Omit to audit all catalog categories.",
        ),
        active_only: bool = typer.Option(True, "--active-only/--include-inactive"),
    ) -> None:
        resolved_category_code = resolve_category_code(category_code) if category_code else None
        with session_scope() as session:
            detail = build_catalog_category_scope_audit(
                session,
                category_code=resolved_category_code,
                active_only=active_only,
            )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("cleanup-catalog-category-scope")
    def cleanup_catalog_category_scope_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code. Omit to clean all catalog categories.",
        ),
        operator_id: str = "admin",
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        resolved_category_code = resolve_category_code(category_code) if category_code else None
        with session_scope() as session:
            detail = quarantine_catalog_category_scope_mismatches(
                session,
                category_code=resolved_category_code,
                operator_id=operator_id,
                dry_run=dry_run,
            )
            if dry_run:
                session.rollback()
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("audit-model-catalog-scope")
    def audit_model_catalog_scope_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code. Omit to audit all model catalog categories.",
        ),
        active_only: bool = typer.Option(True, "--active-only/--include-inactive"),
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
    ) -> None:
        resolved_category_code = (
            _resolve_admin_scope_category_code(
                category_code=category_code,
                business_domain=business_domain,
            )
            if category_code or business_domain
            else None
        )
        with session_scope() as session:
            detail = build_model_catalog_scope_audit(
                session,
                category_code=resolved_category_code,
                active_only=active_only,
            )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("cleanup-model-catalog-scope")
    def cleanup_model_catalog_scope_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code. Omit to clean all model catalog categories.",
        ),
        operator_id: str = "admin",
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
    ) -> None:
        resolved_category_code = (
            _resolve_admin_scope_category_code(
                category_code=category_code,
                business_domain=business_domain,
            )
            if category_code or business_domain
            else None
        )
        with session_scope() as session:
            detail = cleanup_model_catalog_scope_mismatches(
                session,
                category_code=resolved_category_code,
                operator_id=operator_id,
                dry_run=dry_run,
            )
            if dry_run:
                session.rollback()
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("report-feed-pre-ingest-rejections")
    def report_feed_pre_ingest_rejections_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code. Omit to report all feed pre-ingest rejections.",
        ),
        limit: int = 20,
        sample_limit: int = 20,
        log_scan_lines: int = 400,
        source_platform: str = "xianyu",
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
    ) -> None:
        resolved_category_code = (
            _resolve_admin_scope_category_code(
                category_code=category_code,
                business_domain=business_domain,
            )
            if category_code or business_domain
            else None
        )
        with session_scope() as session:
            detail = build_feed_pre_ingest_rejection_report(
                session,
                category_code=resolved_category_code,
                source_platform=source_platform,
                limit=limit,
                sample_limit=sample_limit,
                log_scan_lines=log_scan_lines,
            )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("report-home-feed-decisions")
    def report_home_feed_decisions_command(
        category_code: str | None = typer.Argument(
            None,
            help="Canonical category code. Omit to report all home feed decisions.",
        ),
        lookback_days: int = typer.Option(7, min=1, max=365),
        limit: int = typer.Option(50, min=1, max=500),
        source_platform: str = "xianyu",
        business_domain: str | None = typer.Option(
            None,
            "--business-domain",
            help="Legacy scope alias, kept only for compatibility.",
        ),
    ) -> None:
        resolved_category_code = (
            _resolve_admin_scope_category_code(
                category_code=category_code,
                business_domain=business_domain,
            )
            if category_code or business_domain
            else None
        )
        with session_scope() as session:
            detail = build_home_feed_decision_report(
                session,
                category_code=resolved_category_code,
                source_platform=source_platform,
                lookback_days=lookback_days,
                limit=limit,
            )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("persist-catalog-payload")
    def persist_catalog_payload_command(
        payload_path: Path,
        operator_id: str = "admin",
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        typer.echo(
            json.dumps(
                persist_catalog_payload(
                    payload=payload,
                    operator_id=operator_id,
                    dry_run=dry_run,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("replace-catalog-payload")
    def replace_catalog_payload_command(
        payload_path: Path,
        operator_id: str = "admin",
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        typer.echo(
            json.dumps(
                replace_catalog_payload(
                    payload=payload,
                    operator_id=operator_id,
                    dry_run=dry_run,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("persist-catalog-template-payload")
    def persist_catalog_template_payload_command(
        payload_path: Path,
        operator_id: str = "admin",
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        typer.echo(
            json.dumps(
                persist_catalog_template_payload(
                    payload=payload,
                    operator_id=operator_id,
                    dry_run=dry_run,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("persist-catalog-template-version")
    def persist_catalog_template_version_command(
        payload_path: Path,
        operator_id: str = "admin",
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        typer.echo(
            json.dumps(
                persist_catalog_template_version_payload(
                    payload=payload,
                    operator_id=operator_id,
                    dry_run=dry_run,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("summarize-xianyu-raw-categories")
    def summarize_xianyu_raw_categories_command(
        source_keyword: str | None = None,
        task_id: int | None = None,
        business_domain: str | None = None,
        limit: int = 20,
        item_scan_limit: int = 2000,
        unmapped_only: bool = False,
    ) -> None:
        detail = build_xianyu_raw_category_summary(
            source_keyword=source_keyword,
            task_id=task_id,
            business_domain=business_domain,
            limit=limit,
            item_scan_limit=item_scan_limit,
            unmapped_only=unmapped_only,
        )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("report-xianyu-raw-category-coverage")
    def report_xianyu_raw_category_coverage_command(
        source_keyword: str | None = None,
        task_id: int | None = None,
        business_domain: str | None = None,
        unmapped_limit: int = 20,
        item_scan_limit: int = 2000,
    ) -> None:
        detail = build_xianyu_raw_category_coverage_report(
            source_keyword=source_keyword,
            task_id=task_id,
            business_domain=business_domain,
            unmapped_limit=unmapped_limit,
            item_scan_limit=item_scan_limit,
        )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("auto-supplement-xianyu-category-mappings")
    def auto_supplement_xianyu_category_mappings_command(
        category_code: str | None = typer.Argument(None),
        business_domain: str | None = None,
        operator_id: str = "admin",
        sample_limit: int = 12,
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        resolved_category_code = None
        if category_code is not None or business_domain is not None:
            resolved_category_code = _resolve_admin_scope_category_code(
                category_code=category_code,
                business_domain=business_domain,
            )
        try:
            if dry_run:
                detail = build_xianyu_category_auto_supplement_plan(
                    category_code=resolved_category_code,
                    sample_limit=sample_limit,
                )
            else:
                detail = apply_xianyu_category_auto_supplement(
                    operator_id=operator_id,
                    category_code=resolved_category_code,
                    sample_limit=sample_limit,
                    dry_run=False,
                )
        except XianyuCategoryAutoSupplementError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("draft-xianyu-category-onboarding")
    def draft_xianyu_category_onboarding_command(
        source_keyword: str | None = None,
        task_id: int | None = None,
        business_domain: str | None = None,
        xianyu_cat_id: str | None = None,
        xianyu_tb_cat_id: str | None = None,
        xianyu_c_cat_id: str | None = None,
        sample_limit: int = 25,
        prefer_unmapped: bool = True,
    ) -> None:
        detail = build_xianyu_category_onboarding_draft(
            source_keyword=source_keyword,
            task_id=task_id,
            business_domain=business_domain,
            xianyu_cat_id=xianyu_cat_id,
            xianyu_tb_cat_id=xianyu_tb_cat_id,
            xianyu_c_cat_id=xianyu_c_cat_id,
            sample_limit=sample_limit,
            prefer_unmapped=prefer_unmapped,
        )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("persist-xianyu-category-onboarding")
    def persist_xianyu_category_onboarding_command(
        payload_path: Path,
        operator_id: str = "admin",
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        try:
            detail = persist_xianyu_category_onboarding(
                payload=payload,
                operator_id=operator_id,
                dry_run=dry_run,
            )
        except (CatalogTemplatePersistenceError, XianyuCategoryMappingError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("backfill-xianyu-raw-category-signals")
    def backfill_xianyu_raw_category_signals_command(
        source_keyword: str | None = None,
        task_id: int | None = None,
        business_domain: str | None = None,
        limit: int = 500,
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
        overwrite: bool = False,
    ) -> None:
        detail = backfill_xianyu_raw_category_signals(
            source_keyword=source_keyword,
            task_id=task_id,
            business_domain=business_domain,
            limit=limit,
            dry_run=dry_run,
            overwrite=overwrite,
        )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("sync-xianyu-onboarding-queue")
    def sync_xianyu_onboarding_queue_command(
        operator_id: str = "admin",
        source_keyword: str | None = None,
        task_id: int | None = None,
        business_domain: str | None = None,
        item_scan_limit: int = 2000,
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        detail = sync_xianyu_category_onboarding_queue(
            operator_id=operator_id,
            source_keyword=source_keyword,
            task_id=task_id,
            business_domain=business_domain,
            item_scan_limit=item_scan_limit,
            dry_run=dry_run,
        )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("list-xianyu-onboarding-queue")
    def list_xianyu_onboarding_queue_command(
        status: str | None = None,
        include_closed: bool = False,
        limit: int = 50,
    ) -> None:
        detail = list_xianyu_category_onboarding_queue(
            status=status,
            include_closed=include_closed,
            limit=limit,
        )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("update-xianyu-onboarding-queue")
    def update_xianyu_onboarding_queue_command(
        status: str,
        operator_id: str = "admin",
        queue_id: str | None = None,
        match_key: str | None = None,
        owner_operator_id: str | None = None,
        status_note: str | None = None,
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        try:
            detail = update_xianyu_category_onboarding_queue_status(
                operator_id=operator_id,
                status=status,
                queue_id=queue_id,
                match_key=match_key,
                owner_operator_id=owner_operator_id,
                status_note=status_note,
                dry_run=dry_run,
            )
        except XianyuCategoryMappingError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("show-catalog-spu")
    def show_catalog_spu_command(spu_id: str) -> None:
        with session_scope() as session:
            detail = build_catalog_spu_detail(session, spu_id)
        if detail is None:
            raise typer.Exit(code=1)
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("list-catalog-spus")
    def list_catalog_spus_command(
        category_id: str | None = None,
        template_id: str | None = None,
        merchant_id: str | None = None,
        status: str | None = None,
        title: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> None:
        with session_scope() as session:
            detail = build_catalog_spu_page(
                session,
                page=page,
                page_size=page_size,
                category_id=category_id,
                template_id=template_id,
                merchant_id=merchant_id,
                status=status,
                title=title,
            )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("list-catalog-skus")
    def list_catalog_skus_command(
        spu_id: str | None = None,
        category_id: str | None = None,
        template_id: str | None = None,
        merchant_id: str | None = None,
        status: str | None = None,
        sku_code: str | None = None,
        title: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> None:
        with session_scope() as session:
            detail = build_catalog_sku_page(
                session,
                page=page,
                page_size=page_size,
                spu_id=spu_id,
                category_id=category_id,
                template_id=template_id,
                merchant_id=merchant_id,
                status=status,
                sku_code=sku_code,
                title=title,
            )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("show-catalog-template")
    def show_catalog_template_command(template_id: str) -> None:
        with session_scope() as session:
            detail = build_catalog_template_detail(session, template_id)
        if detail is None:
            raise typer.Exit(code=1)
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("list-catalog-templates")
    def list_catalog_templates_command(category_id: str) -> None:
        with session_scope() as session:
            detail = build_catalog_category_templates(session, category_id)
        if detail is None:
            raise typer.Exit(code=1)
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("show-catalog-outbox")
    def show_catalog_outbox_command(limit: int = 20) -> None:
        with session_scope() as session:
            rows = build_catalog_outbox_rows(session, limit=limit)
        typer.echo(json.dumps(rows, ensure_ascii=False, indent=2, default=str))

    @app.command("process-catalog-outbox")
    def process_catalog_outbox_command(
        limit: int = 20,
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        typer.echo(
            json.dumps(
                process_catalog_outbox_events(limit=limit, dry_run=dry_run),
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

    @app.command("check-catalog-migration")
    def check_catalog_migration_command(
        category_id: str | None = None,
        spu_id: str | None = None,
        expected_template_id: str | None = None,
        page_size: int = 20,
    ) -> None:
        with session_scope() as session:
            detail = build_catalog_migration_report(
                session,
                category_id=category_id,
                spu_id=spu_id,
                expected_template_id=expected_template_id,
                page_size=page_size,
            )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("check-catalog-scoped-migration")
    def check_catalog_scoped_migration_command(
        category_id: str | None = None,
        spu_id: str | None = None,
        expected_template_id: str | None = None,
        business_domain: list[str] | None = typer.Option(None, "--business-domain"),
        expected_coverage_ratio: float = 1.0,
        page_size: int = 20,
    ) -> None:
        with session_scope() as session:
            detail = build_catalog_scoped_migration_report(
                session,
                category_id=category_id,
                spu_id=spu_id,
                expected_template_id=expected_template_id,
                business_domains=business_domain,
                expected_coverage_ratio=expected_coverage_ratio,
                page_size=page_size,
            )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("check-catalog-pricing-dual-read")
    def check_catalog_pricing_dual_read_command(
        business_domain: list[str] | None = typer.Option(None, "--business-domain"),
        freshness_days: int = 30,
        expected_spu_coverage_ratio: float = 0.95,
        expected_price_match_ratio: float = 0.97,
        sample_limit: int = 20,
    ) -> None:
        with session_scope() as session:
            detail = build_catalog_pricing_dual_read_report(
                session,
                business_domains=business_domain,
                freshness_days=freshness_days,
                expected_spu_coverage_ratio=expected_spu_coverage_ratio,
                expected_price_match_ratio=expected_price_match_ratio,
                sample_limit=sample_limit,
            )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("backfill-catalog-pricing-dual-read")
    def backfill_catalog_pricing_dual_read_command(
        business_domain: list[str] | None = typer.Option(None, "--business-domain"),
        operator_id: str = "catalog-pricing-dual-read",
        freshness_days: int = 7,
        limit: int = 100,
        offset: int = 0,
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
        allow_warnings: bool = typer.Option(True, "--allow-warnings/--strict-warnings"),
        process_outbox: bool = typer.Option(False, "--process-outbox/--skip-outbox"),
        min_spu_attribute_count: int = 0,
        min_sku_attribute_count: int = 0,
        sample_limit: int = 20,
    ) -> None:
        with session_scope() as session:
            detail = run_catalog_pricing_dual_read_backfill(
                session,
                business_domains=business_domain,
                operator_id=operator_id,
                freshness_days=freshness_days,
                limit=limit,
                offset=offset,
                dry_run=dry_run,
                allow_warnings=allow_warnings,
                process_outbox=process_outbox,
                min_spu_attribute_count=min_spu_attribute_count,
                min_sku_attribute_count=min_sku_attribute_count,
                sample_limit=sample_limit,
            )
        typer.echo(json.dumps(detail, ensure_ascii=False, indent=2, default=str))

    @app.command("preview-catalog-template-upgrade")
    def preview_catalog_template_upgrade_command(
        spu_id: str,
        target_template_id: str,
    ) -> None:
        typer.echo(
            json.dumps(
                preview_catalog_template_upgrade(
                    spu_id=spu_id,
                    target_template_id=target_template_id,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("preview-catalog-template-replace-plan")
    def preview_catalog_template_replace_plan_command(
        spu_id: str,
        target_template_id: str,
    ) -> None:
        typer.echo(
            json.dumps(
                preview_catalog_template_replace_plan(
                    spu_id=spu_id,
                    target_template_id=target_template_id,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("apply-catalog-template-upgrade")
    def apply_catalog_template_upgrade_command(
        spu_id: str,
        target_template_id: str,
        operator_id: str = "admin",
        request_id: str | None = None,
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        typer.echo(
            json.dumps(
                apply_catalog_template_upgrade(
                    spu_id=spu_id,
                    target_template_id=target_template_id,
                    operator_id=operator_id,
                    request_id=request_id,
                    dry_run=dry_run,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

    @app.command("apply-catalog-template-replace-plan")
    def apply_catalog_template_replace_plan_command(
        spu_id: str,
        target_template_id: str,
        operator_id: str = "admin",
        request_id: str | None = None,
        dry_run: bool = typer.Option(True, "--dry-run/--apply"),
    ) -> None:
        typer.echo(
            json.dumps(
                apply_catalog_template_replace_plan(
                    spu_id=spu_id,
                    target_template_id=target_template_id,
                    operator_id=operator_id,
                    request_id=request_id,
                    dry_run=dry_run,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
