import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
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
import { fmtMinutes, safeFilename } from "./shared";

const ACCENT: [number, number, number] = [13, 148, 136];
const ACCENT_DARK: [number, number, number] = [15, 118, 110];
const SLATE_HEADER: [number, number, number] = [26, 34, 48];
const SLATE_MUTED: [number, number, number] = [61, 79, 102];
const ROW_ALT: [number, number, number] = [248, 250, 252];

function getPageWidth(doc: jsPDF): number {
  return doc.internal.pageSize.getWidth();
}

function drawReportBanner(doc: jsPDF, title: string, metaLines: string[]): number {
  const w = getPageWidth(doc);
  const bandH = 78;
  doc.setFillColor(...ACCENT);
  doc.rect(0, 0, w, bandH, "F");
  doc.setDrawColor(...ACCENT_DARK);
  doc.setLineWidth(1);
  doc.line(0, bandH, w, bandH);

  doc.setTextColor(255, 255, 255);
  doc.setFont("helvetica", "bold");
  doc.setFontSize(20);
  doc.text(title, 40, 38);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(10);
  let y = 56;
  for (const line of metaLines) {
    doc.text(line, 40, y);
    y += 14;
  }
  doc.setTextColor(0, 0, 0);
  return bandH + 24;
}

function tableFooter(doc: jsPDF, label: string): void {
  const pageCount = doc.getNumberOfPages();
  for (let i = 1; i <= pageCount; i++) {
    doc.setPage(i);
    const w = getPageWidth(doc);
    const h = doc.internal.pageSize.getHeight();
    doc.setFontSize(8);
    doc.setTextColor(...SLATE_MUTED);
    doc.setDrawColor(230, 235, 241);
    doc.line(40, h - 28, w - 40, h - 28);
    doc.text(`${label} · Page ${i} of ${pageCount}`, 40, h - 16);
    doc.setTextColor(0, 0, 0);
  }
}

function getLastTableY(doc: jsPDF, fallback: number): number {
  return ((doc as jsPDF & { lastAutoTable?: { finalY?: number } }).lastAutoTable?.finalY ?? fallback) + 18;
}

export function downloadEmployeeReportPdf(args: EmployeeReportPayload): void {
  const { employee, rows, fromDate, toDate } = args;
  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });

  const startY = drawReportBanner(doc, "Employee attendance report", [
    `Generated · ${fmtGeneratedTimestamp()}`,
    `Period · ${fmtDisplayDate(fromDate)} → ${fmtDisplayDate(toDate)} · ${employee.name} (${employee.device_user_id})`,
  ]);

  autoTable(doc, {
    startY,
    theme: "plain",
    head: [["Field", "Value", "Field", "Value"]],
    body: [
      ["Employee", employee.name, "Device user ID", employee.device_user_id],
      ["Device UID", String(employee.device_uid ?? "—"), "Department", employee.department ?? "—"],
      ["Privilege", String(employee.device_privilege ?? "—"), "Device group", employee.device_group_id ?? "—"],
      ["Card", employee.device_card ?? "—", "Shift", `${employee.shift_start ?? "—"} → ${employee.shift_end ?? "—"}`],
      ["Total logs", String(employee.total_logs), "Attendance days", String(employee.total_attendance_days)],
      ["Complete days", String(employee.total_complete_days), "First punch", fmtDisplayDateTime(employee.first_punch_at)],
      ["Last punch", fmtDisplayDateTime(employee.last_punch_at), "", ""],
    ],
    styles: {
      fontSize: 9.5,
      cellPadding: { top: 7, bottom: 7, left: 8, right: 8 },
      lineColor: [226, 232, 240],
      lineWidth: 0.5,
    },
    headStyles: {
      fillColor: SLATE_HEADER,
      textColor: [255, 255, 255],
      fontStyle: "bold",
      halign: "left",
    },
    columnStyles: {
      0: { fontStyle: "bold", cellWidth: 100, textColor: SLATE_MUTED },
      2: { fontStyle: "bold", cellWidth: 100, textColor: SLATE_MUTED },
    },
  });

  const yAfter = getLastTableY(doc, startY);

  doc.setFontSize(11);
  doc.setTextColor(...SLATE_HEADER);
  doc.setFont("helvetica", "bold");
  doc.text("Daily attendance detail", 40, yAfter);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(0, 0, 0);

  autoTable(doc, {
    startY: yAfter + 8,
    theme: "striped",
    head: [["Date", "Day", "In time", "Out time", "Total work (HH:mm)", "Absent", "Punches"]],
    body: rows.map((r) => [
      fmtDisplayDate(r.summary_date),
      fmtDayOfWeek(r.summary_date),
      fmtDisplayDateTime(r.first_check_in),
      fmtDisplayDateTime(r.last_check_out),
      fmtMinutes(r.total_work_minutes),
      r.absent ? "Yes" : "No",
      String(r.punch_count),
    ]),
    styles: {
      fontSize: 9,
      cellPadding: 6,
      lineColor: [226, 232, 240],
      valign: "middle",
    },
    headStyles: {
      fillColor: ACCENT,
      textColor: [255, 255, 255],
      fontStyle: "bold",
    },
    alternateRowStyles: { fillColor: ROW_ALT },
    columnStyles: {
      0: { cellWidth: 72 },
      4: { halign: "center" },
      5: { halign: "center" },
      6: { halign: "center", cellWidth: 52 },
    },
    margin: { left: 40, right: 40 },
  });

  tableFooter(doc, "Biometric attendance · read-only shadow report");
  doc.save(`employee_report_${safeFilename(employee.name)}_${toDate}.pdf`);
}

export function downloadAttendanceSummaryPdf(args: AttendanceSummaryPayload): void {
  const { periodLabel, rows } = args;
  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });

  const startY = drawReportBanner(doc, "Attendance summary · all employees", [
    `Generated · ${fmtGeneratedTimestamp()}`,
    `Coverage · ${periodLabel} · ${rows.length} row(s)`,
  ]);

  autoTable(doc, {
    startY,
    theme: "striped",
    head: [["Date", "Day", "Employee", "Device ID", "In time", "Out time", "Total work", "Absent"]],
    body: rows.map((r) => [
      fmtDisplayDate(r.summary_date),
      fmtDayOfWeek(r.summary_date),
      r.employee_name,
      r.device_user_id,
      fmtDisplayDateTime(r.first_check_in),
      fmtDisplayDateTime(r.last_check_out),
      fmtMinutes(r.total_work_minutes),
      r.first_check_in ? "No" : "Yes",
    ]),
    styles: {
      fontSize: 8.5,
      cellPadding: { top: 5, bottom: 5, left: 6, right: 6 },
      lineColor: [226, 232, 240],
      valign: "middle",
    },
    headStyles: {
      fillColor: SLATE_HEADER,
      textColor: [255, 255, 255],
      fontStyle: "bold",
    },
    alternateRowStyles: { fillColor: ROW_ALT },
    columnStyles: {
      0: { cellWidth: 72 },
      3: { cellWidth: 72 },
      6: { halign: "center", cellWidth: 64 },
      7: { halign: "center", cellWidth: 52 },
    },
    margin: { left: 40, right: 40 },
  });

  tableFooter(doc, "Biometric attendance · read-only shadow report");
  doc.save(`attendance_summary_${safeFilename(periodLabel)}.pdf`);
}

export function downloadDashboardReportPdf(args: DashboardReportPayload): void {
  const { mode, dateRange, kpis, deptMatrix, radar } = args;
  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });

  let startY = drawReportBanner(doc, "Workforce intelligence report", [
    `Generated · ${fmtGeneratedTimestamp()}`,
    `Mode · ${mode} · Range · ${dateRange}`,
  ]);

  autoTable(doc, {
    startY,
    theme: "striped",
    head: [["KPI", "Value", "Trend", "Comparison", "Insight"]],
    body: kpis.map((k) => [k.title, k.value, k.trend, k.comparison, k.insight]),
    styles: { fontSize: 8, cellPadding: 5, valign: "middle" },
    headStyles: { fillColor: SLATE_HEADER, textColor: [255, 255, 255], fontStyle: "bold" },
    alternateRowStyles: { fillColor: ROW_ALT },
    margin: { left: 40, right: 40 },
  });

  startY = getLastTableY(doc, startY);
  doc.setFontSize(11);
  doc.setFont("helvetica", "bold");
  doc.text("Department matrix", 40, startY);

  autoTable(doc, {
    startY: startY + 8,
    theme: "striped",
    head: [["Rank", "Department", "Attendance %", "Punctuality %", "Avg hours", "Overtime %", "Absentee risk", "Productivity"]],
    body: deptMatrix.map((d) => [
      String(d.rank),
      d.department,
      d.attendance.toFixed(1),
      d.punctuality.toFixed(1),
      d.avgHours.toFixed(2),
      d.overtimePct.toFixed(1),
      d.absenteeRisk.toFixed(1),
      d.productivity.toFixed(1),
    ]),
    styles: { fontSize: 8, cellPadding: 5, valign: "middle" },
    headStyles: { fillColor: ACCENT, textColor: [255, 255, 255], fontStyle: "bold" },
    alternateRowStyles: { fillColor: ROW_ALT },
    margin: { left: 40, right: 40 },
  });

  startY = getLastTableY(doc, startY);
  doc.setFontSize(11);
  doc.setFont("helvetica", "bold");
  doc.text("Radar scores", 40, startY);

  autoTable(doc, {
    startY: startY + 8,
    theme: "striped",
    head: [["Metric", "Score"]],
    body: radar.map((r) => [r.metric, r.score.toFixed(1)]),
    styles: { fontSize: 9, cellPadding: 6, valign: "middle" },
    headStyles: { fillColor: SLATE_HEADER, textColor: [255, 255, 255], fontStyle: "bold" },
    alternateRowStyles: { fillColor: ROW_ALT },
    margin: { left: 40, right: 40 },
  });

  tableFooter(doc, "Biometric workforce intelligence");
  doc.save(`workforce-intelligence_${safeFilename(mode)}_${Date.now()}.pdf`);
}
