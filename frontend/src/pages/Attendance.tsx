import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchDailySummary, fetchEmployees } from "@/services/api";
import type { DailySummaryRow, Employee } from "@/types";

function todayISO(): string {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function fmtDateTime(v: string | null): string {
  if (!v) return "-";
  return new Date(v).toLocaleString();
}

type AttendanceRow = DailySummaryRow & { is_absent: boolean };

export function Attendance() {
  const [date, setDate] = useState(todayISO);
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<AttendanceRow[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [emps, summary] = await Promise.all([fetchEmployees(), fetchDailySummary(date)]);
      setEmployees(emps);
      setRows(
        summary.map((r) => ({
          ...r,
          is_absent: r.first_check_in == null,
        }))
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load attendance");
    } finally {
      setLoading(false);
    }
  }, [date]);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = q
      ? rows.filter(
          (r) =>
            r.employee_name.toLowerCase().includes(q) ||
            String(r.device_user_id).includes(q)
        )
      : rows;

    // Sort by first check-in (earliest first). Absent employees always at bottom.
    return [...list].sort((a, b) => {
      if (a.first_check_in && b.first_check_in) {
        return new Date(a.first_check_in).getTime() - new Date(b.first_check_in).getTime();
      }
      if (a.first_check_in && !b.first_check_in) return -1;
      if (!a.first_check_in && b.first_check_in) return 1;
      return a.employee_name.localeCompare(b.employee_name);
    });
  }, [rows, query]);

  const presentCount = filtered.filter((r) => !r.is_absent).length;
  const lateCount = filtered.filter((r) => !r.is_absent && r.late_arrival).length;
  const absentCount = filtered.filter((r) => r.is_absent).length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-ink-950">Daily attendance</h2>
        <p className="mt-1 text-sm text-ink-600">
          Simple view for all employees, ordered by in-time.
        </p>
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

        <label className="flex min-w-[14rem] flex-col gap-1 text-sm">
          <span className="font-medium text-ink-800">Search employee</span>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Name or device ID"
            className="rounded-lg border border-ink-800/20 px-3 py-2 text-ink-950"
          />
        </label>

        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {error ? (
        <div className="rounded-xl border border-warn/30 bg-orange-50 p-4 text-warn">{error}</div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-ink-800/10 bg-white p-4 shadow-sm">
          <p className="text-xs uppercase tracking-wide text-ink-600">Total employees</p>
          <p className="mt-2 font-display text-2xl font-bold text-ink-950">{filtered.length || employees.length}</p>
        </div>
        <div className="rounded-xl border border-ink-800/10 bg-white p-4 shadow-sm">
          <p className="text-xs uppercase tracking-wide text-ink-600">Present</p>
          <p className="mt-2 font-display text-2xl font-bold text-ink-950">{presentCount}</p>
        </div>
        <div className="rounded-xl border border-ink-800/10 bg-white p-4 shadow-sm">
          <p className="text-xs uppercase tracking-wide text-ink-600">Late</p>
          <p className="mt-2 font-display text-2xl font-bold text-ink-950">{lateCount}</p>
        </div>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-ink-800/10 bg-white shadow-sm">
        <table className="w-full text-left text-sm">
          <thead className="bg-mist/80 text-xs uppercase text-ink-600">
            <tr>
              <th className="px-4 py-2">#</th>
              <th className="px-4 py-2">Employee</th>
              <th className="px-4 py-2">Device ID</th>
              <th className="px-4 py-2">In time</th>
              <th className="px-4 py-2">Out time</th>
              <th className="px-4 py-2">Work (min)</th>
              <th className="px-4 py-2">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-800/10">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-ink-600">
                  No employees found for this filter
                </td>
              </tr>
            ) : (
              filtered.map((r, idx) => (
                <tr key={r.employee_id} className="hover:bg-mist/40">
                  <td className="px-4 py-2 text-ink-600">{idx + 1}</td>
                  <td className="px-4 py-2 font-medium text-ink-950">{r.employee_name}</td>
                  <td className="px-4 py-2 text-ink-600">{r.device_user_id}</td>
                  <td className="px-4 py-2 whitespace-nowrap">{fmtDateTime(r.first_check_in)}</td>
                  <td className="px-4 py-2 whitespace-nowrap">{fmtDateTime(r.last_check_out)}</td>
                  <td className="px-4 py-2">{r.total_work_minutes ?? "-"}</td>
                  <td className="px-4 py-2">
                    {r.is_absent ? (
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                        Absent
                      </span>
                    ) : r.late_arrival ? (
                      <span className="rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-warn">
                        Late
                      </span>
                    ) : (
                      <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs font-medium text-accent">
                        On time
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-ink-600">
        Absent today: {absentCount}. Sorted by earliest in-time first; absent employees are listed last.
      </p>
    </div>
  );
}
