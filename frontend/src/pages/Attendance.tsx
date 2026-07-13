import { motion } from "framer-motion";
import { Download } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/cn";
import type { ExportPeriod } from "@/lib/dates";
import { dateList, fmtDisplayDateTime, getExportRange, todayISO } from "@/lib/dates";
import {
  fetchDailySummary,
  fetchDailySummaryRange,
  fetchEmployees,
  getApiErrorMessage,
} from "@/services/api";
import { useUiStore } from "@/stores/ui-store";
import { ReportFormatDialog } from "@/components/reports/ReportFormatDialog";
import type { DailySummaryRow, Employee } from "@/types";
import { exportAttendanceSummary } from "@/utils/reportExports";
import type { ReportFormat } from "@/utils/reportExports";

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
  const [formatDialogOpen, setFormatDialogOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchRoster = useCallback(async () => {
    const [emps, summary] = await Promise.all([fetchEmployees(), fetchDailySummary(date)]);
    setEmployees(emps);
    setRows(
      summary.map((r) => ({
        ...r,
        is_absent: r.first_check_in == null && r.last_check_out == null,
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

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const handler = () => {
      void load();
    };
    window.addEventListener("biometrica:device-sync", handler);
    return () => {
      window.removeEventListener("biometrica:device-sync", handler);
    };
  }, [load]);

  const filtered = useMemo(() => {
    const q = globalSearchQuery.trim().toLowerCase();
    const list = q
      ? rows.filter(
          (r) =>
            r.employee_name.toLowerCase().includes(q) || String(r.device_user_id).toLowerCase().includes(q)
        )
      : rows;

    return [...list].sort((a, b) => {
      const aIn = a.first_check_in ? new Date(a.first_check_in).getTime() : null;
      const bIn = b.first_check_in ? new Date(b.first_check_in).getTime() : null;
      if (aIn != null && bIn != null) return aIn - bIn;
      if (aIn != null) return -1;
      if (bIn != null) return 1;

      const aOut = a.last_check_out ? new Date(a.last_check_out).getTime() : null;
      const bOut = b.last_check_out ? new Date(b.last_check_out).getTime() : null;
      if (aOut != null && bOut != null) return aOut - bOut;
      if (aOut != null) return -1;
      if (bOut != null) return 1;

      return a.employee_name.localeCompare(b.employee_name);
    });
  }, [rows, globalSearchQuery]);

  const presentCount = filtered.filter((r) => !r.is_absent).length;
  const absentCount = filtered.filter((r) => r.is_absent).length;

  const exportReport = useCallback(
    async (format: ReportFormat) => {
      setExporting(true);
      try {
        const range = getExportRange(date, exportPeriod);
        const dates = dateList(range.from, range.to);
        const byDay = await fetchDailySummaryRange(range.from, range.to);
        const allRows: Array<DailySummaryRow & { summary_date: string }> = [];
        for (const day of dates) {
          const summary = byDay[day] ?? [];
          for (const row of summary) {
            allRows.push({ ...row, summary_date: day });
          }
        }
        await exportAttendanceSummary(format, {
          periodLabel: range.label,
          rows: allRows,
        });
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to export report");
      } finally {
        setExporting(false);
      }
    },
    [date, exportPeriod]
  );

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-display-xl text-ink">Attendance</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
          Daily roster sorted by punch order.{" "}
          <span className="text-ink-subtle">
            Use the sidebar <strong>Sync now</strong> action to pull latest device punches. This page auto-updates
            after each successful sync.
          </span>
        </p>
      </header>

      <Card className="border-primary/10 bg-gradient-to-br from-primary-soft/40 via-surface-card to-surface-card">
        <CardContent className="flex flex-col gap-4 p-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="font-display text-display-lg text-ink">Export</h2>
            <p className="mt-1 max-w-xl text-sm text-ink-muted">
              Select date and period together, then download a report for audits and payroll handoff.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-xs font-medium text-ink-muted">Date</span>
              <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </label>
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
            <Button
              type="button"
              onClick={() => setFormatDialogOpen(true)}
              disabled={exporting}
              className="min-w-[140px]"
            >
              <Download className="h-4 w-4" />
              {exporting ? "Preparing…" : "Download"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <ReportFormatDialog
        open={formatDialogOpen}
        onOpenChange={setFormatDialogOpen}
        title="Download attendance report"
        description="Choose a format for the all-employee attendance summary."
        onSelect={(format) => void exportReport(format)}
        busy={exporting}
      />

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
        Absent today (in view): <span className="font-medium text-ink">{absentCount}</span>. Sorted by
        check-in time — earliest arrivals first.
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
                    <td className="px-5 py-3.5 whitespace-nowrap text-ink-muted">{fmtDisplayDateTime(r.first_check_in)}</td>
                    <td className="px-5 py-3.5 whitespace-nowrap text-ink-muted">{fmtDisplayDateTime(r.last_check_out)}</td>
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
