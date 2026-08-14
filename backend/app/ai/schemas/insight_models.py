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


class AttendancePredictionDay(BaseModel):
    day: date
    predicted_present: int
    predicted_absent: int
    predicted_late: int
    confidence: Literal["high", "medium", "low"] = "medium"


class AttendancePredictionResponse(BaseModel):
    period_start: date
    period_end: date
    generated_at: datetime
    horizon_days: int
    source: Literal["heuristic", "insufficient_data"]
    predictions: list[AttendancePredictionDay] = Field(default_factory=list)


class BuddyPunchAlert(BaseModel):
    alert_key: str
    detected_at: datetime
    device_id: str
    employee_codes: list[str] = Field(default_factory=list)
    window_seconds: float
    severity: AnomalySeverity
    description: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuddyPunchResponse(BaseModel):
    lookback_days: int
    generated_at: datetime
    alerts: list[BuddyPunchAlert] = Field(default_factory=list)


class DeviceFailureRisk(BaseModel):
    device_uuid: str
    device_name: str
    risk_score: float
    risk_level: Literal["low", "medium", "high", "critical"]
    factors: list[str] = Field(default_factory=list)
    predicted_failure_window_hours: int | None = None


class DeviceFailurePredictionResponse(BaseModel):
    generated_at: datetime
    devices: list[DeviceFailureRisk] = Field(default_factory=list)


class PayrollInsightItem(BaseModel):
    key: str
    title: str
    detail: str
    severity: AnomalySeverity
    metric_value: float | None = None


class PayrollInsightsLLMOutput(BaseModel):
    insights: list[PayrollInsightItem] = Field(default_factory=list, max_length=8)
    confidence: Literal["high", "medium", "low"] = "medium"


class PayrollInsightsResponse(BaseModel):
    period_start: date
    period_end: date
    available: bool
    source: Literal["grok", "rules", "unconfigured", "cache", "error"]
    insights: list[PayrollInsightItem] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] | None = None
    cached: bool = False
    usage: AIUsageInfo | None = None
    error_code: str | None = None

