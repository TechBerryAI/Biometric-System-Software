"""Shared Redis connection options so no caller can hang on a dead or slow Redis."""

from __future__ import annotations

from typing import Any

# Fail fast instead of blocking a request or worker for the OS default (~2 minutes).
REDIS_CONNECT_TIMEOUT_SECONDS = 3.0
REDIS_SOCKET_TIMEOUT_SECONDS = 5.0


def redis_client_options(
    *,
    connect_timeout: float = REDIS_CONNECT_TIMEOUT_SECONDS,
    socket_timeout: float = REDIS_SOCKET_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """kwargs for ``Redis.from_url`` used across the app.

    Keepalive + periodic health checks recover pooled connections that a firewall
    silently dropped between the app VM and the Redis host.
    """
    return {
        "socket_connect_timeout": connect_timeout,
        "socket_timeout": socket_timeout,
        "socket_keepalive": True,
        "health_check_interval": 30,
        "retry_on_timeout": True,
    }
