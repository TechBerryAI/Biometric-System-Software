"""Unit tests for Grok provider configuration errors."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.ai.providers.grok_provider import AIProviderError, GrokProvider
from app.core.config import Settings, get_settings


class _TinyModel(BaseModel):
    value: str = "ok"


@pytest.mark.testid("BE-UNIT-AI-GROK-001")
def test_grok_provider_errors_without_key() -> None:
    base = get_settings()
    settings = Settings(**{**base.model_dump(), "xai_api_key": None})
    provider = GrokProvider(settings)

    with pytest.raises(AIProviderError, match="XAI_API_KEY"):
        provider.complete_json(
            system_prompt="sys",
            user_payload={"a": 1},
            response_model=_TinyModel,
            purpose="unit_test",
        )
