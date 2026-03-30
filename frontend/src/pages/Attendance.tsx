import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchDailySummary, fetchEmployees } from "@/services/api";
import type { DailySummaryRow, Employee } from "@/types";
import { downloadAttendanceSummaryPdf } from "@/utils/pdfReports";

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
type ExportPeriod = "day" | "week" | "month";

function addDays(date: Date, days: number): Date {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

function formatISO(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function getRange(baseDateISO: string, period: ExportPeriod): { from: string; to: string; label: string } {
  const d = new Date(`${baseDateISO}T00:00:00`);
  if (period === "day") {
    return { from: baseDateISO, to: baseDateISO, label: `Day ${baseDateISO}` };
  }
  if (period === "week") {
    // Trailing 7-day window ending on selected date (past-only).
    const start = addDays(d, -6);
    return {
      from: formatISO(start),
      to: baseDateISO,
      label: `Last 7 days (${formatISO(start)} to ${baseDateISO})`,
    };
  }
  // Trailing 30-day window ending on selected date (past-only).
  const start = addDays(d, -29);
  return {
    from: formatISO(start),
    to: baseDateISO,
    label: `Last 30 days (${formatISO(start)} to ${baseDateISO})`,
  };
}

function dateList(fromISO: string, toISO: string): string[] {
  const out: string[] = [];
  let cur = new Date(`${fromISO}T00:00:00`);
  const end = new Date(`${toISO}T00:00:00`);
  while (cur <= end) {
    out.push(formatISO(cur));
    cur = addDays(cur, 1);
  }
  return out;
}

export function Attendance() {
  const [date, setDate] = useState(todayISO);
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<AttendanceRow[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(false);
  const [exportPeriod, setExportPeriod] = useState<ExportPeriod>("day");
  const [exporting, setExporting] = useState(false);
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

  const exportReport = useCallback(async () => {
    setExporting(true);
    try {
      const range = getRange(date, exportPeriod);
      const dates = dateList(range.from, range.to);
      const allRows: Array<DailySummaryRow & { summary_date: string }> = [];
      for (const day of dates) {
        const summary = await fetchDailySummary(day);
        for (const row of summary) {
          allRows.push({ ...row, summary_date: day });
        }
      }
      downloadAttendanceSummaryPdf({
        periodLabel: range.label,
        rows: allRows,
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to export PDF report");
    } finally {
      setExporting(false);
    }
  }, [date, exportPeriod]);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-display text-2xl font-bold text-ink-950">Daily attendance</h2>
        <p className="mt-1 text-sm text-ink-600">
          Simple view for all employees, ordered by in-time.
        </p>
      </div>

      <div className="space-y-4">
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

        <div className="flex flex-col gap-3 rounded-2xl border-2 border-accent/35 bg-gradient-to-br from-teal-50/90 to-white p-4 shadow-sm sm:flex-row sm:flex-wrap sm:items-end">
          <div className="min-w-0 flex-1 sm:flex-initial">
            <p className="font-display text-sm font-bold text-ink-950">Export PDF report</p>
            <p className="mt-0.5 text-xs text-ink-600">
              All employees for the selected day, week, or month. Opens as a printable PDF.
            </p>
          </div>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-ink-800">Period</span>
            <select
              value={exportPeriod}
              onChange={(e) => setExportPeriod(e.target.value as ExportPeriod)}
              className="min-w-[10rem] rounded-lg border border-ink-800/25 bg-white px-3 py-2.5 text-ink-950 shadow-sm"
            >
              <option value="day">Single day (uses date above)</option>
              <option value="week">Last 7 days (ending on date above)</option>
              <option value="month">Last 30 days (ending on date above)</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => void exportReport()}
            disabled={exporting}
            className="inline-flex min-h-[44px] items-center justify-center rounded-xl bg-accent px-6 py-3 text-sm font-bold uppercase tracking-wide text-white shadow-lg ring-2 ring-teal-600/50 ring-offset-2 hover:bg-teal-600 disabled:opacity-55"
          >
            {exporting ? "Preparing PDF…" : "Download PDF"}
          </button>
        </div>
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
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-800/10">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-ink-600">
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
