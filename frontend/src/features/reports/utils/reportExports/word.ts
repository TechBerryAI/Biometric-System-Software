import {
  Document,
  HeadingLevel,
  Packer,
  Paragraph,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} from "docx";
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
import { fmtMinutes, safeFilename, triggerBlobDownload } from "./shared";

function headerCell(text: string): TableCell {
  return new TableCell({
    children: [new Paragraph({ children: [new TextRun({ text, bold: true })] })],
  });
}

function dataCell(text: string): TableCell {
  return new TableCell({
    children: [new Paragraph({ children: [new TextRun(text)] })],
  });
}

function buildTable(headers: string[], rows: string[][]): Table {
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [
      new TableRow({ children: headers.map(headerCell) }),
      ...rows.map((row) => new TableRow({ children: row.map(dataCell) })),
    ],
  });
}

async function saveDocument(doc: Document, filename: string): Promise<void> {
  const blob = await Packer.toBlob(doc);
  triggerBlobDownload(blob, filename);
}

export async function downloadEmployeeReportWord(args: EmployeeReportPayload): Promise<void> {
  const { employee, rows, fromDate, toDate } = args;

  const doc = new Document({
    sections: [
      {
        children: [
          new Paragraph({ text: "Employee attendance report", heading: HeadingLevel.HEADING_1 }),
          new Paragraph(`Generated · ${fmtGeneratedTimestamp()}`),
          new Paragraph(
            `Period · ${fmtDisplayDate(fromDate)} → ${fmtDisplayDate(toDate)} · ${employee.name} (${employee.device_user_id})`
          ),
          new Paragraph({ text: "Profile", heading: HeadingLevel.HEADING_2 }),
          buildTable(
            ["Field", "Value"],
            [
              ["Employee", employee.name],
              ["Device user ID", employee.device_user_id],
              ["Device UID", String(employee.device_uid ?? "—")],
              ["Department", employee.department ?? "—"],
              ["Privilege", String(employee.device_privilege ?? "—")],
              ["Device group", employee.device_group_id ?? "—"],
              ["Card", employee.device_card ?? "—"],
              ["Shift", `${employee.shift_start ?? "—"} → ${employee.shift_end ?? "—"}`],
              ["Total logs", String(employee.total_logs)],
              ["Attendance days", String(employee.total_attendance_days)],
              ["Complete days", String(employee.total_complete_days)],
              ["First punch", fmtDisplayDateTime(employee.first_punch_at)],
              ["Last punch", fmtDisplayDateTime(employee.last_punch_at)],
            ]
          ),
          new Paragraph({ text: "Daily attendance detail", heading: HeadingLevel.HEADING_2 }),
          buildTable(
            ["Date", "Day", "In time", "Out time", "Total work", "Absent", "Punches"],
            rows.map((r) => [
              fmtDisplayDate(r.summary_date),
              fmtDayOfWeek(r.summary_date),
              fmtDisplayDateTime(r.first_check_in),
              fmtDisplayDateTime(r.last_check_out),
              fmtMinutes(r.total_work_minutes),
              r.absent ? "Yes" : "No",
              String(r.punch_count),
            ])
          ),
        ],
      },
    ],
  });

  await saveDocument(doc, `employee_report_${safeFilename(employee.name)}_${toDate}.docx`);
}

export async function downloadAttendanceSummaryWord(args: AttendanceSummaryPayload): Promise<void> {
  const { periodLabel, rows } = args;

  const doc = new Document({
    sections: [
      {
        children: [
          new Paragraph({ text: "Attendance summary · all employees", heading: HeadingLevel.HEADING_1 }),
          new Paragraph(`Generated · ${fmtGeneratedTimestamp()}`),
          new Paragraph(`Coverage · ${periodLabel} · ${rows.length} row(s)`),
          buildTable(
            ["Date", "Day", "Employee", "Device ID", "In time", "Out time", "Total work", "Absent"],
            rows.map((r) => [
              fmtDisplayDate(r.summary_date),
              fmtDayOfWeek(r.summary_date),
              r.employee_name,
              r.device_user_id,
              fmtDisplayDateTime(r.first_check_in),
              fmtDisplayDateTime(r.last_check_out),
              fmtMinutes(r.total_work_minutes),
              r.first_check_in ? "No" : "Yes",
            ])
          ),
        ],
      },
    ],
  });

  await saveDocument(doc, `attendance_summary_${safeFilename(periodLabel)}.docx`);
}

export async function downloadDashboardReportWord(args: DashboardReportPayload): Promise<void> {
  const { mode, dateRange, kpis, deptMatrix, radar } = args;

  const doc = new Document({
    sections: [
      {
        children: [
          new Paragraph({ text: "Workforce intelligence report", heading: HeadingLevel.HEADING_1 }),
          new Paragraph(`Generated · ${fmtGeneratedTimestamp()}`),
          new Paragraph(`Mode · ${mode} · Range · ${dateRange}`),
          new Paragraph({ text: "KPIs", heading: HeadingLevel.HEADING_2 }),
          buildTable(
            ["KPI", "Value", "Trend", "Comparison", "Insight"],
            kpis.map((k) => [k.title, k.value, k.trend, k.comparison, k.insight])
          ),
          new Paragraph({ text: "Department matrix", heading: HeadingLevel.HEADING_2 }),
          buildTable(
            ["Rank", "Department", "Attendance %", "Punctuality %", "Avg hours", "Overtime %", "Absentee risk", "Productivity"],
            deptMatrix.map((d) => [
              String(d.rank),
              d.department,
              d.attendance.toFixed(1),
              d.punctuality.toFixed(1),
              d.avgHours.toFixed(2),
              d.overtimePct.toFixed(1),
              d.absenteeRisk.toFixed(1),
              d.productivity.toFixed(1),
            ])
          ),
          new Paragraph({ text: "Radar scores", heading: HeadingLevel.HEADING_2 }),
          buildTable(
            ["Metric", "Score"],
            radar.map((r) => [r.metric, r.score.toFixed(1)])
          ),
        ],
      },
    ],
  });

  await saveDocument(doc, `workforce-intelligence_${safeFilename(mode)}_${Date.now()}.docx`);
}
