import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { ArrowLeft, Download, UserMinus } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "@/features/auth/AuthContext";
import { hasCapability } from "@/features/auth/sessionCapabilities";
import {
  AttendanceAdjustmentModal,
  AttendanceRowEditButton,
} from "@/features/attendance/components/AttendanceAdjustmentPanel";
import { EmployeeAvatar } from "@/features/employees/components/EmployeeAvatar";
import { OffboardEmployeeDialog } from "@/features/employees/components/OffboardEmployeeDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import {
  clampDateRange,
  fmtDayOfWeek,
  fmtDisplayDate,
  fmtDisplayDateTime,
  todayISO,
} from "@/lib/dates";
import { fetchEmployeeById, fetchEmployeeDailyAttendance, offboardEmployee } from "@/features/employees/api";
import { ReportFormatDialog } from "@/features/reports/components/ReportFormatDialog";
import type { EmployeeDailyAttendance, EmployeeDetail } from "@/types";
import { exportEmployeeReport, type ReportFormat } from "@/features/reports/utils/reportExports";

function fmtMinutes(total: number | null): string {
  if (total == null) return "—";
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

type TabId = "profile" | "attendance";

export function EmployeeProfile() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const navigate = useNavigate();
  const { user, can } = useAuth();
  const canEditEmployees = can("employee:edit");
  const canAdjustAttendance = hasCapability(user, "attendance_adjust");
  const numericEmployeeId = Number(employeeId);

  const [tab, setTab] = useState<TabId>("profile");
  const [employee, setEmployee] = useState<EmployeeDetail | null>(null);
  const [rows, setRows] = useState<EmployeeDailyAttendance[]>([]);
  const [fromDate, setFromDate] = useState(defaultFromDate);
  const [toDate, setToDate] = useState(todayISO);
  const [loadingEmployee, setLoadingEmployee] = useState(true);
  const [loadingAttendance, setLoadingAttendance] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [correctionRow, setCorrectionRow] = useState<EmployeeDailyAttendance | null>(null);
  const [correctionOpen, setCorrectionOpen] = useState(false);
  const [formatDialogOpen, setFormatDialogOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [offboardOpen, setOffboardOpen] = useState(false);

  const openCorrection = useCallback((row: EmployeeDailyAttendance) => {
    setCorrectionRow(row);
    setCorrectionOpen(true);
  }, []);

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
    if (fromDate > toDate) {
      setError("'From' date must be on or before 'To' date.");
      return;
    }
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
    const absent = rows.filter((r) => r.absent).length;
    return { present, absent };
  }, [rows]);

  const handleExport = useCallback(
    async (format: ReportFormat) => {
      if (!employee) return;
      setExporting(true);
      try {
        await exportEmployeeReport(format, { employee, rows, fromDate, toDate });
      } finally {
        setExporting(false);
      }
    },
    [employee, rows, fromDate, toDate]
  );

  if (!Number.isFinite(numericEmployeeId)) {
    return (
      <Card className="border-status-absent-soft bg-status-absent-soft/25">
        <CardContent className="p-6 text-sm text-status-absent">Invalid employee id in URL.</CardContent>
      </Card>
    );
  }

  if (loadingEmployee && employee == null) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-48 w-full rounded-2xl" />
      </div>
    );
  }

  if (error && employee == null) {
    return (
      <Card className="border-status-absent-soft bg-status-absent-soft/25">
        <CardContent className="p-6">
          <p className="text-sm text-status-absent">{error}</p>
          <Button className="mt-4" variant="secondary" asChild>
            <Link to="/employees">Back</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-start gap-4">
          {employee ? <EmployeeAvatar name={employee.name} id={employee.id} size="md" /> : null}
          <div>
            <Button variant="ghost" size="sm" className="-ml-2 mb-1 h-8 gap-1 px-2 text-ink-muted" asChild>
              <Link to="/employees">
                <ArrowLeft className="h-4 w-4" />
                Employees
              </Link>
            </Button>
            <h1 className="font-display text-display-xl text-ink">{employee?.name ?? "Employee"}</h1>
            <p className="mt-1 text-sm text-ink-muted">
              Device{" "}
              <span className="rounded-lg bg-primary-soft px-2 py-0.5 font-mono text-xs text-primary">
                {employee?.device_user_id ?? "—"}
              </span>
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {canEditEmployees && employee ? (
            <Button type="button" variant="destructive" onClick={() => setOffboardOpen(true)}>
              <UserMinus className="h-4 w-4" />
              Offboard
            </Button>
          ) : null}
          <Button
            type="button"
            variant="secondary"
            onClick={() => setFormatDialogOpen(true)}
            disabled={!employee || exporting}
          >
            <Download className="h-4 w-4" />
            {exporting ? "Preparing…" : "Download"}
          </Button>
        </div>
      </div>

      <ReportFormatDialog
        open={formatDialogOpen}
        onOpenChange={setFormatDialogOpen}
        title="Download employee report"
        description="Choose a format for this employee's attendance report."
        onSelect={(format) => void handleExport(format)}
        busy={exporting}
      />

      {employee ? (
        <OffboardEmployeeDialog
          open={offboardOpen}
          onOpenChange={setOffboardOpen}
          employeeName={employee.name}
          deviceUserId={employee.device_user_id}
          onConfirm={async () => {
            await offboardEmployee(employee.id);
            navigate("/employees");
          }}
        />
      ) : null}

      <div className="inline-flex rounded-2xl border border-line/80 bg-surface-card p-1 shadow-sm">
        {(
          [
            ["profile", "Profile"] as const,
            ["attendance", "Attendance"] as const,
          ] as const
        ).map(([k, label]) => (
          <button
            key={k}
            type="button"
            onClick={() => setTab(k)}
            className={cn(
              "rounded-xl px-4 py-2 text-sm font-medium transition-all duration-200",
              tab === k
                ? "bg-primary-soft text-primary shadow-sm"
                : "text-ink-muted hover:text-ink hover:bg-surface/80"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "profile" ? (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {[
              { t: "Total logs", v: employee?.total_logs ?? 0 },
              { t: "Attendance days", v: employee?.total_attendance_days ?? 0 },
              { t: "Complete days", v: employee?.total_complete_days ?? 0 },
            ].map((x, i) => (
              <motion.div
                key={x.t}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.04 }}
              >
                <Card className="transition-shadow hover:shadow-card-hover">
                  <CardContent className="p-5">
                    <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">{x.t}</p>
                    <p className="mt-2 font-display text-2xl font-semibold text-ink tabular-nums">{x.v}</p>
                  </CardContent>
                </Card>
              </motion.div>
            ))}
            <Card className="sm:col-span-2 lg:col-span-1">
              <CardContent className="p-5">
                <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">First punch</p>
                <p className="mt-2 text-sm font-medium text-ink leading-snug">
                  {fmtDisplayDateTime(employee?.first_punch_at ?? null)}
                </p>
              </CardContent>
            </Card>
            <Card className="sm:col-span-2 lg:col-span-1">
              <CardContent className="p-5">
                <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">Last punch</p>
                <p className="mt-2 text-sm font-medium text-ink leading-snug">
                  {fmtDisplayDateTime(employee?.last_punch_at ?? null)}
                </p>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Employee details</CardTitle>
            </CardHeader>
            <CardContent>
              <dl className="grid gap-6 sm:grid-cols-2">
                {[
                  ["Employee ID", String(employee?.id ?? "—")],
                  ["Name", employee?.name ?? "—"],
                  ["Device user ID", employee?.device_user_id ?? "—"],
                  ["Device UID", String(employee?.device_uid ?? "—")],
                  ["Privilege", String(employee?.device_privilege ?? "—")],
                  ["Group ID", employee?.device_group_id ?? "—"],
                  ["Card", employee?.device_card ?? "—"],
                  ["Department", employee?.department ?? "—"],
                  ["Shift start", employee?.shift_start ?? "—"],
                  ["Shift end", employee?.shift_end ?? "—"],
                ].map(([dt, dd]) => (
                  <div key={dt}>
                    <dt className="text-xs font-medium uppercase tracking-wider text-ink-muted">{dt}</dt>
                    <dd className="mt-1 text-sm text-ink">{dd}</dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
        </div>
      ) : (
        <div className="space-y-6">
          <Card>
            <CardContent className="flex flex-col gap-4 p-6 sm:flex-row sm:flex-wrap sm:items-end">
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-xs font-medium text-ink-muted">From</span>
                <Input
                  type="date"
                  value={fromDate}
                  onChange={(e) => {
                    const next = clampDateRange(e.target.value, toDate);
                    setFromDate(next.from);
                    setToDate(next.to);
                  }}
                />
              </label>
              <label className="flex flex-col gap-1.5 text-sm">
                <span className="text-xs font-medium text-ink-muted">To</span>
                <Input
                  type="date"
                  value={toDate}
                  onChange={(e) => {
                    const next = clampDateRange(fromDate, e.target.value);
                    setFromDate(next.from);
                    setToDate(next.to);
                  }}
                />
              </label>
              <Button
                type="button"
                variant="secondary"
                onClick={() => void loadAttendance()}
                disabled={loadingAttendance}
              >
                {loadingAttendance ? "Loading…" : "Refresh"}
              </Button>
            </CardContent>
          </Card>

          <div className="grid gap-4 sm:grid-cols-2">
            {[
              { label: "Present days", value: stats.present },
              { label: "Absent days", value: stats.absent },
            ].map((s) => (
              <Card key={s.label}>
                <CardContent className="p-5">
                  <p className="text-xs font-medium uppercase tracking-wider text-ink-muted">{s.label}</p>
                  <p className="mt-2 font-display text-2xl font-semibold text-ink tabular-nums">{s.value}</p>
                </CardContent>
              </Card>
            ))}
          </div>

          {error ? (
            <Card className="border-status-absent-soft bg-status-absent-soft/25">
              <CardContent className="p-4 text-sm text-status-absent">{error}</CardContent>
            </Card>
          ) : null}

          <div className="overflow-hidden rounded-2xl border border-line/70 bg-surface-card shadow-card">
            <div className="scrollbar-thin overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="sticky top-0 z-[1] bg-surface/95 backdrop-blur-sm">
                  <tr className="text-xs font-medium uppercase tracking-wider text-ink-muted shadow-[inset_0_-1px_0_#E2E8F0]">
                    <th className="px-5 py-3.5">Date</th>
                    <th className="px-5 py-3.5">Day</th>
                    <th className="px-5 py-3.5">In</th>
                    <th className="px-5 py-3.5">Out</th>
                    <th className="px-5 py-3.5">Work</th>
                    <th className="px-5 py-3.5">Punches</th>
                    {canAdjustAttendance ? <th className="px-5 py-3.5">Actions</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 ? (
                    <tr>
                      <td colSpan={canAdjustAttendance ? 7 : 6} className="px-5 py-14 text-center text-ink-muted">
                        No rows in this range.
                      </td>
                    </tr>
                  ) : (
                    rows.map((r, idx) => (
                      <tr
                        key={r.summary_date}
                        role={canAdjustAttendance ? "button" : undefined}
                        tabIndex={canAdjustAttendance ? 0 : undefined}
                        onClick={() => {
                          if (canAdjustAttendance) openCorrection(r);
                        }}
                        onKeyDown={(e) => {
                          if (canAdjustAttendance && (e.key === "Enter" || e.key === " ")) {
                            e.preventDefault();
                            openCorrection(r);
                          }
                        }}
                        className={cn(
                          "border-b border-line/40 transition-colors",
                          idx % 2 === 1 && "bg-surface/[0.35]",
                          canAdjustAttendance &&
                            "cursor-pointer hover:bg-primary-soft/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary/30"
                        )}
                      >
                        <td className="px-5 py-3.5">{fmtDisplayDate(r.summary_date)}</td>
                        <td className="px-5 py-3.5 text-ink-muted">{fmtDayOfWeek(r.summary_date)}</td>
                        <td className="px-5 py-3.5 whitespace-nowrap text-ink-muted">
                          {fmtDisplayDateTime(r.first_check_in)}
                        </td>
                        <td className="px-5 py-3.5 whitespace-nowrap text-ink-muted">
                          {fmtDisplayDateTime(r.last_check_out)}
                        </td>
                        <td className="px-5 py-3.5 tabular-nums text-ink-muted">
                          {fmtMinutes(r.total_work_minutes)}
                        </td>
                        <td className="px-5 py-3.5 tabular-nums text-ink-muted">{r.punch_count}</td>
                        {canAdjustAttendance ? (
                          <td className="px-5 py-3.5">
                            <AttendanceRowEditButton onClick={() => openCorrection(r)} />
                          </td>
                        ) : null}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {canAdjustAttendance ? (
            <AttendanceAdjustmentModal
              open={correctionOpen}
              onOpenChange={setCorrectionOpen}
              employeeId={numericEmployeeId}
              row={correctionRow}
              onApplied={() => {
                void loadAttendance();
                void loadEmployee();
              }}
            />
          ) : null}
        </div>
      )}
    </div>
  );
}
