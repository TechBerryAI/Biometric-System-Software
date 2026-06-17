import axios from "axios";
import { API_BASE_URL } from "@/config/api";
import type {
  AttendanceLog,
  AttendanceSession,
  DailySummaryRow,
  Employee,
  EmployeeCreatePayload,
  EmployeeDailyAttendance,
  EmployeeDetail,
} from "@/types";

const baseURL = API_BASE_URL;

export const api = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

const rawApi = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

let accessToken: string | null = null;
let refreshHandler: (() => Promise<string | null>) | null = null;

export function configureApiAuth(token: string | null) {
  accessToken = token;
}

export function clearApiAuth() {
  accessToken = null;
}

export function registerTokenRefreshHandler(handler: () => Promise<string | null>) {
  refreshHandler = handler;
}

api.interceptors.request.use((config) => {
  if (accessToken) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (!axios.isAxiosError(error) || error.response?.status !== 401) throw error;
    const original = error.config as typeof error.config & { _retry?: boolean };
    if (!original || original._retry || !refreshHandler) throw error;
    original._retry = true;
    const token = await refreshHandler();
    if (!token) throw error;
    original.headers = original.headers ?? {};
    original.headers.Authorization = `Bearer ${token}`;
    return api.request(original);
  }
);

export type CurrentUserResponse = {
  user_uuid: string;
  email: string;
  full_name?: string | null;
  role: "SUPER_ADMIN" | "HR_ADMIN" | "IT_ADMIN" | "CEO";
  active: boolean;
};

export type AppUserRole = "HR_ADMIN" | "IT_ADMIN";

export type AccountCreatePayload = {
  email: string;
  full_name?: string;
  password: string;
  role: AppUserRole;
  active?: boolean;
};

export type AuthTokens = {
  access_token: string;
  token_type: "bearer";
  refresh_token: string;
  refresh_expires_at: string;
  role: string;
};

export async function loginWithPassword(email: string, password: string): Promise<AuthTokens> {
  const { data } = await rawApi.post<AuthTokens>("/auth/login", { email, password });
  configureApiAuth(data.access_token);
  return data;
}

export async function refreshSession(refreshToken: string): Promise<AuthTokens | null> {
  try {
    const { data } = await rawApi.post<AuthTokens>("/auth/refresh", { refresh_token: refreshToken });
    configureApiAuth(data.access_token);
    return data;
  } catch {
    return null;
  }
}

export async function logoutSession(refreshToken: string): Promise<void> {
  try {
    await api.post("/auth/logout", { refresh_token: refreshToken });
  } catch {
    // no-op, local session should still be cleared
  }
}

export async function fetchCurrentUser(): Promise<CurrentUserResponse | null> {
  try {
    const { data } = await api.get<CurrentUserResponse>("/auth/me");
    return data;
  } catch {
    return null;
  }
}

export async function createAppAccount(payload: AccountCreatePayload): Promise<CurrentUserResponse> {
  const normalized = {
    email: payload.email.trim().toLowerCase(),
    full_name: payload.full_name?.trim() || null,
    password: payload.password,
    role: payload.role,
    active: payload.active ?? true,
  };
  const { data } = await api.post<CurrentUserResponse>("/auth/users", normalized);
  return data;
}

export async function updateMyProfile(payload: { full_name: string }): Promise<CurrentUserResponse> {
  const { data } = await api.put<CurrentUserResponse>("/auth/me", {
    full_name: payload.full_name.trim(),
  });
  return data;
}

export async function changeMyPassword(payload: {
  current_password: string;
  new_password: string;
  confirm_password: string;
}): Promise<AuthTokens> {
  const { data } = await api.post<AuthTokens>("/auth/me/password", payload);
  configureApiAuth(data.access_token);
  return data;
}

export async function fetchEmployees(): Promise<Employee[]> {
  const { data } = await api.get<Employee[]>("/employees");
  return data;
}

export async function upsertEmployee(payload: EmployeeCreatePayload): Promise<Employee> {
  const { data } = await api.post<Employee>("/employees", payload);
  return data;
}

export async function updateEmployee(employeeId: number, payload: EmployeeCreatePayload): Promise<Employee> {
  const { data } = await api.put<Employee>(`/employees/${employeeId}`, payload);
  return data;
}

export async function fetchEmployeeById(employeeId: number): Promise<EmployeeDetail> {
  const { data } = await api.get<EmployeeDetail>(`/employees/${employeeId}`);
  return data;
}

export async function fetchEmployeeDailyAttendance(
  employeeId: number,
  params: { from?: string; to?: string }
): Promise<EmployeeDailyAttendance[]> {
  const { data } = await api.get<EmployeeDailyAttendance[]>(
    `/employees/${employeeId}/daily-attendance`,
    { params }
  );
  return data;
}

export async function fetchDailySummary(
  summaryDate?: string
): Promise<DailySummaryRow[]> {
  const { data } = await api.get<DailySummaryRow[]>("/attendance/daily-summary", {
    params: summaryDate ? { summary_date: summaryDate } : {},
  });
  return data;
}

export async function fetchAttendanceLogs(params: {
  from?: string;
  to?: string;
  employee_code?: string;
  employee_id?: number;
  offset?: number;
  limit?: number;
}): Promise<AttendanceLog[]> {
  const { data } = await api.get<AttendanceLog[]>("/attendance/logs", { params });
  return data;
}

export async function fetchAttendanceSessions(params: {
  from?: string;
  to?: string;
  employee_id?: number;
}): Promise<AttendanceSession[]> {
  const { data } = await api.get<AttendanceSession[]>("/attendance/sessions", {
    params,
  });
  return data;
}

export type DeviceSyncResponse = {
  users_on_device: number;
  new_employees: number;
  attendance_records_fetched: number;
  new_attendance_logs: number;
  placeholder_employees_created?: number;
};

/** Device pulls can take minutes on large terminals; keep this much higher than default API calls. */
const SYNC_HTTP_TIMEOUT_MS = 600_000;

/** Grok narrative can be slower than typical CRUD calls. */
const INSIGHTS_HTTP_TIMEOUT_MS = 90_000;

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
};

export async function fetchAttendanceAnomalies(lookback_days = 30): Promise<AnomalyDetectionResponse> {
  const { data } = await api.get<AnomalyDetectionResponse>("/insights/anomalies", { params: { lookback_days } });
  return data;
}

export type ForecastPoint = {
  date: string;
  predicted_attendance_rate_percent: number;
  predicted_absenteeism_percent: number;
};

export type ForecastResponse = {
  generated_at: string;
  lookback_days: number;
  horizon_days: number;
  points: ForecastPoint[];
};

export async function fetchAttendanceForecast(
  lookback_days = 30,
  horizon_days = 7
): Promise<ForecastResponse> {
  const { data } = await api.get<ForecastResponse>("/insights/forecast", {
    params: { lookback_days, horizon_days },
  });
  return data;
}

export type CopilotQueryResponse = {
  intent: string;
  intent_confidence: "high" | "medium" | "low";
  structured_result: Record<string, unknown>;
  explanation?: { summary: string; insights: string[]; caveats: string[] } | null;
  blocked: boolean;
  block_reason?: string | null;
};

export async function queryInsightsCopilot(question: string): Promise<CopilotQueryResponse> {
  const { data } = await api.post<CopilotQueryResponse>("/insights/copilot/query", { question });
  return data;
}

/** Pull users + attendance from the terminal (read-only), then reload DB-backed views. */
export async function syncFromDevice(full = false): Promise<DeviceSyncResponse> {
  const { data } = await api.post<DeviceSyncResponse>("/sync/device", null, {
    timeout: SYNC_HTTP_TIMEOUT_MS,
    params: full ? { full: true } : {},
  });
  return data;
}

export type AttendanceDayPreview = {
  employee_id: number;
  local_date: string;
  current_check_in: string | null;
  current_check_out: string | null;
  punch_count: number;
};

export type AttendanceAdjustmentRead = {
  correction_uuid: string;
  employee_id: number;
  local_date: string;
  previous_check_in: string | null;
  previous_check_out: string | null;
  new_check_in: string | null;
  new_check_out: string | null;
  status: string;
  device_updated: boolean;
  device_command_uuid: string | null;
  error_message: string | null;
  applied_at: string | null;
};

export async function fetchAttendanceDayPreview(employeeId: number, date: string): Promise<AttendanceDayPreview> {
  const { data } = await api.get<AttendanceDayPreview>(`/attendance/adjust/day/${employeeId}`, { params: { date } });
  return data;
}

export async function applyAttendanceAdjustment(payload: {
  employee_id: number;
  local_date: string;
  new_check_in: string;
  new_check_out?: string | null;
}): Promise<AttendanceAdjustmentRead> {
  const { data } = await api.post<AttendanceAdjustmentRead>("/attendance/adjust/correct", payload, {
    timeout: SYNC_HTTP_TIMEOUT_MS,
  });
  return data;
}

export type OperationalMetrics = {
  queue_depth: number;
  stale_commands: number;
  dead_letter_commands: number;
  failing_devices: number;
  sync_drift_events: number;
  device_health_status?: string;
  device_ip?: string;
  device_port?: number;
  device_auto_sync_enabled?: boolean;
};

export type DeviceCommandRow = {
  command_uuid: string;
  device_id: string;
  command_type: string;
  status: string;
  retries: number;
  last_error: string | null;
  correlation_id: string | null;
  created_by: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type AuditLogRow = {
  id: number;
  actor_user_uuid: string | null;
  action_type: string;
  entity_type: string;
  entity_id: string;
  request_id: string | null;
  timestamp: string;
};

export async function fetchOperationalMetrics(): Promise<OperationalMetrics> {
  const { data } = await api.get<OperationalMetrics>("/ops/metrics");
  return data;
}

export async function fetchDeviceCommands(status?: string): Promise<DeviceCommandRow[]> {
  const { data } = await api.get<DeviceCommandRow[]>("/ops/device-commands", {
    params: status ? { status } : {},
  });
  return data;
}

export async function fetchAuditLogs(): Promise<AuditLogRow[]> {
  const { data } = await api.get<AuditLogRow[]>("/ops/audit-logs");
  return data;
}

export function getApiErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const raw = err.response?.data as { detail?: unknown } | undefined;
    if (typeof raw?.detail === "string") return raw.detail;
    if (Array.isArray(raw?.detail)) {
      return raw.detail
        .map((x) => (typeof x === "object" && x && "msg" in x ? String((x as { msg: unknown }).msg) : String(x)))
        .join("; ");
    }
    if (err.response?.status === 409) {
      return "Device is busy with another sync. Wait a few seconds and try again.";
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return "Request failed";
}

export function formatSyncErrorMessage(err: unknown): string {
  const message = getApiErrorMessage(err);
  if (message.includes("no route to host")) {
    return `${message} You can still enter attendance manually via privileged account adjustment while the device is offline.`;
  }
  if (message.includes("busy") || message.includes("lock")) {
    return message;
  }
  return message;
}
