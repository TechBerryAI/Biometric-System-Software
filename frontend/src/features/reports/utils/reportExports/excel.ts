import * as XLSX from "xlsx";
import {
  fmtDayOfWeek,
  fmtDisplayDate,
  fmtDisplayDateTime,
  fmtGeneratedTimestamp,
} from "@/lib/dates";
import type {
  AttendanceSummaryPayload,
  DashboardReportPayload,
  EmployeeReportPayload,
} from "./types";
import { fmtMinutes, mapRowsWithDaySeparators, safeFilename } from "./shared";

function writeWorkbook(workbook: XLSX.WorkBook, filename: string): void {
  XLSX.writeFile(workbook, filename);
}

export function downloadEmployeeReportExcel(args: EmployeeReportPayload): void {
  const { employee, rows, fromDate, toDate } = args;
  const workbook = XLSX.utils.book_new();

  const profileSheet = XLSX.utils.aoa_to_sheet([
    ["Employee attendance report"],
    ["Generated", fmtGeneratedTimestamp()],
    ["Period", `${fmtDisplayDate(fromDate)} → ${fmtDisplayDate(toDate)}`],
    ["Employee", employee.name],
    ["Device user ID", employee.device_user_id],
    [],
    ["Field", "Value"],
    ["Device UID", employee.device_uid ?? "—"],
    ["Department", employee.department ?? "—"],
    ["Privilege", employee.device_privilege ?? "—"],
    ["Device group", employee.device_group_id ?? "—"],
    ["Card", employee.device_card ?? "—"],
    ["Shift", `${employee.shift_start ?? "—"} → ${employee.shift_end ?? "—"}`],
    ["Total logs", employee.total_logs],
    ["Attendance days", employee.total_attendance_days],
    ["Complete days", employee.total_complete_days],
    ["First punch", fmtDisplayDateTime(employee.first_punch_at)],
    ["Last punch", fmtDisplayDateTime(employee.last_punch_at)],
  ]);
  XLSX.utils.book_append_sheet(workbook, profileSheet, "Profile");

  const attendanceSheet = XLSX.utils.aoa_to_sheet([
    ["Date", "Day", "In time", "Out time", "Total work (HH:mm)", "Absent", "Punches"],
    ...rows.map((r) => [
      fmtDisplayDate(r.summary_date),
      fmtDayOfWeek(r.summary_date),
      fmtDisplayDateTime(r.first_check_in),
      fmtDisplayDateTime(r.last_check_out),
      fmtMinutes(r.total_work_minutes),
      r.absent ? "Yes" : "No",
      r.punch_count,
    ]),
  ]);
  XLSX.utils.book_append_sheet(workbook, attendanceSheet, "Attendance");

  writeWorkbook(workbook, `employee_report_${safeFilename(employee.name)}_${toDate}.xlsx`);
}

export function downloadAttendanceSummaryExcel(args: AttendanceSummaryPayload): void {
  const { periodLabel, rows } = args;
  const workbook = XLSX.utils.book_new();

  const dataRows = mapRowsWithDaySeparators(rows, (r) => [
    fmtDisplayDate(r.summary_date),
    fmtDayOfWeek(r.summary_date),
    r.employee_name,
    r.device_user_id,
    fmtDisplayDateTime(r.first_check_in),
    fmtDisplayDateTime(r.last_check_out),
    fmtMinutes(r.total_work_minutes),
    r.first_check_in ? "No" : "Yes",
  ]);

  const sheet = XLSX.utils.aoa_to_sheet([
    ["Attendance summary · all employees"],
    ["Generated", fmtGeneratedTimestamp()],
    ["Coverage", periodLabel],
    ["Row count", rows.length],
    [],
    ["Date", "Day", "Employee", "Device ID", "In time", "Out time", "Total work", "Absent"],
    ...dataRows,
  ]);
  XLSX.utils.book_append_sheet(workbook, sheet, "Summary");

  writeWorkbook(workbook, `attendance_summary_${safeFilename(periodLabel)}.xlsx`);
}

export function downloadDashboardReportExcel(args: DashboardReportPayload): void {
  const { mode, dateRange, kpis, deptMatrix, radar } = args;
  const workbook = XLSX.utils.book_new();

  const kpiSheet = XLSX.utils.aoa_to_sheet([
    ["Workforce intelligence report"],
    ["Generated", fmtGeneratedTimestamp()],
    ["Mode", mode],
    ["Date range", dateRange],
    [],
    ["KPI", "Value", "Trend", "Comparison", "Insight"],
    ...kpis.map((k) => [k.title, k.value, k.trend, k.comparison, k.insight]),
  ]);
  XLSX.utils.book_append_sheet(workbook, kpiSheet, "KPIs");

  const deptSheet = XLSX.utils.aoa_to_sheet([
    ["Rank", "Department", "Attendance %", "Punctuality %", "Avg hours", "Overtime %", "Absentee risk", "Productivity"],
    ...deptMatrix.map((d) => [
      d.rank,
      d.department,
      Number(d.attendance.toFixed(1)),
      Number(d.punctuality.toFixed(1)),
      Number(d.avgHours.toFixed(2)),
      Number(d.overtimePct.toFixed(1)),
      Number(d.absenteeRisk.toFixed(1)),
      Number(d.productivity.toFixed(1)),
    ]),
  ]);
  XLSX.utils.book_append_sheet(workbook, deptSheet, "Departments");

  const radarSheet = XLSX.utils.aoa_to_sheet([
    ["Metric", "Score"],
    ...radar.map((r) => [r.metric, Number(r.score.toFixed(1))]),
  ]);
  XLSX.utils.book_append_sheet(workbook, radarSheet, "Radar");

  writeWorkbook(workbook, `workforce-intelligence_${safeFilename(mode)}_${Date.now()}.xlsx`);
}
