from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from uuid import UUID
from typing import Any

from goofish_analyzer.adapters import (
    finish_collector_job_run,
    start_collector_job_run,
    QualityMetricsService,
)

LOGGER_NAME = "goofish_analyzer"
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=level, format=_LOG_FORMAT)
    return logger


logger = configure_logging()


def _job_event(event: str, **context: Any) -> str:
    payload = {"event": event, **context}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)


def run_analyzer_job(
    *,
    job_name: str,
    phase: str,
    metric_date: date,
    task_key: str,
    start_metadata: dict[str, Any],
    execute: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    job_run_id: UUID | None = None
    try:
        job_run_id = start_collector_job_run(
            job_name=job_name,
            phase=phase,
            status="running",
            metadata=start_metadata,
        )
    except Exception as exc:
        start_error_context = dict(start_metadata)
        start_error_context.update(
            {
                "job_name": job_name,
                "phase": phase,
                "task_key": task_key,
                "metric_date": metric_date.isoformat(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
        logger.exception(
            _job_event("analyzer_job_start_failed", **start_error_context)
        )
        raise

    summary: dict[str, Any] = {}
    final_status = "completed"
    final_exit_code = 0
    job_error: Exception | None = None

    try:
        summary = execute()
        event_context = dict(start_metadata)
        event_context.update(
            {
                "job_name": job_name,
                "phase": phase,
                "task_key": task_key,
                "job_run_id": str(job_run_id),
                "metric_date": metric_date.isoformat(),
            }
        )
        logger.info(
            _job_event("analyzer_job_completed", **event_context)
        )
        return summary
    except Exception as exc:
        job_error = exc
        final_status = "failed"
        final_exit_code = 1
        summary = {"error": str(exc)}
        event_context = dict(start_metadata)
        event_context.update(
            {
                "job_name": job_name,
                "phase": phase,
                "task_key": task_key,
                "job_run_id": str(job_run_id),
                "metric_date": metric_date.isoformat(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
        logger.exception(
            _job_event("analyzer_job_failed", **event_context)
        )
        raise
    finally:
        if job_run_id is None:
            return
        finished_at = datetime.now(UTC)
        try:
            finish_collector_job_run(
                job_run_id=job_run_id,
                status=final_status,
                phase=phase,
                exit_code=final_exit_code,
                metadata=summary,
            )
            QualityMetricsService.record_metric(
                metric_date=metric_date,
                metric_hour=finished_at.hour,
                metric_key="analyzer_job_success_rate",
                metric_value=1.0 if final_status == "completed" else 0.0,
                task_key=task_key,
                metadata={
                    "job_run_id": str(job_run_id),
                    "job_name": job_name,
                    "phase": phase,
                    "status": final_status,
                    "exit_code": final_exit_code,
                    "summary": summary,
                    "recorded_at": finished_at.isoformat(),
                },
            )
        except Exception:
            event_context = dict(start_metadata)
            event_context.update(
                {
                    "job_name": job_name,
                    "phase": phase,
                    "task_key": task_key,
                    "job_run_id": str(job_run_id),
                    "metric_date": metric_date.isoformat(),
                    "status": final_status,
                    "exit_code": final_exit_code,
                    "error_type": type(job_error).__name__ if job_error is not None else None,
                    "error_message": str(job_error) if job_error is not None else None,
                }
            )
            logger.exception(
                _job_event("analyzer_job_finalization_failed", **event_context)
            )
            if job_error is None:
                raise
