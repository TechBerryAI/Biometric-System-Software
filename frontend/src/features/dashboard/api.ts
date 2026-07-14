import axios from "axios";
import { api, INSIGHTS_HTTP_TIMEOUT_MS } from "@/shared/api/client";

export type ManagementInsightsResponse = {
  available: boolean;
  source: "grok" | "unconfigured" | "cache" | "rules" | "error";
  bullets: string[];
  confidence?: "high" | "medium" | "low" | null;
  risk_flags?: string[];
  cached?: boolean;
  error_code?: string | null;
};

export async function fetchManagementInsights(days = 14): Promise<ManagementInsightsResponse> {
  try {
    const { data } = await api.get<ManagementInsightsResponse>("/insights/management", {
      params: { days },
      timeout: INSIGHTS_HTTP_TIMEOUT_MS,
    });
    if (!data || !Array.isArray(data.bullets) || typeof data.available !== "boolean") {
      return {
        available: false,
        source: "error",
        bullets: [],
        error_code: "malformed_response",
      };
    }
    return data;
  } catch (err) {
    if (axios.isAxiosError(err)) {
      const code =
        err.code === "ECONNABORTED"
          ? "timeout"
          : err.response?.status === 403
          ? "forbidden"
          : err.response?.status === 429
          ? "rate_limited"
          : "request_failed";
      return {
        available: false,
        source: "error",
        bullets: [],
        error_code: code,
      };
    }
    return {
      available: false,
      source: "error",
      bullets: [],
      error_code: "unknown_error",
    };
  }
}

export type AttendanceAnomaly = {
  id: number;
  anomaly_key: string;
  anomaly_date: string;
  category: string;
  severity: "low" | "medium" | "high" | "critical";
  score: number;
  description: string;
  explanation?: string | null;
  recommendation?: string | null;
};

export type AnomalyDetectionResponse = {
  period_start: string;
  period_end: string;
  detector: "isolation_forest" | "heuristic";
  anomalies: AttendanceAnomaly[];
  available?: boolean;
  error_code?: string | null;
};

export async function fetchAttendanceAnomalies(lookback_days = 30): Promise<AnomalyDetectionResponse> {
  try {
    const { data } = await api.get<AnomalyDetectionResponse>("/insights/anomalies", {
      params: { lookback_days },
      timeout: INSIGHTS_HTTP_TIMEOUT_MS,
    });
    if (!data || !Array.isArray(data.anomalies)) {
      return {
        available: false,
        period_start: "",
        period_end: "",
        detector: "heuristic",
        anomalies: [],
        error_code: "malformed_response",
      };
    }
    return { ...data, available: true, error_code: null };
  } catch (err) {
    if (axios.isAxiosError(err)) {
      const code =
        err.code === "ECONNABORTED"
          ? "timeout"
          : err.response?.status === 403
          ? "forbidden"
          : err.response?.status === 429
          ? "rate_limited"
          : "request_failed";
      return {
        available: false,
        period_start: "",
        period_end: "",
        detector: "heuristic",
        anomalies: [],
        error_code: code,
      };
    }
    return {
      available: false,
      period_start: "",
      period_end: "",
      detector: "heuristic",
      anomalies: [],
      error_code: "unknown_error",
    };
  }
}
