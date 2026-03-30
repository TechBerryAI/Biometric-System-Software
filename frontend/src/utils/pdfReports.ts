import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import type { DailySummaryRow, EmployeeDailyAttendance, EmployeeDetail } from "@/types";

/** Brand teal (matches Tailwind accent) */
const ACCENT: [number, number, number] = [13, 148, 136];
const ACCENT_DARK: [number, number, number] = [15, 118, 110];
const SLATE_HEADER: [number, number, number] = [26, 34, 48];
const SLATE_MUTED: [number, number, number] = [61, 79, 102];
const ROW_ALT: [number, number, number] = [248, 250, 252];

function fmtDateTime(value: string | null): string {
  if (!value) return "—";
  try {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  } catch {
    return new Date(value).toLocaleString();
  }
}

function fmtDate(value: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
      new Date(`${value}T12:00:00`)
    );
  } catch {
    return new Date(`${value}T00:00:00`).toLocaleDateString();
  }
}

function fmtMinutes(total: number | null): string {
  if (total == null) return "—";
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function safeFilename(value: string): string {
  return value.replace(/[^a-z0-9]+/gi, "_").replace(/^_+|_+$/g, "").toLowerCase();
}

function getPageWidth(doc: jsPDF): number {
  return doc.internal.pageSize.getWidth();
}

/** Teal header band + title (landscape A4 ~842pt wide) */
function drawReportBanner(
  doc: jsPDF,
  title: string,
  metaLines: string[]
): number {
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

export function downloadEmployeeReportPdf(args: {
  employee: EmployeeDetail;
  rows: EmployeeDailyAttendance[];
  fromDate: string;
  toDate: string;
}): void {
  const { employee, rows, fromDate, toDate } = args;
  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });

  const startY = drawReportBanner(doc, "Employee attendance report", [
    `Generated · ${new Intl.DateTimeFormat(undefined, { dateStyle: "long", timeStyle: "short" }).format(new Date())}`,
    `Period · ${fmtDate(fromDate)} → ${fmtDate(toDate)} · ${employee.name} (${employee.device_user_id})`,
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
      ["Complete days", String(employee.total_complete_days), "First punch", fmtDateTime(employee.first_punch_at)],
      ["Last punch", fmtDateTime(employee.last_punch_at), "", ""],
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

  const yAfter =
    ((doc as jsPDF & { lastAutoTable?: { finalY?: number } }).lastAutoTable?.finalY ?? startY) + 18;

  doc.setFontSize(11);
  doc.setTextColor(...SLATE_HEADER);
  doc.setFont("helvetica", "bold");
  doc.text("Daily attendance detail", 40, yAfter);
  doc.setFont("helvetica", "normal");
  doc.setTextColor(0, 0, 0);

  autoTable(doc, {
    startY: yAfter + 8,
    theme: "striped",
    head: [["Date", "In time", "Out time", "Total work (HH:mm)", "Absent", "Punches"]],
    body: rows.map((r) => [
      fmtDate(r.summary_date),
      fmtDateTime(r.first_check_in),
      fmtDateTime(r.last_check_out),
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
      3: { halign: "center" },
      4: { halign: "center" },
      5: { halign: "center", cellWidth: 52 },
    },
    margin: { left: 40, right: 40 },
  });

  tableFooter(doc, "Biometric attendance · read-only shadow report");
  doc.save(`employee_report_${safeFilename(employee.name)}_${toDate}.pdf`);
}

/** All-employees report: no Late column (per product requirement). */
export function downloadAttendanceSummaryPdf(args: {
  periodLabel: string;
  rows: Array<DailySummaryRow & { summary_date: string }>;
}): void {
  const { periodLabel, rows } = args;
  const doc = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4" });

  const startY = drawReportBanner(doc, "Attendance summary · all employees", [
    `Generated · ${new Intl.DateTimeFormat(undefined, { dateStyle: "long", timeStyle: "short" }).format(new Date())}`,
    `Coverage · ${periodLabel} · ${rows.length} row(s)`,
  ]);

  autoTable(doc, {
    startY,
    theme: "striped",
    head: [["Date", "Employee", "Device ID", "In time", "Out time", "Total work", "Absent"]],
    body: rows.map((r) => [
      fmtDate(r.summary_date),
      r.employee_name,
      r.device_user_id,
      fmtDateTime(r.first_check_in),
      fmtDateTime(r.last_check_out),
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
      0: { cellWidth: 86 },
      2: { cellWidth: 72 },
      5: { halign: "center", cellWidth: 64 },
      6: { halign: "center", cellWidth: 52 },
    },
    margin: { left: 40, right: 40 },
  });

  tableFooter(doc, "Biometric attendance · read-only shadow report");
  doc.save(`attendance_summary_${safeFilename(periodLabel)}.pdf`);
}
