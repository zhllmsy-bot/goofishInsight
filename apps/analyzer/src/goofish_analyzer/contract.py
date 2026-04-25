from __future__ import annotations

from pathlib import Path
from typing import Any


ANALYZER_JOBS = {"daily_metrics", "model_scores", "analysis_reports", "all"}

DEFAULT_LOCK_DIR = Path("reports/runtime/locks")
DEFAULT_LOCK_PATHS = {
    "daily_metrics": DEFAULT_LOCK_DIR / "analyzer_daily_metrics.lock",
    "model_scores": DEFAULT_LOCK_DIR / "analyzer_model_scores.lock",
    "analysis_reports": DEFAULT_LOCK_DIR / "analyzer_analysis_reports.lock",
}

SOURCE_MODES = {"legacy_items", "catalog_dual_read", "catalog_primary"}

PHASE3_CATALOG_SWITCH_GATES = {
    "spu_coverage_gte": 0.95,
    "price_parity_gte": 0.97,
    "contract_test": "pass",
    "rollback_ready": True,
}

JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"

HEALTH_STATUS_HEALTHY = "healthy"
HEALTH_STATUS_UNHEALTHY = "unhealthy"
HEALTH_STATUS_UNKNOWN = "unknown"

JOB_NAMES = {
    "daily_metrics": "analyzer_daily_metrics",
    "model_scores": "analyzer_model_scores",
    "analysis_reports": "analyzer_analysis_reports",
}

LOCK_JOB_NAMES = {
    "daily_metrics": "daily-metrics",
    "model_scores": "model-scores",
    "analysis_reports": "analysis-reports",
}

EXIT_CODE_ALREADY_RUNNING = {
    "daily_metrics": 18,
    "model_scores": 19,
    "analysis_reports": 20,
}


def build_source_contract(source_mode: str, *, read_path_override: str | None = None) -> dict[str, Any]:
    if read_path_override is not None:
        current_read_path = read_path_override
    elif source_mode == "catalog_dual_read":
        current_read_path = "items+item_spec_enrichments + category_catalog_views (dual-read)"
    elif source_mode == "catalog_primary":
        current_read_path = "category_catalog_views (primary)"
    else:
        current_read_path = "items+item_spec_enrichments"

    return {
        "source_mode": source_mode,
        "current_read_path": current_read_path,
        "phase3_target_read_path": "category_catalog_views (primary)",
        "cutover_gates": dict(PHASE3_CATALOG_SWITCH_GATES),
    }


def resolve_lock_path(job: str, explicit_lock_path: Path | None = None) -> Path:
    return explicit_lock_path or DEFAULT_LOCK_PATHS[job]
