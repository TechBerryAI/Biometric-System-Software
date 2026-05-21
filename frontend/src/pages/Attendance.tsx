import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import type { ExportPeriod } from "@/lib/dates";
import { dateList, getExportRange, todayISO } from "@/lib/dates";
import {
  fetchDailySummary,
  fetchEmployees,
  getApiErrorMessage,
  syncFromDevice,
} from "@/services/api";
import { useUiStore } from "@/stores/ui-store";
import type { DailySummaryRow, Employee } from "@/types";
import { downloadAttendanceSummaryPdf } from "@/utils/pdfReports";

function fmtDateTime(v: string | null): string {
  if (!v) return "—";
  return new Date(v).toLocaleString();
}

function fmtWorkHm(total: number | null): string {
  if (total == null) return "—";
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (h === 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
}

type AttendanceRow = DailySummaryRow & { is_absent: boolean };

export function Attendance() {
  const [date, setDate] = useState(todayISO);
  const globalSearchQuery = useUiStore((s) => s.globalSearchQuery);
  const [rows, setRows] = useState<AttendanceRow[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(false);
  const [exportPeriod, setExportPeriod] = useState<ExportPeriod>("day");
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRoster = useCallback(async () => {
    const [emps, summary] = await Promise.all([fetchEmployees(), fetchDailySummary(date)]);
    setEmployees(emps);
    setRows(
      summary.map((r) => ({
        ...r,
        is_absent: r.first_check_in == null,
      }))
    );
  }, [date]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await fetchRoster();
    } catch (e: unknown) {
      setError(getApiErrorMessage(e) || "Failed to load attendance");
    } finally {
      setLoading(false);
    }
  }, [fetchRoster]);

  /** Same as scripts/sync_from_device.py via API, then reload roster for the selected date. */
  const refreshFromDevice = useCallback(async () => {
    setLoading(true);
    setError(null);
    let syncWarning: string | null = null;
    try {
      await syncFromDevice();
    } catch (e: unknown) {
      syncWarning = getApiErrorMessage(e);
    }
    try {
      await fetchRoster();
      if (syncWarning) {
        setError(`${syncWarning} Roster may be stale until the device is reachable.`);
      }
    } catch (e: unknown) {
      setError(getApiErrorMessage(e) || "Failed to load attendance");
    } finally {
      setLoading(false);
    }
  }, [fetchRoster]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const intervalMs = 120_000;
    const id = window.setInterval(() => {
      void refreshFromDevice();
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [refreshFromDevice]);

  const filtered = useMemo(() => {
    const q = globalSearchQuery.trim().toLowerCase();
    const list = q
      ? rows.filter(
          (r) =>
            r.employee_name.toLowerCase().includes(q) || String(r.device_user_id).toLowerCase().includes(q)
        )
      : rows;

    return [...list].sort((a, b) => {
      if (a.first_check_in && b.first_check_in) {
        return new Date(a.first_check_in).getTime() - new Date(b.first_check_in).getTime();
      }
      if (a.first_check_in && !b.first_check_in) return -1;
      if (!a.first_check_in && b.first_check_in) return 1;
      return a.employee_name.localeCompare(b.employee_name);
    });
  }, [rows, globalSearchQuery]);

  const presentCount = filtered.filter((r) => !r.is_absent).length;
  const absentCount = filtered.filter((r) => r.is_absent).length;

  const exportReport = useCallback(async () => {
    setExporting(true);
    try {
      const range = getExportRange(date, exportPeriod);
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
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-display-xl text-ink">Attendance</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
          Daily roster sorted by punch order.{" "}
          <span className="text-ink-subtle">
            Refresh pulls the latest punches from the terminal, then reloads this view; the same sync runs every 2
            minutes in the background.
          </span>
        </p>
      </header>

      <Card className="overflow-hidden">
        <CardContent className="flex flex-col gap-4 p-6 sm:flex-row sm:flex-wrap sm:items-end">
          <label className="flex min-w-[10rem] flex-col gap-1.5 text-sm">
            <span className="text-xs font-medium text-ink-muted">Date</span>
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
          <Button type="button" variant="secondary" onClick={() => void refreshFromDevice()} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} />
            Refresh
          </Button>
        </CardContent>
      </Card>

      <Card className="border-primary/10 bg-gradient-to-br from-primary-soft/40 via-surface-card to-surface-card">
        <CardContent className="flex flex-col gap-4 p-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="font-display text-display-lg text-ink">Export</h2>
            <p className="mt-1 max-w-xl text-sm text-ink-muted">
              Generate a printable PDF for the selected window — perfect for audits and payroll handoff.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-xs font-medium text-ink-muted">Period</span>
              <select
                value={exportPeriod}
                onChange={(e) => setExportPeriod(e.target.value as ExportPeriod)}
                className="h-10 min-w-[12rem] rounded-xl border border-line bg-surface-card px-3 text-sm text-ink shadow-sm transition-shadow hover:border-line focus-visible:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/15"
              >
                <option value="day">Single day</option>
                <option value="week">Last 7 days</option>
                <option value="month">Last 30 days</option>
              </select>
            </label>
            <Button type="button" onClick={() => void exportReport()} disabled={exporting} className="min-w-[140px]">
              {exporting ? "Preparing…" : "Download PDF"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {error ? (
        <Card className="border-status-absent-soft bg-status-absent-soft/25">
          <CardContent className="p-4">
            <p className="text-sm text-status-absent">{error}</p>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 sm:grid-cols-3">
        {[
          { label: "In view", value: filtered.length || employees.length },
          { label: "Present", value: presentCount },
          { label: "Absent", value: absentCount },
        ].map((k, i) => (
          <motion.div
            key={k.label}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
          >
            <Card className="transition-shadow duration-300 hover:shadow-card-hover">
              <CardContent className="p-5">
                <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">{k.label}</p>
                <p className="mt-2 font-display text-3xl font-semibold text-ink tabular-nums">{k.value}</p>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      <p className="text-xs text-ink-muted">
        Absent today (in view): <span className="font-medium text-ink">{absentCount}</span>. Sorted by earliest
        check-in; absent rows follow present colleagues.
      </p>

      <div className="overflow-hidden rounded-2xl border border-line/70 bg-surface-card shadow-card">
        <div className="scrollbar-thin overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="sticky top-0 z-[1] bg-surface/95 backdrop-blur-sm">
              <tr className="text-xs font-medium uppercase tracking-wider text-ink-muted shadow-[inset_0_-1px_0_#E2E8F0]">
                <th className="px-5 py-3.5">#</th>
                <th className="px-5 py-3.5">Employee</th>
                <th className="px-5 py-3.5 whitespace-nowrap">In</th>
                <th className="px-5 py-3.5 whitespace-nowrap">Out</th>
                <th className="px-5 py-3.5">Total work</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-5 py-16 text-center text-ink-muted">
                    No rows for this filter.
                  </td>
                </tr>
              ) : (
                filtered.map((r, idx) => (
                  <tr
                    key={r.employee_id}
                    className={cn(
                      "border-b border-line/40 transition-colors hover:bg-surface/80",
                      idx % 2 === 1 && "bg-surface/[0.35]"
                    )}
                  >
                    <td className="px-5 py-3.5 tabular-nums text-ink-muted">{idx + 1}</td>
                    <td className="px-5 py-3.5">
                      <p className="font-medium text-ink">{r.employee_name}</p>
                      <p className="text-xs text-ink-muted font-mono">{r.device_user_id}</p>
                    </td>
                    <td className="px-5 py-3.5 whitespace-nowrap text-ink-muted">{fmtDateTime(r.first_check_in)}</td>
                    <td className="px-5 py-3.5 whitespace-nowrap text-ink-muted">{fmtDateTime(r.last_check_out)}</td>
                    <td className="px-5 py-3.5 tabular-nums text-ink-muted">{fmtWorkHm(r.total_work_minutes)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
