import { api, SYNC_HTTP_TIMEOUT_MS } from "@/shared/api/client";
import type { AttendanceLog, DailySummaryRow, DayPunchesResponse } from "@/types";

export async function fetchDailySummary(summaryDate?: string): Promise<DailySummaryRow[]> {
  const { data } = await api.get<DailySummaryRow[]>("/attendance/daily-summary", {
    params: summaryDate ? { summary_date: summaryDate } : {},
  });
  return data;
}

/** Single request for a date range — avoids N parallel full-roster summary calls. */
export async function fetchDailySummaryRange(
  from: string,
  to: string
): Promise<Record<string, DailySummaryRow[]>> {
  const { data } = await api.get<Record<string, DailySummaryRow[]>>(
    "/attendance/daily-summary/range",
    { params: { from, to } }
  );
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

export async function fetchDayPunches(employeeId: number, date: string): Promise<DayPunchesResponse> {
  const { data } = await api.get<DayPunchesResponse>("/attendance/day-punches", {
    params: { employee_id: employeeId, date },
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
  employee_id: number;
  local_date: string;
  previous_check_in: string | null;
  previous_check_out: string | null;
  new_check_in: string | null;
  new_check_out: string | null;
  status: string;
  device_updated: boolean;
  device_command_uuid: string | null;
  device_tier: string | null;
  error_message: string | null;
  applied_at: string | null;
};

export type CorrectionCapabilities = {
  tier: string;
  record_size: number | null;
  supports_selective_delete: boolean;
  supports_full_rewrite: boolean;
  supports_write: boolean;
  strict_device_authority: boolean;
  correction_allow_db_only_fallback: boolean;
};

export async function fetchCorrectionCapabilities(): Promise<CorrectionCapabilities> {
  const { data } = await api.get<CorrectionCapabilities>("/attendance/adjust/capabilities");
  return data;
}

export async function fetchCorrectionStatus(commandUuid: string): Promise<AttendanceAdjustmentRead> {
  const { data } = await api.get<AttendanceAdjustmentRead>(`/attendance/adjust/commands/${commandUuid}`);
  return data;
}

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
  const { data, status } = await api.post<AttendanceAdjustmentRead>("/attendance/adjust/correct", payload, {
    timeout: SYNC_HTTP_TIMEOUT_MS,
    validateStatus: (code) => (code >= 200 && code < 300) || code === 202,
  });
  if (status === 202) {
    return { ...data, status: data.status || "device_pending" };
  }
  return data;
}
