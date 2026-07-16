"""Unit tests for feature flags."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.feature_flags import FeatureFlags, reset_feature_flags


@pytest.mark.testid("BE-UNIT-FF-001")
def test_feature_flags_defaults() -> None:
    reset_feature_flags()
    settings = MagicMock(feature_flags="")
    flags = FeatureFlags(settings)
    assert flags.is_enabled("ai_insights") is True
    assert flags.is_enabled("mfa_enforcement") is False
    reset_feature_flags()


@pytest.mark.testid("BE-UNIT-FF-002")
def test_feature_flags_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_feature_flags()
    settings = MagicMock(feature_flags="ai_insights=false,mfa_enforcement=true")
    flags = FeatureFlags(settings)
    assert flags.is_enabled("ai_insights") is False
    assert flags.is_enabled("mfa_enforcement") is True
    reset_feature_flags()


@pytest.mark.testid("BE-UNIT-FF-003")
def test_feature_flags_unknown_default() -> None:
    reset_feature_flags()
    flags = FeatureFlags(MagicMock(feature_flags=""))
    assert flags.is_enabled("no_such_flag", default=True) is True
    assert flags.is_enabled("no_such_flag") is False
    reset_feature_flags()
