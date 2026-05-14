"""Application configuration from environment."""

from __future__ import annotations

from functools import lru_cache
from datetime import time

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="Biometric Attendance API", alias="APP_NAME")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    database_url: PostgresDsn = Field(
        default="postgresql+psycopg://biometric:biometric@localhost:5432/biometric",
        alias="DATABASE_URL",
    )

    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_namespace: str = Field(default="biometric", alias="REDIS_NAMESPACE")

    zk_device_ip: str = Field(default="192.168.1.200", alias="ZK_DEVICE_IP")
    zk_device_port: int = Field(default=4370, alias="ZK_DEVICE_PORT")
    zk_device_password: int = Field(default=0, alias="ZK_DEVICE_PASSWORD")
    zk_device_timeout_seconds: int = Field(default=30, alias="ZK_DEVICE_TIMEOUT_SECONDS")
    zk_device_id: str = Field(default="main-entrance", alias="ZK_DEVICE_ID")
    zk_force_udp: bool = Field(default=False, alias="ZK_FORCE_UDP")
    zk_omit_ping: bool = Field(default=False, alias="ZK_OMIT_PING")

    timezone: str = Field(default="UTC", alias="TIMEZONE")
    device_poll_interval_seconds: int = Field(default=120, alias="DEVICE_POLL_INTERVAL_SECONDS")
    default_shift_start: time = Field(default=time(9, 30), alias="DEFAULT_SHIFT_START")
    # After each device pull, rebuild sessions for this many trailing local calendar days (1–62).
    session_rebuild_lookback_days: int = Field(
        default=14, ge=1, le=62, alias="SESSION_REBUILD_LOOKBACK_DAYS"
    )

    # xAI Grok — optional; used for /insights/management (aggregate context only).
    xai_api_key: str | None = Field(default=None, alias="XAI_API_KEY")
    xai_model: str = Field(default="grok-code-fast-1", alias="XAI_MODEL")
    xai_base_url: str = Field(default="https://api.x.ai/v1", alias="XAI_BASE_URL")
    ai_timeout_seconds: int = Field(default=25, ge=5, le=120, alias="AI_TIMEOUT_SECONDS")
    ai_max_tokens: int = Field(default=800, ge=128, le=4096, alias="AI_MAX_TOKENS")
    ai_temperature: float = Field(default=0.3, ge=0.0, le=1.0, alias="AI_TEMPERATURE")
    ai_cache_ttl: int = Field(default=300, ge=30, le=86400, alias="AI_CACHE_TTL")
    ai_retry_attempts: int = Field(default=2, ge=0, le=5, alias="AI_RETRY_ATTEMPTS")
    ai_circuit_breaker_failures: int = Field(default=4, ge=1, le=20, alias="AI_CIRCUIT_BREAKER_FAILURES")
    ai_circuit_breaker_reset_seconds: int = Field(
        default=90,
        ge=10,
        le=3600,
        alias="AI_CIRCUIT_BREAKER_RESET_SECONDS",
    )
    ai_rate_limit_per_minute: int = Field(default=30, ge=1, le=500, alias="AI_RATE_LIMIT_PER_MINUTE")
    ai_daily_quota: int = Field(default=500, ge=10, le=100000, alias="AI_DAILY_QUOTA")

    jwt_secret_key: str = Field(default="change-me", alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=15, ge=1, le=1440, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, ge=1, le=90, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    auth_enabled: bool = Field(default=True, alias="AUTH_ENABLED")
    auth_bootstrap_admin_email: str | None = Field(default=None, alias="AUTH_BOOTSTRAP_ADMIN_EMAIL")
    auth_bootstrap_admin_password: str | None = Field(default=None, alias="AUTH_BOOTSTRAP_ADMIN_PASSWORD")
    login_attempt_window_seconds: int = Field(default=900, ge=60, le=86400, alias="LOGIN_ATTEMPT_WINDOW_SECONDS")
    login_attempt_max: int = Field(default=5, ge=3, le=50, alias="LOGIN_ATTEMPT_MAX")

    command_queue_batch_size: int = Field(default=25, ge=1, le=250, alias="COMMAND_QUEUE_BATCH_SIZE")
    command_max_retries: int = Field(default=5, ge=1, le=20, alias="COMMAND_MAX_RETRIES")
    command_retry_base_seconds: int = Field(default=30, ge=5, le=600, alias="COMMAND_RETRY_BASE_SECONDS")
    command_retry_max_seconds: int = Field(default=900, ge=30, le=86400, alias="COMMAND_RETRY_MAX_SECONDS")
    command_stale_minutes: int = Field(default=15, ge=1, le=240, alias="COMMAND_STALE_MINUTES")
    command_heartbeat_seconds: int = Field(default=10, ge=5, le=120, alias="COMMAND_HEARTBEAT_SECONDS")
    command_lock_blocking_seconds: int = Field(default=1, ge=0, le=30, alias="COMMAND_LOCK_BLOCKING_SECONDS")
    command_cooldown_ms: int = Field(default=250, ge=0, le=10000, alias="COMMAND_COOLDOWN_MS")
    command_max_recover_verification_lookback: int = Field(
        default=3,
        ge=1,
        le=20,
        alias="COMMAND_MAX_RECOVER_VERIFICATION_LOOKBACK",
    )
    reconciliation_interval_seconds: int = Field(default=300, ge=30, le=3600, alias="RECONCILIATION_INTERVAL_SECONDS")
    snapshot_interval_seconds: int = Field(default=900, ge=60, le=21600, alias="SNAPSHOT_INTERVAL_SECONDS")
    snapshot_retention_days: int = Field(default=30, ge=7, le=3650, alias="SNAPSHOT_RETENTION_DAYS")
    command_history_retention_days: int = Field(default=90, ge=7, le=3650, alias="COMMAND_HISTORY_RETENTION_DAYS")
    reconciliation_retention_days: int = Field(default=180, ge=30, le=3650, alias="RECONCILIATION_RETENTION_DAYS")
    metrics_retention_days: int = Field(default=90, ge=7, le=3650, alias="METRICS_RETENTION_DAYS")
    allow_device_uid_rewrite: bool = Field(default=False, alias="ALLOW_DEVICE_UID_REWRITE")
    allow_device_privilege_update: bool = Field(default=False, alias="ALLOW_DEVICE_PRIVILEGE_UPDATE")
    allow_device_card_rewrite: bool = Field(default=False, alias="ALLOW_DEVICE_CARD_REWRITE")
    allow_device_admin_override: bool = Field(default=False, alias="ALLOW_DEVICE_ADMIN_OVERRIDE")
    device_read_only: bool = Field(default=False, alias="DEVICE_READ_ONLY")


@lru_cache
def get_settings() -> Settings:
    return Settings()

