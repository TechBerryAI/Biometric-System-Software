import { http, HttpResponse } from "msw";
import { API_BASE_URL } from "@/config/api";

const base = API_BASE_URL.replace(/\/$/, "");

export const mockUser = {
  user_uuid: "usr_TESTADMIN000001",
  email: "admin@company.com",
  full_name: "Admin User",
  role: "SUPER_ADMIN" as const,
  active: true,
  capabilities: {
    attendance_adjust: true,
    forensic_audit: true,
  },
};

export const mockTokens = {
  access_token: "test-access-token",
  token_type: "bearer" as const,
  refresh_token: "test-refresh-token",
  refresh_expires_at: new Date(Date.now() + 86_400_000).toISOString(),
  role: "SUPER_ADMIN",
};

export const mockEmployees = [
  {
    id: 1,
    device_user_id: "1001",
    name: "Ada Lovelace",
    department: "Engineering",
    shift_start: "09:00",
    shift_end: "18:00",
    created_at: "2024-01-01T00:00:00Z",
  },
];

export const mockDailySummary = [
  {
    summary_date: "2024-06-01",
    employee_id: 1,
    device_user_id: "1001",
    employee_name: "Ada Lovelace",
    first_check_in: "2024-06-01T09:00:00Z",
    last_check_out: "2024-06-01T17:00:00Z",
    total_work_minutes: 480,
    sessions_count: 1,
  },
];

export const mockOpsMetrics = {
  queue_depth: 0,
  stale_commands: 0,
  dead_letter_commands: 0,
  failing_devices: 0,
  sync_drift_events: 0,
  device_health_status: "ONLINE",
  device_ip: "192.168.1.200",
  device_port: 4370,
  device_auto_sync_enabled: true,
  incomplete_attendance_days: 0,
  last_attendance_sync_at: "2026-07-22T04:46:00Z",
  incomplete_attendance_samples: [],
  attendance_sync_stale: false,
  device_connectivity_mode: "both",
  device_clock_drift_seconds: 0,
};

export const handlers = [
  http.post(`${base}/auth/forgot-password`, async () => {
    return HttpResponse.json({ status: "ok" });
  }),
  http.post(`${base}/auth/reset-password`, async () => {
    return HttpResponse.json({ status: "ok" });
  }),
  http.post(`${base}/auth/login`, async () => {
    return HttpResponse.json(mockTokens);
  }),
  http.post(`${base}/auth/refresh`, async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { refresh_token?: string };
    if (!body.refresh_token) {
      return HttpResponse.json({ detail: "Missing refresh token" }, { status: 401 });
    }
    return HttpResponse.json(mockTokens);
  }),
  http.post(`${base}/auth/logout`, async () => {
    return new HttpResponse(null, { status: 204 });
  }),
  http.get(`${base}/auth/me`, async ({ request }) => {
    const auth = request.headers.get("authorization");
    if (!auth) return HttpResponse.json({ detail: "Unauthorized" }, { status: 401 });
    return HttpResponse.json(mockUser);
  }),
  http.put(`${base}/auth/me`, async () => {
    return HttpResponse.json(mockUser);
  }),
  http.post(`${base}/auth/me/password`, async () => {
    return HttpResponse.json(mockTokens);
  }),
  http.post(`${base}/auth/users`, async () => {
    return HttpResponse.json({
      ...mockUser,
      email: "new@company.com",
      role: "IT_ADMIN",
    });
  }),
  http.get(`${base}/employees`, async () => {
    return HttpResponse.json(mockEmployees);
  }),
  http.get(`${base}/employees/:id`, async ({ params }) => {
    return HttpResponse.json({
      ...mockEmployees[0],
      id: Number(params.id),
      total_logs: 10,
      first_punch_at: "2024-01-01T09:00:00Z",
      last_punch_at: "2024-06-01T17:00:00Z",
      total_attendance_days: 5,
      total_complete_days: 4,
    });
  }),
  http.get(`${base}/employees/:id/daily-attendance`, async () => {
    return HttpResponse.json([
      {
        summary_date: "2024-06-01",
        first_check_in: "2024-06-01T09:00:00Z",
        last_check_out: "2024-06-01T17:00:00Z",
        total_work_minutes: 480,
        absent: false,
        punch_count: 2,
      },
    ]);
  }),
  http.post(`${base}/employees`, async () => {
    return HttpResponse.json(mockEmployees[0]);
  }),
  http.put(`${base}/employees/:id`, async () => {
    return HttpResponse.json(mockEmployees[0]);
  }),
  http.delete(`${base}/employees/:id`, async () => {
    return new HttpResponse(null, { status: 204 });
  }),
  http.get(`${base}/attendance/daily-summary`, async () => {
    return HttpResponse.json(mockDailySummary);
  }),
  http.get(`${base}/attendance/daily-summary/range`, async () => {
    return HttpResponse.json({ "2024-06-01": mockDailySummary });
  }),
  http.get(`${base}/attendance/day-punches`, async ({ request }) => {
    const url = new URL(request.url);
    const employeeId = Number(url.searchParams.get("employee_id") || "1");
    const date = url.searchParams.get("date") || "2024-06-01";
    return HttpResponse.json({
      employee_id: employeeId,
      employee_name: "Ada Lovelace",
      device_user_id: "1001",
      local_date: date,
      first_check_in: "2024-06-01T08:00:00Z",
      last_check_out: "2024-06-01T17:00:00Z",
      total_work_minutes: 540,
      punches: [
        {
          id: 1,
          timestamp: "2024-06-01T08:00:00Z",
          device_id: "main-entrance",
          punch_type: "0",
          role: "in",
        },
        {
          id: 2,
          timestamp: "2024-06-01T17:00:00Z",
          device_id: "main-entrance",
          punch_type: "1",
          role: "out",
        },
      ],
    });
  }),
  http.get(`${base}/attendance/logs`, async () => {
    return HttpResponse.json([]);
  }),
  http.get(`${base}/ops/metrics`, async () => {
    return HttpResponse.json(mockOpsMetrics);
  }),
  http.get(`${base}/ops/device-commands`, async () => {
    return HttpResponse.json([]);
  }),
  http.get(`${base}/insights/management`, async () => {
    return HttpResponse.json({
      available: true,
      source: "rules",
      bullets: ["All systems nominal"],
    });
  }),
  http.get(`${base}/insights/anomalies`, async () => {
    return HttpResponse.json({
      period_start: "2024-05-01",
      period_end: "2024-06-01",
      detector: "heuristic",
      anomalies: [],
    });
  }),
  http.post(`${base}/sync/device`, async () => {
    return HttpResponse.json({
      users_on_device: 1,
      new_employees: 0,
      attendance_records_fetched: 0,
      new_attendance_logs: 0,
    });
  }),
  http.get(`${base}/attendance/adjust/capabilities`, async () => {
    return HttpResponse.json({
      tier: "A",
      record_size: 40,
      supports_selective_delete: true,
      supports_full_rewrite: true,
      supports_write: true,
      strict_device_authority: true,
      correction_allow_db_only_fallback: false,
    });
  }),
  http.get(`${base}/attendance/adjust/day/:employeeId`, async () => {
    return HttpResponse.json({
      employee_id: 1,
      local_date: "2024-06-01",
      current_check_in: "2024-06-01T09:00:00",
      current_check_out: "2024-06-01T17:00:00",
      punch_count: 2,
    });
  }),
  http.post(`${base}/attendance/adjust/correct`, async () => {
    return HttpResponse.json({
      employee_id: 1,
      local_date: "2024-06-01",
      previous_check_in: "2024-06-01T09:00:00",
      previous_check_out: "2024-06-01T17:00:00",
      new_check_in: "2024-06-01T09:05:00",
      new_check_out: "2024-06-01T17:00:00",
      status: "applied",
      device_updated: true,
      device_command_uuid: "cmd-1",
      device_tier: "A",
      error_message: null,
      applied_at: new Date().toISOString(),
    });
  }),
];
