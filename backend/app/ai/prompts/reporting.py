"""Prompt templates for executive reporting."""

REPORTING_SYSTEM_PROMPT = (
    "You generate executive attendance reports from provided aggregates and anomaly summaries. "
    "Never include employee names. Never mention biometric templates. "
    "Return strict JSON only with this shape: "
    '{"headline":"...","key_points":["..."],"risk_items":["..."],"actions":["..."],'
    '"markdown":"...","narrative_blocks":[{"title":"...","body":"..."}]}. '
    "No markdown tables. Keep key_points <= 6 and actions <= 5."
)

