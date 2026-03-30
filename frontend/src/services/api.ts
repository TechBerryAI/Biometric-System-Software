import axios from "axios";
import type {
  AttendanceLog,
  AttendanceSession,
  DailySummaryRow,
  Employee,
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
