"""Application configuration from environment."""

from __future__ import annotations

from functools import lru_cache
from datetime import time
from urllib.parse import quote_plus

from pydantic import Field, model_validator
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
    cors_allow_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,http://frontend:5173",
        alias="CORS_ALLOW_ORIGINS",
    )
    cors_allow_origin_regex: str = Field(default=r"^http://(localhost|127\.0\.0\.1):\d+$", alias="CORS_ALLOW_ORIGIN_REGEX")
    cors_allow_private_network_origins: bool = Field(default=True, alias="CORS_ALLOW_PRIVATE_NETWORK_ORIGINS")

    # Primary setting. If omitted, it is built from DB_* fields below.
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    db_host: str | None = Field(default=None, alias="DB_HOST")
    db_port: int | None = Field(default=None, alias="DB_PORT")
    db_name: str | None = Field(default=None, alias="DB_NAME")
    db_user: str | None = Field(default=None, alias="DB_USER")
    db_password: str | None = Field(default=None, alias="DB_PASSWORD")
    db_sslmode: str | None = Field(default=None, alias="DB_SSLMODE")

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
    device_auto_sync_enabled: bool = Field(
        default=True,
        alias="DEVICE_AUTO_SYNC_ENABLED",
        description="When false, Celery stops polling the biometric device (manual sync still works).",
    )
    device_snapshot_enabled: bool = Field(
        default=True,
        alias="DEVICE_SNAPSHOT_ENABLED",
        description="When false, Celery skips periodic fetch_users snapshots.",
    )
    device_connectivity_probe_seconds: int = Field(
        default=60,
        ge=15,
        le=600,
        alias="DEVICE_CONNECTIVITY_PROBE_SECONDS",
        description="How often Celery TCP-probes the device and updates health_status in the DB.",
    )
    device_sync_overlap_minutes: int = Field(default=15, ge=1, le=720, alias="DEVICE_SYNC_OVERLAP_MINUTES")
    duplicate_punch_window_seconds: int = Field(default=30, ge=0, le=300, alias="DUPLICATE_PUNCH_WINDOW_SECONDS")
    attendance_api_default_limit: int = Field(default=1000, ge=100, le=10000, alias="ATTENDANCE_API_DEFAULT_LIMIT")
    attendance_api_max_limit: int = Field(default=5000, ge=500, le=50000, alias="ATTENDANCE_API_MAX_LIMIT")
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
    command_lock_blocking_seconds: int = Field(default=1, ge=0, le=120, alias="COMMAND_LOCK_BLOCKING_SECONDS")
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
    strict_device_authority: bool = Field(
        default=False,
        alias="STRICT_DEVICE_AUTHORITY",
        description="When true, DB attendance is updated only after verified device write (Tier A).",
    )
    correction_allow_db_only_fallback: bool = Field(
        default=True,
        alias="CORRECTION_ALLOW_DB_ONLY_FALLBACK",
        description="When strict mode is on but firmware cannot write attlog, allow applied_db_only if true.",
    )
    correction_tier_b_write_enabled: bool = Field(
        default=False,
        alias="CORRECTION_TIER_B_WRITE_ENABLED",
        description="When true, allow guarded full attlog rewrite on Tier B firmware with readback verification.",
    )

    @model_validator(mode="after")
    def _compose_database_url(self) -> "Settings":
        # Keep explicit DATABASE_URL untouched.
        if self.database_url:
            return self

        # Build from split DB_* vars (useful for VM/tunneled TCP deployments).
        if self.db_host and self.db_port and self.db_name and self.db_user is not None:
            user = quote_plus(self.db_user)
            auth = user
            if self.db_password is not None:
                auth = f"{user}:{quote_plus(self.db_password)}"

            url = f"postgresql+psycopg://{auth}@{self.db_host}:{self.db_port}/{self.db_name}"
            if self.db_sslmode:
                url = f"{url}?sslmode={quote_plus(self.db_sslmode)}"
            self.database_url = url
            return self

        # Backward-compatible local default.
        self.database_url = "postgresql+psycopg://biometric:biometric@localhost:5432/biometric"
        return self

    @property
    def cors_allowed_origins(self) -> list[str]:
        """Parse comma-separated CORS origins into a normalized list."""
        values = [item.strip().rstrip("/") for item in self.cors_allow_origins.split(",")]
        # Keep order stable while removing empty/duplicate values.
        deduped: list[str] = []
        seen: set[str] = set()
        for origin in values:
            if not origin or origin in seen:
                continue
            seen.add(origin)
            deduped.append(origin)
        return deduped


@lru_cache
def get_settings() -> Settings:
    return Settings()

