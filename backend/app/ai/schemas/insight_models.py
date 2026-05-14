"""Pydantic contracts for AI services and endpoints."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class AIUsageInfo(BaseModel):
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    latency_ms: int | None = None
    retries: int = 0
    cached: bool = False


class ManagementInsightsLLMOutput(BaseModel):
    bullets: list[str] = Field(default_factory=list, max_length=5)
    confidence: Literal["high", "medium", "low"] = "medium"
    risk_flags: list[str] = Field(default_factory=list, max_length=5)


class ManagementInsightsResponse(BaseModel):
    available: bool
    source: Literal["grok", "rules", "unconfigured", "cache", "error"]
    bullets: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] | None = None
    risk_flags: list[str] = Field(default_factory=list)
    cached: bool = False
    usage: AIUsageInfo | None = None
    error_code: str | None = None


class AnomalySeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class AnomalyExplanationItem(BaseModel):
    anomaly_key: str
    explanation: str
    recommendation: str


class AnomalyExplanationsLLMOutput(BaseModel):
    items: list[AnomalyExplanationItem] = Field(default_factory=list)


class AttendanceAnomalyRead(BaseModel):
    id: int
    anomaly_key: str
    anomaly_date: date
    category: str
    severity: AnomalySeverity
    score: float
    department: str | None = None
    metric_value: float | None = None
    baseline_value: float | None = None
    description: str
    explanation: str | None = None
    recommendation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AnomalyDetectionResponse(BaseModel):
    period_start: date
    period_end: date
    generated_at: datetime
    detector: Literal["isolation_forest", "heuristic"]
    anomalies: list[AttendanceAnomalyRead]
    usage: AIUsageInfo | None = None
    cached: bool = False


class ForecastPoint(BaseModel):
    date: date
    predicted_attendance_rate_percent: float
    predicted_absenteeism_percent: float


class ForecastResponse(BaseModel):
    generated_at: datetime
    lookback_days: int
    horizon_days: int
    points: list[ForecastPoint]


class NarrativeBlock(BaseModel):
    title: str
    body: str


class ExecutiveReportLLMOutput(BaseModel):
    headline: str
    key_points: list[str] = Field(default_factory=list)
    risk_items: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    markdown: str
    narrative_blocks: list[NarrativeBlock] = Field(default_factory=list)


class ExecutiveReportResponse(BaseModel):
    report_type: Literal["weekly", "monthly", "department"]
    generated_at: datetime
    period_start: date
    period_end: date
    scope: str
    cached: bool = False
    usage: AIUsageInfo | None = None
    report: ExecutiveReportLLMOutput


class CopilotIntent(str, Enum):
    highest_absenteeism_department = "highest_absenteeism_department"
    attendance_trend = "attendance_trend"
    top_overtime_employees = "top_overtime_employees"
    unsupported = "unsupported"


class CopilotQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=300)


class CopilotExplanationLLMOutput(BaseModel):
    summary: str
    insights: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class CopilotQueryResponse(BaseModel):
    intent: CopilotIntent
    intent_confidence: Literal["high", "medium", "low"]
    structured_result: dict[str, Any]
    explanation: CopilotExplanationLLMOutput | None = None
    cached: bool = False
    usage: AIUsageInfo | None = None
    blocked: bool = False
    block_reason: str | None = None

