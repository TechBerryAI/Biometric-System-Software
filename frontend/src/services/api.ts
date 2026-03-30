import axios from "axios";
import type {
  AttendanceLog,
  AttendanceSession,
  DailySummaryRow,
  Employee,
  EmployeeCreatePayload,
  EmployeeDailyAttendance,
  EmployeeDetail,
} from "@/types";

const baseURL =
  import.meta.env.VITE_API_URL?.replace(/\/$/, "") || "http://localhost:8000";

export const api = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

export async function fetchEmployees(): Promise<Employee[]> {
  const { data } = await api.get<Employee[]>("/employees");
  return data;
}

export async function upsertEmployee(payload: EmployeeCreatePayload): Promise<Employee> {
  const { data } = await api.post<Employee>("/employees", payload);
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

/** Pull users + attendance from the terminal (read-only), then reload DB-backed views. */
export async function syncFromDevice(): Promise<DeviceSyncResponse> {
  const { data } = await api.post<DeviceSyncResponse>("/sync/device", null, {
    timeout: SYNC_HTTP_TIMEOUT_MS,
  });
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
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return "Request failed";
}
