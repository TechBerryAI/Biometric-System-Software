"""Application configuration from environment."""

from __future__ import annotations

from functools import lru_cache

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

    zk_device_ip: str = Field(default="192.168.1.200", alias="ZK_DEVICE_IP")
    zk_device_port: int = Field(default=4370, alias="ZK_DEVICE_PORT")
    zk_device_password: int = Field(default=0, alias="ZK_DEVICE_PASSWORD")
    zk_device_timeout_seconds: int = Field(default=30, alias="ZK_DEVICE_TIMEOUT_SECONDS")
    zk_device_id: str = Field(default="main-entrance", alias="ZK_DEVICE_ID")
    zk_force_udp: bool = Field(default=False, alias="ZK_FORCE_UDP")
    zk_omit_ping: bool = Field(default=False, alias="ZK_OMIT_PING")

    timezone: str = Field(default="UTC", alias="TIMEZONE")
    device_poll_interval_seconds: int = Field(default=120, alias="DEVICE_POLL_INTERVAL_SECONDS")


@lru_cache
def get_settings() -> Settings:
    return Settings()

