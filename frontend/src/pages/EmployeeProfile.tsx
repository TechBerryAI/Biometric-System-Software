import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  fetchEmployeeById,
  fetchEmployeeDailyAttendance,
} from "@/services/api";
import type { EmployeeDailyAttendance, EmployeeDetail } from "@/types";
import { downloadEmployeeReportPdf } from "@/utils/pdfReports";

function fmtDateTime(v: string | null): string {
  if (!v) return "-";
  return new Date(v).toLocaleString();
}

function fmtDate(v: string): string {
  return new Date(`${v}T00:00:00`).toLocaleDateString();
}

function fmtMinutes(total: number | null): string {
  if (total == null) return "-";
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function defaultFromDate(): string {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function todayISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

type TabId = "profile" | "attendance";

export function EmployeeProfile() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const numericEmployeeId = Number(employeeId);

  const [tab, setTab] = useState<TabId>("profile");
  const [employee, setEmployee] = useState<EmployeeDetail | null>(null);
  const [rows, setRows] = useState<EmployeeDailyAttendance[]>([]);
  const [fromDate, setFromDate] = useState(defaultFromDate);
  const [toDate, setToDate] = useState(todayISO);
  const [loadingEmployee, setLoadingEmployee] = useState(true);
  const [loadingAttendance, setLoadingAttendance] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadEmployee = useCallback(async () => {
    if (!Number.isFinite(numericEmployeeId)) return;
    setLoadingEmployee(true);
    setError(null);
    try {
      const data = await fetchEmployeeById(numericEmployeeId);
      setEmployee(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load employee");
    } finally {
      setLoadingEmployee(false);
    }
  }, [numericEmployeeId]);

  const loadAttendance = useCallback(async () => {
    if (!Number.isFinite(numericEmployeeId)) return;
    setLoadingAttendance(true);
    setError(null);
    try {
      const data = await fetchEmployeeDailyAttendance(numericEmployeeId, {
        from: fromDate,
        to: toDate,
      });
      setRows(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load daily attendance");
    } finally {
      setLoadingAttendance(false);
    }
  }, [numericEmployeeId, fromDate, toDate]);

  useEffect(() => {
    void loadEmployee();
  }, [loadEmployee]);

  useEffect(() => {
    void loadAttendance();
  }, [loadAttendance]);

  const stats = useMemo(() => {
    const present = rows.filter((r) => !r.absent).length;
    const late = rows.filter((r) => !r.absent && r.late_arrival).length;
    const absent = rows.filter((r) => r.absent).length;
    return { present, late, absent };
  }, [rows]);

  const exportReport = useCallback(() => {
    if (!employee) return;
    setDownloading(true);
    try {
      downloadEmployeeReportPdf({ employee, rows, fromDate, toDate });
    } finally {
      setDownloading(false);
    }
  }, [employee, rows, fromDate, toDate]);

  if (!Number.isFinite(numericEmployeeId)) {
    return (
      <div className="rounded-xl border border-warn/30 bg-orange-50 p-6 text-warn">
        Invalid employee id in URL.
      </div>
    );
  }

  if (loadingEmployee && employee == null) {
    return <p className="text-ink-600">Loading employee profile…</p>;
  }

  if (error && employee == null) {
    return (
      <div className="rounded-xl border border-warn/30 bg-orange-50 p-6 text-warn">
        {error}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-2xl font-bold text-ink-950">
            {employee?.name ?? "Employee"}
          </h2>
          <p className="mt-1 text-sm text-ink-600">
            Device ID:{" "}
            <span className="rounded-md bg-teal-50 px-2 py-1 font-mono text-xs text-accent">
              {employee?.device_user_id ?? "-"}
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={exportReport}
            disabled={!employee}
            className="inline-flex min-h-[42px] items-center justify-center rounded-xl bg-accent px-4 py-2.5 text-sm font-bold text-white shadow-lg ring-2 ring-teal-600/45 ring-offset-2 hover:bg-teal-600 disabled:opacity-50"
          >
            {downloading ? "Preparing PDF…" : "Download PDF report"}
          </button>
          <Link
            to="/employees"
            className="rounded-lg border border-ink-800/20 bg-white px-3 py-2 text-sm text-ink-800 hover:bg-mist/40"
          >
            Back to employees
          </Link>
        </div>
      </div>

      <div className="rounded-2xl border border-ink-800/10 bg-white p-2 shadow-sm">
        <div className="flex gap-2">
          <button
            type="button"
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              tab === "profile" ? "bg-accent text-white" : "text-ink-700 hover:bg-mist/50"
            }`}
            onClick={() => setTab("profile")}
          >
            Profile
          </button>
          <button
            type="button"
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              tab === "attendance" ? "bg-accent text-white" : "text-ink-700 hover:bg-mist/50"
            }`}
            onClick={() => setTab("attendance")}
          >
            Daily attendance
          </button>
        </div>
      </div>

      {tab === "profile" ? (
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <div className="rounded-xl border border-ink-800/10 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wide text-ink-600">Total logs</p>
              <p className="mt-2 font-display text-2xl font-bold text-ink-950">
                {employee?.total_logs ?? 0}
              </p>
            </div>
            <div className="rounded-xl border border-ink-800/10 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wide text-ink-600">Attendance days</p>
              <p className="mt-2 font-display text-2xl font-bold text-ink-950">
                {employee?.total_attendance_days ?? 0}
              </p>
            </div>
            <div className="rounded-xl border border-ink-800/10 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wide text-ink-600">Complete days</p>
              <p className="mt-2 font-display text-2xl font-bold text-ink-950">
                {employee?.total_complete_days ?? 0}
              </p>
            </div>
            <div className="rounded-xl border border-ink-800/10 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wide text-ink-600">First punch</p>
              <p className="mt-2 text-sm font-medium text-ink-900">
                {fmtDateTime(employee?.first_punch_at ?? null)}
              </p>
            </div>
            <div className="rounded-xl border border-ink-800/10 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wide text-ink-600">Last punch</p>
              <p className="mt-2 text-sm font-medium text-ink-900">
                {fmtDateTime(employee?.last_punch_at ?? null)}
              </p>
            </div>
          </div>

          <div className="rounded-2xl border border-ink-800/10 bg-white p-6 shadow-sm">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-ink-700">
              Employee details
            </h3>
            <dl className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-600">Employee ID</dt>
                <dd className="mt-1 text-sm text-ink-950">{employee?.id ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-600">Name</dt>
                <dd className="mt-1 text-sm text-ink-950">{employee?.name ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-600">Device user ID</dt>
                <dd className="mt-1 text-sm text-ink-950">{employee?.device_user_id ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-600">Device UID</dt>
                <dd className="mt-1 text-sm text-ink-950">{employee?.device_uid ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-600">Device privilege</dt>
                <dd className="mt-1 text-sm text-ink-950">{employee?.device_privilege ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-600">Device group ID</dt>
                <dd className="mt-1 text-sm text-ink-950">{employee?.device_group_id ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-600">Device card</dt>
                <dd className="mt-1 text-sm text-ink-950">{employee?.device_card ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-600">Department</dt>
                <dd className="mt-1 text-sm text-ink-950">{employee?.department ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-600">Shift start</dt>
                <dd className="mt-1 text-sm text-ink-950">{employee?.shift_start ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase tracking-wide text-ink-600">Shift end</dt>
                <dd className="mt-1 text-sm text-ink-950">{employee?.shift_end ?? "-"}</dd>
              </div>
            </dl>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-end gap-4 rounded-2xl border border-ink-800/10 bg-white p-4 shadow-sm">
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-ink-800">From</span>
              <input
                type="date"
                value={fromDate}
                onChange={(e) => setFromDate(e.target.value)}
                className="rounded-lg border border-ink-800/20 px-3 py-2 text-ink-950"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="font-medium text-ink-800">To</span>
              <input
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                className="rounded-lg border border-ink-800/20 px-3 py-2 text-ink-950"
              />
            </label>
            <button
              type="button"
              onClick={() => void loadAttendance()}
              disabled={loadingAttendance}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {loadingAttendance ? "Loading..." : "Refresh"}
            </button>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-ink-800/10 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wide text-ink-600">Present days</p>
              <p className="mt-2 font-display text-2xl font-bold text-ink-950">{stats.present}</p>
            </div>
            <div className="rounded-xl border border-ink-800/10 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wide text-ink-600">Late days</p>
              <p className="mt-2 font-display text-2xl font-bold text-ink-950">{stats.late}</p>
            </div>
            <div className="rounded-xl border border-ink-800/10 bg-white p-4 shadow-sm">
              <p className="text-xs uppercase tracking-wide text-ink-600">Absent days</p>
              <p className="mt-2 font-display text-2xl font-bold text-ink-950">{stats.absent}</p>
            </div>
          </div>

          {error ? (
            <div className="rounded-xl border border-warn/30 bg-orange-50 p-4 text-warn">
              {error}
            </div>
          ) : null}

          <div className="overflow-x-auto rounded-2xl border border-ink-800/10 bg-white shadow-sm">
            <table className="w-full text-left text-sm">
              <thead className="bg-mist/80 text-xs uppercase text-ink-600">
                <tr>
                  <th className="px-4 py-2">Date</th>
                  <th className="px-4 py-2">In time</th>
                  <th className="px-4 py-2">Out time</th>
                  <th className="px-4 py-2">Total work (HH:mm)</th>
                  <th className="px-4 py-2">Late</th>
                  <th className="px-4 py-2">Absent</th>
                  <th className="px-4 py-2">Punches</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-800/10">
                {rows.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-ink-600">
                      No daily attendance found for selected range.
                    </td>
                  </tr>
                ) : (
                  rows.map((r) => (
                    <tr key={r.summary_date} className="hover:bg-mist/40">
                      <td className="px-4 py-2">{fmtDate(r.summary_date)}</td>
                      <td className="px-4 py-2 whitespace-nowrap">{fmtDateTime(r.first_check_in)}</td>
                      <td className="px-4 py-2 whitespace-nowrap">{fmtDateTime(r.last_check_out)}</td>
                      <td className="px-4 py-2">{fmtMinutes(r.total_work_minutes)}</td>
                      <td className="px-4 py-2">{r.late_arrival ? "Yes" : "No"}</td>
                      <td className="px-4 py-2">{r.absent ? "Yes" : "No"}</td>
                      <td className="px-4 py-2">{r.punch_count}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
