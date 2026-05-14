"""Call xAI Grok for short management takeaways from aggregate attendance context."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import Settings


class GrokInsightError(Exception):
    pass


def _parse_bullets_json(content: str) -> list[str]:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if fence:
        text = fence.group(1).strip()
    data: Any = json.loads(text)
    if isinstance(data, dict) and "bullets" in data:
        raw = data["bullets"]
    elif isinstance(data, list):
        raw = data
    else:
        raise GrokInsightError("Model response was not a bullets list or object with 'bullets'.")
    if not isinstance(raw, list):
        raise GrokInsightError("Bullets payload is not a list.")
    out = [str(x).strip() for x in raw if str(x).strip()]
    return out[:5]


def generate_management_bullets(context: dict, settings: Settings) -> list[str]:
    if not settings.xai_api_key:
        raise GrokInsightError("XAI_API_KEY is not configured.")

    base = settings.xai_base_url.rstrip("/")
    url = f"{base}/chat/completions"

    system = (
        "You write concise management summaries for HR standups from attendance aggregates. "
        "Rules: (1) Output ONLY valid JSON with shape {\"bullets\": [\"...\", ...]} — no markdown, "
        "no code fences, no keys other than bullets. (2) At most 5 bullets; each one sentence; "
        "plain English. (3) Do not invent people, names, or departments not in the JSON. "
        "(4) Do not suggest charts or visualizations. (5) Focus on today vs recent trend when data supports it."
    )
    user = json.dumps(context, separators=(",", ":"), ensure_ascii=False)

    payload = {
        "model": settings.xai_model,
        "temperature": 0.35,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    headers = {
        "Authorization": f"Bearer {settings.xai_api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            r = client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            body = r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:500] if e.response is not None else str(e)
        raise GrokInsightError(f"xAI HTTP {e.response.status_code if e.response else '?'}: {detail}") from e
    except httpx.RequestError as e:
        raise GrokInsightError(f"xAI request failed: {e}") from e

    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise GrokInsightError("Unexpected xAI response shape.") from e

    if not isinstance(content, str) or not content.strip():
        raise GrokInsightError("Empty model content.")

    try:
        return _parse_bullets_json(content)
    except (json.JSONDecodeError, GrokInsightError):
        raise GrokInsightError("Could not parse JSON bullets from model output.") from None
