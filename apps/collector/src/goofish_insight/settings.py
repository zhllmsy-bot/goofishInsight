from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="text", alias="LOG_FORMAT")
    database_url: str = Field(
        default="postgresql+psycopg://goofish:change-this-password@localhost:5432/goofish_insight",
        alias="DATABASE_URL",
    )
    default_task_key: str = Field(default="garmin-fenix", alias="DEFAULT_TASK_KEY")
    base_dir: Path = Field(default=REPO_ROOT)
    browser_profile_dir: Path = Field(
        default=REPO_ROOT / "data" / "browser-profile",
        alias="BROWSER_PROFILE_DIR",
    )
    ai_provider: str = Field(
        default="openai_compatible",
        validation_alias=AliasChoices("AI_PROVIDER", "ARK_AI_PROVIDER"),
    )
    ai_base_url: str = Field(
        default="",
        validation_alias=AliasChoices("AI_BASE_URL", "ARK_AI_BASE_URL"),
    )
    ai_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("AI_API_KEY", "ARK_AI_API_KEY", "BAILIAN_CODING_PLAN_API_KEY"),
    )
    ai_model: str = Field(
        default="qwen3.5-plus",
        validation_alias=AliasChoices("AI_MODEL", "ARK_AI_MODEL"),
    )
    ai_timeout_sec: int = Field(
        default=30,
        validation_alias=AliasChoices("AI_TIMEOUT_SEC", "ARK_AI_TIMEOUT_SEC"),
    )
    ai_enable_thinking: bool = Field(
        default=False,
        validation_alias=AliasChoices("AI_ENABLE_THINKING", "ARK_AI_ENABLE_THINKING"),
    )
    ai_max_tokens: int = Field(
        default=600,
        validation_alias=AliasChoices("AI_MAX_TOKENS", "ARK_AI_MAX_TOKENS"),
    )
    review_v3_ai_max_tokens: int = Field(
        default=220,
        alias="REVIEW_V3_AI_MAX_TOKENS",
    )
    review_v3_batch_ai_max_tokens: int = Field(
        default=900,
        alias="REVIEW_V3_BATCH_AI_MAX_TOKENS",
    )
    ai_prompt_trace_enabled: bool = Field(default=False, alias="AI_PROMPT_TRACE_ENABLED")
    ai_prompt_trace_dir: Path = Field(
        default=REPO_ROOT / "reports" / "llm-traces",
        alias="AI_PROMPT_TRACE_DIR",
    )
    review_v3_executor: str = Field(default="direct", alias="REVIEW_V3_EXECUTOR")
    cozeloop_base_url: str = Field(default="http://127.0.0.1:8888", alias="COZELOOP_BASE_URL")
    cozeloop_workspace_id: str = Field(default="", alias="COZELOOP_WORKSPACE_ID")
    cozeloop_pat: str = Field(default="", alias="COZELOOP_PAT")
    cozeloop_session_key: str = Field(default="", alias="COZELOOP_SESSION_KEY")
    cozeloop_model_id: int = Field(default=1, alias="COZELOOP_MODEL_ID")
    cozeloop_first_pass_model_id: int = Field(default=1, alias="COZELOOP_FIRST_PASS_MODEL_ID")
    cozeloop_second_pass_model_id: int = Field(default=1, alias="COZELOOP_SECOND_PASS_MODEL_ID")
    cozeloop_first_pass_model_name: str = Field(default="", alias="COZELOOP_FIRST_PASS_MODEL_NAME")
    cozeloop_second_pass_model_name: str = Field(default="", alias="COZELOOP_SECOND_PASS_MODEL_NAME")
    cozeloop_prompt_key_prefix: str = Field(default="goofish-review-v3", alias="COZELOOP_PROMPT_KEY_PREFIX")
    mobile_overlay_vlm_enabled: bool = Field(default=True, alias="MOBILE_OVERLAY_VLM_ENABLED")
    mobile_overlay_vlm_base_url: str = Field(default="http://127.0.0.1:8020", alias="MOBILE_OVERLAY_VLM_BASE_URL")
    mobile_overlay_vlm_model: str = Field(
        default="Qwen2.5-VL-72B-Instruct-4bit-MLX",
        alias="MOBILE_OVERLAY_VLM_MODEL",
    )
    mobile_overlay_vlm_timeout_sec: int = Field(default=300, alias="MOBILE_OVERLAY_VLM_TIMEOUT_SEC")
    mobile_overlay_vlm_max_output_tokens: int = Field(default=320, alias="MOBILE_OVERLAY_VLM_MAX_OUTPUT_TOKENS")
    mobile_overlay_vlm_enable_thinking: bool = Field(default=True, alias="MOBILE_OVERLAY_VLM_ENABLE_THINKING")
    prune_raw_after_ingest: bool = Field(default=True, alias="PRUNE_RAW_AFTER_INGEST")
    low_price_filter_ratio: float = Field(default=0.35, alias="LOW_PRICE_FILTER_RATIO")
    low_price_filter_min_samples: int = Field(default=8, alias="LOW_PRICE_FILTER_MIN_SAMPLES")
    price_template_contract_enabled: bool = Field(default=True, alias="PRICE_TEMPLATE_CONTRACT_ENABLED")
    price_template_dashboard_enabled: bool = Field(default=True, alias="PRICE_TEMPLATE_DASHBOARD_ENABLED")
    price_template_opportunity_enabled: bool = Field(default=True, alias="PRICE_TEMPLATE_OPPORTUNITY_ENABLED")
    price_template_trend_enabled: bool = Field(default=True, alias="PRICE_TEMPLATE_TREND_ENABLED")
    price_template_alert_strict_mode: bool = Field(default=True, alias="PRICE_TEMPLATE_ALERT_STRICT_MODE")
    dashboard_cors_origins: str = Field(
        default=(
            "http://127.0.0.1:5173,"
            "http://localhost:5173,"
            "http://127.0.0.1:5174,"
            "http://localhost:5174"
        ),
        alias="DASHBOARD_CORS_ORIGINS",
    )
    alert_webhook_url: str = Field(default="", alias="ALERT_WEBHOOK_URL")
    alert_webhook_auth_token: str = Field(default="", alias="ALERT_WEBHOOK_AUTH_TOKEN")
    alert_webhook_secret: str = Field(default="", alias="ALERT_WEBHOOK_SECRET")
    alert_webhook_timeout_sec: int = Field(default=5, alias="ALERT_WEBHOOK_TIMEOUT_SEC")
    db_pool_size: int = Field(default=20, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")
    db_pool_timeout_sec: int = Field(default=30, alias="DB_POOL_TIMEOUT_SEC")
    db_pool_recycle_sec: int = Field(default=1800, alias="DB_POOL_RECYCLE_SEC")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
