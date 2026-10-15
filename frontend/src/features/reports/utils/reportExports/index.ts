/**
 * Report export entry points.
 *
 * exceljs, jspdf, docx and xlsx add up to several MB, so each format's implementation is loaded on
 * demand when the user exports instead of shipping with the Dashboard / Attendance / Reports pages.
 */
import type { DepartmentAttendancePayload } from "./departmentAttendanceExcel";
import type {
  AttendanceSummaryPayload,
  DashboardReportPayload,
  EmployeeReportPayload,
  ReportFormat,
} from "./types";

export type {
  DepartmentAttendanceDay,
  DepartmentAttendanceMember,
  DepartmentAttendancePayload,
} from "./departmentAttendanceExcel";

export type {
  AttendanceSummaryPayload,
  DashboardDeptRow,
  DashboardKpiExport,
  DashboardRadarRow,
  DashboardReportPayload,
  EmployeeReportPayload,
  ReportFormat,
} from "./types";

export async function downloadDepartmentAttendanceExcel(args: DepartmentAttendancePayload): Promise<void> {
  const { downloadDepartmentAttendanceExcel: download } = await import("./departmentAttendanceExcel");
  return download(args);
}

export async function exportEmployeeReport(format: ReportFormat, args: EmployeeReportPayload): Promise<void> {
  if (format === "pdf") return (await import("./pdf")).downloadEmployeeReportPdf(args);
  if (format === "excel") return (await import("./excel")).downloadEmployeeReportExcel(args);
  return (await import("./word")).downloadEmployeeReportWord(args);
}

export async function exportAttendanceSummary(format: ReportFormat, args: AttendanceSummaryPayload): Promise<void> {
  if (format === "pdf") return (await import("./pdf")).downloadAttendanceSummaryPdf(args);
  if (format === "excel") return (await import("./attendanceMatrixExcel")).downloadAttendanceMatrixExcel(args);
  return (await import("./word")).downloadAttendanceSummaryWord(args);
}

export async function exportDashboardReport(format: ReportFormat, args: DashboardReportPayload): Promise<void> {
  if (format === "pdf") return (await import("./pdf")).downloadDashboardReportPdf(args);
  if (format === "excel") return (await import("./excel")).downloadDashboardReportExcel(args);
  return (await import("./word")).downloadDashboardReportWord(args);
}

/** @deprecated Use exportEmployeeReport("pdf", ...) */
export async function downloadEmployeeReportPdf(args: EmployeeReportPayload): Promise<void> {
  return (await import("./pdf")).downloadEmployeeReportPdf(args);
}

/** @deprecated Use exportAttendanceSummary("pdf", ...) */
export async function downloadAttendanceSummaryPdf(args: AttendanceSummaryPayload): Promise<void> {
  return (await import("./pdf")).downloadAttendanceSummaryPdf(args);
}
