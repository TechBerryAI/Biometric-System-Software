"""xAI Grok provider with retry, timeout, and strict JSON parsing."""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.ai.utils.metrics import incr
from app.ai.utils.json_parser import extract_json_payload
from app.ai.utils.telemetry import log_ai_event
from app.core.config import Settings

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class AIProviderError(Exception):
    """Raised when the external AI provider cannot return a valid response."""


@dataclass
class AIUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int = 0
    model: str = ""
    retries: int = 0
    from_cache: bool = False


class _CircuitBreaker:
    def __init__(self, threshold: int, reset_seconds: int) -> None:
        self._threshold = threshold
        self._reset_seconds = reset_seconds
        self._failures = 0
        self._opened_at: float | None = None
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        with self._lock:
            if self._opened_at is None:
                return True
            elapsed = time.time() - self._opened_at
            if elapsed >= self._reset_seconds:
                self._opened_at = None
                self._failures = 0
                return True
            return False

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self._threshold:
                self._opened_at = time.time()

    def opened_until(self) -> datetime | None:
        with self._lock:
            if self._opened_at is None:
                return None
            return datetime.fromtimestamp(self._opened_at + self._reset_seconds, tz=timezone.utc)


class GrokProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._disabled_reason: str | None = None
        self._breaker = _CircuitBreaker(
            threshold=settings.ai_circuit_breaker_failures,
            reset_seconds=settings.ai_circuit_breaker_reset_seconds,
        )

    def complete_json(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        response_model: type[T],
        purpose: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[T, AIUsage]:
        if not self._settings.xai_api_key:
            raise AIProviderError("XAI_API_KEY is not configured.")
        if self._disabled_reason:
            raise AIProviderError(self._disabled_reason)

        if not self._breaker.can_execute():
            reset_at = self._breaker.opened_until()
            suffix = f" until {reset_at.isoformat()}" if reset_at else ""
            raise AIProviderError(f"AI provider circuit breaker is open{suffix}.")

        url = f"{self._settings.xai_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._settings.xai_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._settings.xai_model,
            "temperature": self._settings.ai_temperature if temperature is None else temperature,
            "max_tokens": self._settings.ai_max_tokens if max_tokens is None else max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, separators=(",", ":"), ensure_ascii=False)},
            ],
        }

        attempt = 0
        max_attempts = max(1, self._settings.ai_retry_attempts + 1)
        start = time.perf_counter()
        while attempt < max_attempts:
            attempt += 1
            try:
                with httpx.Client(
                    timeout=httpx.Timeout(float(self._settings.ai_timeout_seconds), connect=10.0)
                ) as client:
                    resp = client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    body = resp.json()
                parsed, usage = self._parse_and_validate_response(body, response_model, purpose=purpose, retries=attempt - 1)
                usage.latency_ms = int((time.perf_counter() - start) * 1000)
                usage.model = self._settings.xai_model
                self._breaker.record_success()
                incr("ai_provider_success")
                log_ai_event(
                    log,
                    "provider_success",
                    purpose=purpose,
                    model=usage.model,
                    latency_ms=usage.latency_ms,
                    retries=usage.retries,
                    tokens_total=usage.total_tokens,
                )
                return parsed, usage
            except httpx.HTTPStatusError as exc:
                self._breaker.record_failure()
                incr("ai_provider_failure")
                status = exc.response.status_code if exc.response is not None else None
                # Permanent client-side configuration errors should fail fast
                # instead of retrying the same bad request several times.
                if status in {400, 401, 403, 404}:
                    detail = (
                        f"xAI HTTP {status}. Check XAI_BASE_URL / XAI_MODEL / XAI_API_KEY configuration."
                    )
                    self._disabled_reason = detail
                    raise AIProviderError(detail) from exc
                if attempt >= max_attempts:
                    log.warning("ai.provider.failed purpose=%s attempts=%s error=%s", purpose, attempt, exc)
                    raise AIProviderError(f"AI completion failed for '{purpose}': {exc}") from exc
                sleep_s = min(0.25 * (2 ** (attempt - 1)), 2.0)
                time.sleep(sleep_s)
            except (httpx.HTTPError, ValueError, ValidationError, AIProviderError) as exc:
                self._breaker.record_failure()
                incr("ai_provider_failure")
                if attempt >= max_attempts:
                    log.warning("ai.provider.failed purpose=%s attempts=%s error=%s", purpose, attempt, exc)
                    raise AIProviderError(f"AI completion failed for '{purpose}': {exc}") from exc
                sleep_s = min(0.25 * (2 ** (attempt - 1)), 2.0)
                time.sleep(sleep_s)

        raise AIProviderError(f"AI completion failed for '{purpose}'")

    def _parse_and_validate_response(
        self,
        body: dict[str, Any],
        response_model: type[T],
        *,
        purpose: str,
        retries: int,
    ) -> tuple[T, AIUsage]:
        try:
            content = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise AIProviderError("Unexpected xAI response shape.") from exc
        if not isinstance(content, str) or not content.strip():
            raise AIProviderError("xAI returned empty content.")

        payload = extract_json_payload(content)
        if not isinstance(payload, dict):
            raise AIProviderError("Expected JSON object in model response.")

        try:
            model = response_model.model_validate(payload)
        except ValidationError as exc:
            log.warning("ai.provider.validation_failed purpose=%s payload=%s", purpose, payload)
            raise

        usage_node = body.get("usage") if isinstance(body, dict) else None
        usage = AIUsage(
            prompt_tokens=usage_node.get("prompt_tokens") if isinstance(usage_node, dict) else None,
            completion_tokens=usage_node.get("completion_tokens") if isinstance(usage_node, dict) else None,
            total_tokens=usage_node.get("total_tokens") if isinstance(usage_node, dict) else None,
            retries=retries,
        )
        return model, usage

