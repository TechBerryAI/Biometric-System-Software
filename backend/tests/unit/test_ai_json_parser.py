"""Unit tests for AI JSON payload extraction."""

from __future__ import annotations

import pytest

from app.ai.utils.json_parser import extract_json_payload


@pytest.mark.testid("BE-UNIT-AI-JSON-001")
def test_extract_json_payload_from_fence() -> None:
    content = """Here you go:
```json
{"bullets": ["ok"], "confidence": "high"}
```
"""
    payload = extract_json_payload(content)
    assert payload == {"bullets": ["ok"], "confidence": "high"}


@pytest.mark.testid("BE-UNIT-AI-JSON-001")
def test_extract_json_payload_raw() -> None:
    payload = extract_json_payload('{"items": [1, 2]}')
    assert payload == {"items": [1, 2]}


@pytest.mark.testid("BE-UNIT-AI-JSON-001")
def test_extract_json_payload_embedded_object() -> None:
    payload = extract_json_payload("prefix {\"a\": 1} suffix")
    assert payload == {"a": 1}
