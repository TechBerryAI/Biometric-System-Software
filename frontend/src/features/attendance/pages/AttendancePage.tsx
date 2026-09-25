import { motion } from "framer-motion";
import { ArrowUpDown, Download } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { DayPunchesDialog } from "@/features/attendance/components/DayPunchesDialog";
import { cn } from "@/lib/cn";
import { fmtDisplayDateTime, getExportRange, todayISO } from "@/lib/dates";
import { fetchDailySummary } from "@/features/attendance/api";
import {
  ATTENDANCE_SORT_LABELS,
  sortAttendanceRows,
  type AttendanceSortMode,
} from "@/features/attendance/sortAttendance";
import { fetchEmployees } from "@/features/employees/api";
import { getApiErrorMessage } from "@/shared/api/client";
import { useUiStore } from "@/stores/ui-store";
import { ReportFormatDialog } from "@/features/reports/components/ReportFormatDialog";
import type { DailySummaryRow, Employee } from "@/types";
import { exportAttendanceSummary } from "@/features/reports/utils/reportExports";
import type { ReportFormat } from "@/features/reports/utils/reportExports";

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
  const [sortMode, setSortMode] = useState<AttendanceSortMode>("early_first");
  const [exporting, setExporting] = useState(false);
  const [formatDialogOpen, setFormatDialogOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [punchesOpen, setPunchesOpen] = useState(false);
  const [punchesEmployee, setPunchesEmployee] = useState<AttendanceRow | null>(null);

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

    return sortAttendanceRows(list, sortMode);
  }, [rows, globalSearchQuery, sortMode]);

  const presentCount = filtered.filter((r) => !r.is_absent).length;
  const absentCount = filtered.filter((r) => r.is_absent).length;

  const exportReport = useCallback(
    async (format: ReportFormat) => {
      setExporting(true);
      try {
        const range = getExportRange(date, "day");
        const summary = await fetchDailySummary(date);
        const dayRows = summary.map((row) => ({ ...row, summary_date: date }));
        await exportAttendanceSummary(format, {
          periodLabel: range.label,
          rows: sortAttendanceRows(dayRows, sortMode),
          fromDate: date,
          toDate: date,
        });
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Failed to export report");
      } finally {
        setExporting(false);
      }
    },
    [date, sortMode]
  );

  return (
    <div className="space-y-8">
      <header>
        <h1 className="font-display text-display-xl text-ink">Attendance</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
          Daily roster with present employees sorted by your chosen order; absents always list last.{" "}
          <span className="text-ink-subtle">
            Use the sidebar <strong>Sync now</strong> action to pull all punches still stored on the terminal. This page auto-updates
            after each successful sync.
          </span>
        </p>
      </header>

      <Card className="border-primary/10 bg-gradient-to-br from-primary-soft/40 via-surface-card to-surface-card">
        <CardContent className="flex flex-col gap-4 p-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="font-display text-display-lg text-ink">Export</h2>
            <p className="mt-1 max-w-xl text-sm text-ink-muted">
              Download this day&apos;s roster for audits and payroll handoff. Use Reports for multi-day ranges.
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-xs font-medium text-ink-muted">Date</span>
              <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
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

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs text-ink-muted">
          Absent today (in view): <span className="font-medium text-ink">{absentCount}</span>. Sorted by{" "}
          <span className="font-medium text-ink">{ATTENDANCE_SORT_LABELS[sortMode].toLowerCase()}</span>
          {loading ? "…" : ""} — absents listed last. Exports use the same order.
        </p>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="secondary" size="sm" className="shrink-0 self-start sm:self-auto">
              <ArrowUpDown className="h-4 w-4" />
              Sort: {ATTENDANCE_SORT_LABELS[sortMode]}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-48">
            <DropdownMenuRadioGroup
              value={sortMode}
              onValueChange={(value) => setSortMode(value as AttendanceSortMode)}
            >
              {(Object.keys(ATTENDANCE_SORT_LABELS) as AttendanceSortMode[]).map((mode) => (
                <DropdownMenuRadioItem key={mode} value={mode}>
                  {ATTENDANCE_SORT_LABELS[mode]}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

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
                      <button
                        type="button"
                        className="text-left transition hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/25 rounded"
                        onClick={() => {
                          setPunchesEmployee(r);
                          setPunchesOpen(true);
                        }}
                      >
                        <p className="font-medium text-ink hover:underline underline-offset-2">{r.employee_name}</p>
                        <p className="text-xs text-ink-muted font-mono">{r.device_user_id}</p>
                      </button>
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

      <DayPunchesDialog
        open={punchesOpen}
        onOpenChange={setPunchesOpen}
        employeeId={punchesEmployee?.employee_id ?? null}
        employeeName={punchesEmployee?.employee_name ?? "Employee"}
        date={date}
      />
    </div>
  );
}
