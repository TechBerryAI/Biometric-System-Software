import axios from "axios";
import type {
  AttendanceLog,
  AttendanceSession,
  DailySummaryRow,
  Employee,
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
