import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Download, FileSpreadsheet } from "lucide-react";
import { useMemo, useState } from "react";
import { AttendanceTrendChart } from "@/features/dashboard/components/AttendanceTrendChart";
import { WeeklyAttendanceChart } from "@/features/reports/components/WeeklyAttendanceChart";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useAttendanceTrend } from "@/features/attendance/hooks/useAttendanceTrend";
import type { ExportPeriod } from "@/lib/dates";
import { dateList, getExportRange, todayISO } from "@/lib/dates";
import { ReportFormatDialog } from "@/features/reports/components/ReportFormatDialog";
import { fetchDailySummaryRange } from "@/features/attendance/api";
import { fetchEmployees } from "@/features/employees/api";
import { useAuth } from "@/features/auth/AuthContext";
import { isOperatorAccount } from "@/features/auth/sessionCapabilities";
import type { DailySummaryRow } from "@/types";
import {
  downloadDepartmentAttendanceExcel,
  exportAttendanceSummary,
  type ReportFormat,
} from "@/features/reports/utils/reportExports";

export function Reports() {
  const { user } = useAuth();
  const godMode = isOperatorAccount(user);
  const [anchorDate, setAnchorDate] = useState(todayISO);
  const [period, setPeriod] = useState<ExportPeriod>("week");
  const [department, setDepartment] = useState("");
  const [formatDialogOpen, setFormatDialogOpen] = useState(false);
  const trend = useAttendanceTrend(14);

  const employeesQuery = useQuery({
    queryKey: ["employees"],
    queryFn: fetchEmployees,
    enabled: godMode,
  });

  const departments = useMemo(() => {
    const set = new Set<string>();
    for (const e of employeesQuery.data ?? []) {
      const d = e.department?.trim();
      if (d) set.add(d);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [employeesQuery.data]);

  const range = useMemo(() => getExportRange(anchorDate, period), [anchorDate, period]);

  const departmentMembers = useMemo(() => {
    if (!department) return [];
    return (employeesQuery.data ?? []).filter((e) => (e.department ?? "").trim() === department);
  }, [department, employeesQuery.data]);

  const summaryExportMutation = useMutation({
    mutationFn: async (format: ReportFormat) => {
      const dates = dateList(range.from, range.to);
      const byDay = await fetchDailySummaryRange(range.from, range.to);
      const allRows: Array<DailySummaryRow & { summary_date: string }> = [];
      for (const day of dates) {
        const summary = byDay[day] ?? [];
        for (const row of summary) {
          allRows.push({ ...row, summary_date: day });
        }
      }
      await exportAttendanceSummary(format, { periodLabel: range.label, rows: allRows });
    },
  });

  const departmentExportMutation = useMutation({
    mutationFn: async () => {
      if (!department) throw new Error("Select a department first.");
      if (departmentMembers.length === 0) {
        throw new Error(`No employees found in department “${department}”.`);
      }
      const dates = dateList(range.from, range.to);
      const byDay = await fetchDailySummaryRange(range.from, range.to);

      await downloadDepartmentAttendanceExcel({
        department,
        fromDate: range.from,
        toDate: range.to,
        members: departmentMembers.map((employee) => ({
          employee,
          days: dates.map((isoDate) => {
            const dayRows = byDay[isoDate] ?? [];
            const summary = dayRows.find((r) => r.employee_id === employee.id) ?? null;
            return { isoDate, summary };
          }),
        })),
      });
    },
  });

  const exportBusy = summaryExportMutation.isPending || departmentExportMutation.isPending;
  const exportError = departmentExportMutation.isError
    ? departmentExportMutation.error
    : summaryExportMutation.isError
      ? summaryExportMutation.error
      : null;

  function handleDownloadClick() {
    if (godMode && department) {
      departmentExportMutation.mutate();
      return;
    }
    setFormatDialogOpen(true);
  }

  return (
    <div className="space-y-10">
      <header>
        <h1 className="font-display text-display-xl text-ink">Reports</h1>
        <p className="mt-2 max-w-2xl text-sm text-ink-muted leading-relaxed">
          Export attendance packets and scan short-range summaries without leaving the console.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2 text-primary">
              <FileSpreadsheet className="h-5 w-5" strokeWidth={1.75} />
              <CardTitle>Report export</CardTitle>
            </div>
            <CardDescription>
              {godMode
                ? "Pick a department for a multi-sheet Excel pack, or leave it blank for the standard all-employee export."
                : "Roll up every employee across your chosen window into one document."}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-xs font-medium text-ink-muted">End date</span>
              <Input type="date" value={anchorDate} onChange={(e) => setAnchorDate(e.target.value)} />
            </label>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-xs font-medium text-ink-muted">Window</span>
              <select
                value={period}
                onChange={(e) => setPeriod(e.target.value as ExportPeriod)}
                className="h-10 rounded-xl border border-line bg-surface-card px-3 text-sm shadow-sm focus-visible:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/15"
              >
                <option value="day">Single day</option>
                <option value="week">Last 7 days</option>
                <option value="month">Last 30 days</option>
              </select>
            </label>
            {godMode ? (
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-xs font-medium text-ink-muted">Department</span>
                <select
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  className="h-10 rounded-xl border border-line bg-surface-card px-3 text-sm shadow-sm focus-visible:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/15"
                >
                  <option value="">All employees (standard export)</option>
                  {departments.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </select>
                {department ? (
                  <span className="text-xs text-ink-muted">
                    {departmentMembers.length} member{departmentMembers.length === 1 ? "" : "s"} · one sheet each
                  </span>
                ) : null}
              </label>
            ) : null}
            <p className="rounded-xl border border-line/80 bg-surface px-3 py-2 text-xs text-ink-muted leading-relaxed">
              {range.label}
            </p>
            <Button
              type="button"
              className="w-full sm:w-auto"
              onClick={handleDownloadClick}
              disabled={exportBusy || (godMode && Boolean(department) && departmentMembers.length === 0)}
            >
              <Download className="h-4 w-4" />
              {exportBusy
                ? "Preparing…"
                : godMode && department
                  ? "Download Excel"
                  : "Download"}
            </Button>
            {exportError ? (
              <p className="text-sm text-status-absent">
                {exportError instanceof Error ? exportError.message : "Export failed"}
              </p>
            ) : null}
          </CardContent>
        </Card>

        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
          <WeeklyAttendanceChart data={trend.data} loading={trend.isLoading} />
        </motion.div>
      </div>

      <ReportFormatDialog
        open={formatDialogOpen}
        onOpenChange={setFormatDialogOpen}
        title="Download attendance report"
        description="Choose a format for the all-employee attendance summary."
        onSelect={(format) => summaryExportMutation.mutate(format)}
        busy={summaryExportMutation.isPending}
      />

      <AttendanceTrendChart data={trend.data} loading={trend.isLoading} />
    </div>
  );
}
