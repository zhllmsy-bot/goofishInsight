from __future__ import annotations

import json
import time
from datetime import datetime
from ...compat import UTC
from decimal import Decimal

import typer

from ...application.services.browser_guard import (
    evaluate_browser_guard_preflight,
    format_browser_guard_preflight_message,
)
from ...application.services.collector_browser import infer_auth_state_from_error_message


DEFAULT_MESSAGE_TEXT = (
    "\u4f60\u597d\uff0c\u8bf7\u95ee\uff0c\u4ef7\u683c\u8fd8\u6709\u7a7a\u95f4\u5417\uff1f"
)


def register_feed_commands(
    app: typer.Typer,
    *,
    load_profile_settings,
    resolve_cdp_url,
    run_home_feed_refresh,
) -> None:
    @app.command("refresh-home-feed")
    def refresh_home_feed(
        profile_key: str = "chrome-attached",
        business_domain: str | None = None,
        max_cards: int = typer.Option(20, min=1, max=60),
        max_messages: int = typer.Option(3, min=0, max=20),
        min_message_interval_seconds: int = typer.Option(15, min=5, max=120),
        freshness_days: int = typer.Option(30, min=7, max=180),
        min_sample_points: int = typer.Option(4, min=2, max=20),
        message_text: str = DEFAULT_MESSAGE_TEXT,
        dry_run: bool = False,
        require_actionable_band: bool = False,
        only_within_target_price: bool = False,
        min_profit_margin_pct: float = typer.Option(10.0, min=0.0, max=100.0),
    ) -> None:
        profile_settings = load_profile_settings(profile_key)
        cdp_url = resolve_cdp_url(profile_settings.get("cdp_url"))
        if not cdp_url:
            raise RuntimeError("Home feed refresh requires an attached Chrome instance with CDP enabled.")

        guard_decision = evaluate_browser_guard_preflight(
            profile_key=profile_key,
            feature="home_feed",
            scope_key=business_domain,
        )
        if not guard_decision["allowed"]:
            typer.echo(
                json.dumps(
                    {
                        "status": "blocked_by_browser_guard",
                        "browser_guard": guard_decision,
                        "message": format_browser_guard_preflight_message(guard_decision),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        summary = run_home_feed_refresh(
            cdp_url=cdp_url,
            profile_key=profile_key,
            business_domain=business_domain,
            max_cards=max_cards,
            max_messages=max_messages,
            min_message_interval_seconds=min_message_interval_seconds,
            freshness_days=freshness_days,
            min_sample_points=min_sample_points,
            message_text=message_text,
            dry_run=dry_run,
            require_actionable_band=require_actionable_band,
            only_within_target_price=only_within_target_price,
            min_profit_margin_pct=Decimal(str(min_profit_margin_pct)),
        )
        typer.echo(json.dumps(summary, ensure_ascii=False, indent=2))

    @app.command("watch-home-feed")
    def watch_home_feed(
        profile_key: str = "chrome-attached",
        business_domain: str | None = None,
        interval_seconds: int = typer.Option(20, min=5, max=3600),
        max_cards: int = typer.Option(20, min=1, max=60),
        max_messages: int = typer.Option(1, min=0, max=20),
        min_message_interval_seconds: int = typer.Option(15, min=5, max=120),
        freshness_days: int = typer.Option(30, min=7, max=180),
        min_sample_points: int = typer.Option(4, min=2, max=20),
        message_text: str = DEFAULT_MESSAGE_TEXT,
        dry_run: bool = False,
        require_actionable_band: bool = False,
        only_within_target_price: bool = False,
        min_profit_margin_pct: float = typer.Option(10.0, min=0.0, max=100.0),
        max_cycles: int | None = typer.Option(None, min=1),
    ) -> None:
        profile_settings = load_profile_settings(profile_key)
        cdp_url = resolve_cdp_url(profile_settings.get("cdp_url"))
        if not cdp_url:
            raise RuntimeError("Home feed watch requires an attached Chrome instance with CDP enabled.")

        typer.echo(
            f"Watching home feed every {interval_seconds}s "
            f"(dry_run={dry_run}, category_entry_mode=true, "
            f"require_actionable_band={require_actionable_band}, max_messages={max_messages})."
        )

        cycle = 0
        while True:
            cycle += 1
            started_at = datetime.now(UTC)
            post_guard_sleep_seconds = 0
            cycle_auth_state = None
            guard_decision = evaluate_browser_guard_preflight(
                profile_key=profile_key,
                feature="home_feed",
                scope_key=business_domain,
            )
            if not guard_decision["allowed"]:
                typer.echo(
                    json.dumps(
                        {
                            "generated_at": datetime.now(UTC).isoformat(),
                            "watch_cycle": cycle,
                            "profile_key": profile_key,
                            "business_domain": business_domain,
                            "interval_seconds": interval_seconds,
                            "status": "blocked_by_browser_guard",
                            "browser_guard": guard_decision,
                            "message": format_browser_guard_preflight_message(guard_decision),
                        },
                        ensure_ascii=False,
                    )
                )
                if max_cycles is not None and cycle >= max_cycles:
                    break
                sleep_seconds = max(
                    int(guard_decision.get("recommended_sleep_seconds") or 0),
                    interval_seconds,
                )
                time.sleep(sleep_seconds)
                continue

            try:
                summary = run_home_feed_refresh(
                    cdp_url=cdp_url,
                    profile_key=profile_key,
                    business_domain=business_domain,
                    max_cards=max_cards,
                    max_messages=max_messages,
                    min_message_interval_seconds=min_message_interval_seconds,
                    freshness_days=freshness_days,
                    min_sample_points=min_sample_points,
                    message_text=message_text,
                    dry_run=dry_run,
                    require_actionable_band=require_actionable_band,
                    only_within_target_price=only_within_target_price,
                    min_profit_margin_pct=Decimal(str(min_profit_margin_pct)),
                )
                summary["watch_cycle"] = cycle
                summary["interval_seconds"] = interval_seconds
                cycle_auth_state = str((summary.get("browser_guard") or {}).get("auth_state") or "").strip() or None
                post_guard_sleep_seconds = max(
                    int((summary.get("browser_guard") or {}).get("recommended_sleep_seconds") or 0),
                    0,
                )
                typer.echo(json.dumps(summary, ensure_ascii=False))
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                post_guard_decision = getattr(exc, "browser_guard_decision", None)
                cycle_auth_state = str((post_guard_decision or {}).get("auth_state") or "").strip() or None
                if cycle_auth_state is None:
                    cycle_auth_state = infer_auth_state_from_error_message(str(exc))
                post_guard_sleep_seconds = max(
                    int((post_guard_decision or {}).get("recommended_sleep_seconds") or 0),
                    0,
                )
                typer.echo(
                    json.dumps(
                        {
                            "generated_at": datetime.now(UTC).isoformat(),
                            "watch_cycle": cycle,
                            "profile_key": profile_key,
                            "business_domain": business_domain,
                            "auth_state": cycle_auth_state,
                            "browser_guard": post_guard_decision,
                            "message": (
                                format_browser_guard_preflight_message(post_guard_decision)
                                if isinstance(post_guard_decision, dict)
                                else None
                            ),
                            "error": str(exc),
                        },
                        ensure_ascii=False,
                    ),
                    err=True,
                )

            if max_cycles is not None and cycle >= max_cycles:
                break

            elapsed_seconds = (datetime.now(UTC) - started_at).total_seconds()
            sleep_seconds = max(interval_seconds - elapsed_seconds, post_guard_sleep_seconds, 0)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
