"""Defensive JSON extraction from LLM text responses."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json_payload(content: str) -> Any:
    text = content.strip()

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, flags=re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        return json.loads(candidate)

    raise ValueError("No valid JSON payload found in model output.")

