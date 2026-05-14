"""Redis key namespacing helpers for shared Redis deployments."""

from __future__ import annotations


def with_namespace(namespace: str, key: str) -> str:
    ns = namespace.strip().strip(":")
    if not ns:
        return key
    return f"{ns}:{key.lstrip(':')}"
