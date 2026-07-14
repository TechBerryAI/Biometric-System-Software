import {
  downloadAttendanceSummaryExcel,
  downloadDashboardReportExcel,
  downloadEmployeeReportExcel,
} from "./excel";
import {
  downloadAttendanceSummaryPdf,
  downloadDashboardReportPdf,
  downloadEmployeeReportPdf,
} from "./pdf";
import type {
  AttendanceSummaryPayload,
  DashboardReportPayload,
  EmployeeReportPayload,
  ReportFormat,
} from "./types";
import {
  downloadAttendanceSummaryWord,
  downloadDashboardReportWord,
  downloadEmployeeReportWord,
} from "./word";

export type {
  AttendanceSummaryPayload,
  DashboardDeptRow,
  DashboardKpiExport,
  DashboardRadarRow,
  DashboardReportPayload,
  EmployeeReportPayload,
  ReportFormat,
} from "./types";

export function exportEmployeeReport(format: ReportFormat, args: EmployeeReportPayload): void | Promise<void> {
  if (format === "pdf") {
    downloadEmployeeReportPdf(args);
    return;
  }
  if (format === "excel") {
    downloadEmployeeReportExcel(args);
    return;
  }
  return downloadEmployeeReportWord(args);
}

export function exportAttendanceSummary(
  format: ReportFormat,
  args: AttendanceSummaryPayload
): void | Promise<void> {
  if (format === "pdf") {
    downloadAttendanceSummaryPdf(args);
    return;
  }
  if (format === "excel") {
    downloadAttendanceSummaryExcel(args);
    return;
  }
  return downloadAttendanceSummaryWord(args);
}

export function exportDashboardReport(
  format: ReportFormat,
  args: DashboardReportPayload
): void | Promise<void> {
  if (format === "pdf") {
    downloadDashboardReportPdf(args);
    return;
  }
  if (format === "excel") {
    downloadDashboardReportExcel(args);
    return;
  }
  return downloadDashboardReportWord(args);
}

/** @deprecated Use exportEmployeeReport("pdf", ...) */
export { downloadEmployeeReportPdf } from "./pdf";

/** @deprecated Use exportAttendanceSummary("pdf", ...) */
export { downloadAttendanceSummaryPdf } from "./pdf";
