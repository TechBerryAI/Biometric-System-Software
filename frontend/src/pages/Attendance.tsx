import { useCallback, useEffect, useState } from "react";
import { fetchAttendanceLogs, fetchAttendanceSessions, fetchEmployees } from "@/services/api";
import type { AttendanceLog, AttendanceSession, Employee } from "@/types";

function todayISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function Attendance() {
  const [date, setDate] = useState(todayISO);
  const [employeeId, setEmployeeId] = useState<string>("");
  const [logs, setLogs] = useState<AttendanceLog[]>([]);
  const [sessions, setSessions] = useState<AttendanceSession[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const emps = await fetchEmployees();
      setEmployees(emps);
      const params = {
        from: date,
        to: date,
        ...(employeeId ? { employee_id: Number(employeeId) } : {}),
      };
      const [lg, ss] = await Promise.all([
        fetchAttendanceLogs({ from: date, to: date }),
        fetchAttendanceSessions(params),
      ]);
      setLogs(lg);
      setSessions(ss);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load attendance");
    } finally {
      setLoading(false);
    }
  }, [date, employeeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const empName = (id: number) => employees.find((e) => e.id === id)?.name ?? `Employee ${id}`;

  return (
    <div className="space-y-8">
      <div>
        <h2 className="font-display text-2xl font-bold text-ink-950">Attendance</h2>
        <p className="mt-1 text-sm text-ink-600">Raw logs and paired sessions for the selected day</p>
      </div>

      <div className="flex flex-wrap items-end gap-4 rounded-2xl border border-ink-800/10 bg-white p-4 shadow-sm">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium text-ink-800">Date</span>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="rounded-lg border border-ink-800/20 px-3 py-2 text-ink-950"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm min-w-[12rem]">
          <span className="font-medium text-ink-800">Sessions filter (employee)</span>
          <select
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
            className="rounded-lg border border-ink-800/20 px-3 py-2 text-ink-950"
          >
            <option value="">All employees</option>
            {employees.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name} ({e.device_user_id})
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error ? (
        <div className="rounded-xl border border-warn/30 bg-orange-50 p-4 text-warn">{error}</div>
      ) : null}

      <section className="space-y-3">
        <h3 className="font-display text-lg font-semibold text-ink-950">Raw logs</h3>
        <div className="overflow-x-auto rounded-2xl border border-ink-800/10 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-mist/80 text-xs uppercase text-ink-600">
              <tr>
                <th className="px-4 py-2">Time</th>
                <th className="px-4 py-2">Employee code</th>
                <th className="px-4 py-2">Punch</th>
                <th className="px-4 py-2">Device</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800/10">
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-ink-600">
                    No logs for this date
                  </td>
                </tr>
              ) : (
                logs.map((l) => (
                  <tr key={l.id} className="hover:bg-mist/40">
                    <td className="px-4 py-2 whitespace-nowrap">
                      {new Date(l.timestamp).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 font-mono text-xs">{l.employee_code}</td>
                    <td className="px-4 py-2">{l.punch_type}</td>
                    <td className="px-4 py-2 text-ink-600">{l.device_id}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="font-display text-lg font-semibold text-ink-950">Sessions</h3>
        <div className="overflow-x-auto rounded-2xl border border-ink-800/10 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-mist/80 text-xs uppercase text-ink-600">
              <tr>
                <th className="px-4 py-2">Employee</th>
                <th className="px-4 py-2">Check in</th>
                <th className="px-4 py-2">Check out</th>
                <th className="px-4 py-2">Work (min)</th>
                <th className="px-4 py-2">Late</th>
                <th className="px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-ink-800/10">
              {sessions.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-center text-ink-600">
                    No sessions for this filter
                  </td>
                </tr>
              ) : (
                sessions.map((s) => (
                  <tr key={s.id} className="hover:bg-mist/40">
                    <td className="px-4 py-2">{empName(s.employee_id)}</td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      {new Date(s.check_in).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 whitespace-nowrap">
                      {s.check_out ? new Date(s.check_out).toLocaleString() : "—"}
                    </td>
                    <td className="px-4 py-2">{s.work_duration ?? "—"}</td>
                    <td className="px-4 py-2">{s.late_minutes ?? "—"}</td>
                    <td className="px-4 py-2">
                      <span
                        className={
                          s.status === "complete"
                            ? "text-accent"
                            : "text-warn font-medium"
                        }
                      >
                        {s.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
