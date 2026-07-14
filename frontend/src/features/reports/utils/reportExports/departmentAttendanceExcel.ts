import ExcelJS from "exceljs";
import type { DailySummaryRow, Employee } from "@/types";
import { safeFilename, triggerBlobDownload } from "./shared";

const HEADER_YELLOW = "FFFF00";
const TIMEZONE = "Asia/Kolkata";
const COLS = 7;

export type DepartmentAttendanceDay = {
  isoDate: string;
  summary: DailySummaryRow | null;
};

export type DepartmentAttendanceMember = {
  employee: Employee;
  days: DepartmentAttendanceDay[];
};

export type DepartmentAttendancePayload = {
  department: string;
  fromDate: string;
  toDate: string;
  members: DepartmentAttendanceMember[];
};

export type AttendanceMark = "Present" | "Week Off" | "Leave";

const thinBorder: Partial<ExcelJS.Borders> = {
  top: { style: "thin", color: { argb: "FF000000" } },
  left: { style: "thin", color: { argb: "FF000000" } },
  bottom: { style: "thin", color: { argb: "FF000000" } },
  right: { style: "thin", color: { argb: "FF000000" } },
};

const centerAlign: Partial<ExcelJS.Alignment> = {
  horizontal: "center",
  vertical: "middle",
  wrapText: true,
};

function parseISODate(isoDate: string): Date {
  return new Date(`${isoDate}T12:00:00`);
}

function ordinal(n: number): string {
  const v = n % 100;
  if (v >= 11 && v <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

/** e.g. 26-May-26 */
export function fmtReportDate(isoDate: string): string {
  const d = parseISODate(isoDate);
  const day = String(d.getDate()).padStart(2, "0");
  const mon = d.toLocaleString("en-GB", { month: "short" });
  const yy = String(d.getFullYear()).slice(-2);
  return `${day}-${mon}-${yy}`;
}

/** e.g. May - June */
export function fmtMonthSpan(fromISO: string, toISO: string): string {
  const from = parseISODate(fromISO);
  const to = parseISODate(toISO);
  const a = from.toLocaleString("en-GB", { month: "long" });
  const b = to.toLocaleString("en-GB", { month: "long" });
  return a === b ? a : `${a} - ${b}`;
}

/** e.g. Mark the Attendance from 26th May to 25th June 2026 */
export function fmtAttendanceInstruction(fromISO: string, toISO: string): string {
  const from = parseISODate(fromISO);
  const to = parseISODate(toISO);
  const fromPart = `${ordinal(from.getDate())} ${from.toLocaleString("en-GB", { month: "long" })}`;
  const toPart = `${ordinal(to.getDate())} ${to.toLocaleString("en-GB", { month: "long" })} ${to.getFullYear()}`;
  return `Mark the Attendance from ${fromPart} to ${toPart}`;
}

/** e.g. 9:30am */
export function fmtPunchAmPm(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  const parts = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: TIMEZONE,
  }).formatToParts(d);
  const hour = parts.find((p) => p.type === "hour")?.value ?? "";
  const minute = parts.find((p) => p.type === "minute")?.value ?? "";
  const dayPeriod = (parts.find((p) => p.type === "dayPeriod")?.value ?? "").toLowerCase();
  return `${hour}:${minute}${dayPeriod}`;
}

export function fmtTotalHours(minutes: number | null | undefined): string {
  if (minutes == null) return "";
  const hours = minutes / 60;
  if (Number.isInteger(hours)) return String(hours);
  return hours.toFixed(1).replace(/\.0$/, "");
}

export function resolveAttendanceMark(isoDate: string, summary: DailySummaryRow | null): AttendanceMark {
  if (summary?.first_check_in) return "Present";
  // Classify weekends in app timezone so export matches India workweek.
  const weekday = new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    timeZone: TIMEZONE,
  }).format(new Date(`${isoDate}T12:00:00+05:30`));
  if (weekday === "Sat" || weekday === "Sun") return "Week Off";
  return "Leave";
}

function applyCenterBorder(cell: ExcelJS.Cell, bold = false): void {
  cell.alignment = centerAlign;
  cell.border = thinBorder;
  cell.font = { bold, name: "Calibri", size: 11 };
}

function sanitizeSheetName(name: string, used: Set<string>): string {
  let base = name.replace(/[\\/?*[\]:]/g, " ").trim() || "Employee";
  if (base.length > 28) base = base.slice(0, 28).trim();
  let candidate = base;
  let n = 2;
  while (used.has(candidate.toLowerCase())) {
    const suffix = ` (${n})`;
    candidate = `${base.slice(0, Math.max(1, 31 - suffix.length))}${suffix}`;
    n += 1;
  }
  used.add(candidate.toLowerCase());
  return candidate;
}

function fillYellowHeader(row: ExcelJS.Row): void {
  for (let col = 1; col <= COLS; col++) {
    const cell = row.getCell(col);
    cell.fill = {
      type: "pattern",
      pattern: "solid",
      fgColor: { argb: `FF${HEADER_YELLOW}` },
    };
    cell.font = { bold: true, name: "Calibri", size: 11 };
    cell.alignment = centerAlign;
    cell.border = thinBorder;
  }
}

function writeMemberSheet(
  workbook: ExcelJS.Workbook,
  sheetName: string,
  member: DepartmentAttendanceMember,
  fromDate: string,
  toDate: string
): void {
  const { employee, days } = member;
  const sheet = workbook.addWorksheet(sheetName, {
    views: [{ showGridLines: true }],
  });

  sheet.columns = [
    { key: "a", width: 12 },
    { key: "b", width: 16 },
    { key: "c", width: 36 },
    { key: "d", width: 12 },
    { key: "e", width: 12 },
    { key: "f", width: 12 },
    { key: "g", width: 16 },
  ];

  // Row 1 — labels
  const headerLabels = [
    "Employee Code",
    "Name",
    "Month",
    "",
    "",
    "",
    "Reporting Manager",
  ];
  const row1 = sheet.getRow(1);
  headerLabels.forEach((label, i) => {
    row1.getCell(i + 1).value = label;
  });
  fillYellowHeader(row1);
  sheet.mergeCells(1, 3, 1, 6);

  // Row 2 — values
  const row2 = sheet.getRow(2);
  row2.getCell(1).value = employee.device_user_id;
  row2.getCell(2).value = employee.name;
  row2.getCell(3).value = fmtMonthSpan(fromDate, toDate);
  row2.getCell(7).value = "";
  for (let col = 1; col <= COLS; col++) {
    applyCenterBorder(row2.getCell(col));
  }
  sheet.mergeCells(2, 3, 2, 6);

  // Row 3 — instruction
  const row3 = sheet.getRow(3);
  row3.getCell(1).value = fmtAttendanceInstruction(fromDate, toDate);
  sheet.mergeCells(3, 1, 3, 7);
  applyCenterBorder(row3.getCell(1), true);
  for (let col = 2; col <= COLS; col++) {
    applyCenterBorder(row3.getCell(col), true);
  }

  // Row 4 — table headers
  const colHeaders = [
    "Sr.No",
    "Date (DD-MMM-YY)",
    "Attendance(Present/Week Off/WFH/ Leave)",
    "Time In",
    "Time Out",
    "Total Hours",
    "Remarks By RM",
  ];
  const row4 = sheet.getRow(4);
  colHeaders.forEach((label, i) => {
    const cell = row4.getCell(i + 1);
    cell.value = label;
    applyCenterBorder(cell, true);
  });

  // Data rows
  days.forEach((day, index) => {
    const excelRow = index + 5;
    const row = sheet.getRow(excelRow);
    const mark = resolveAttendanceMark(day.isoDate, day.summary);

    row.getCell(1).value = index + 1;
    row.getCell(2).value = fmtReportDate(day.isoDate);

    if (mark === "Present") {
      row.getCell(3).value = "Present";
      row.getCell(4).value = fmtPunchAmPm(day.summary?.first_check_in);
      row.getCell(5).value = fmtPunchAmPm(day.summary?.last_check_out);
      row.getCell(6).value = fmtTotalHours(day.summary?.total_work_minutes);
      row.getCell(7).value = "";
    } else {
      row.getCell(3).value = mark;
      row.getCell(4).value = "";
      row.getCell(5).value = "";
      row.getCell(6).value = "";
      row.getCell(7).value = "";
      sheet.mergeCells(excelRow, 3, excelRow, 5);
    }

    for (let col = 1; col <= COLS; col++) {
      applyCenterBorder(row.getCell(col));
    }
  });
}

export async function downloadDepartmentAttendanceExcel(
  args: DepartmentAttendancePayload
): Promise<void> {
  const { department, fromDate, toDate, members } = args;
  if (members.length === 0) {
    throw new Error(`No employees found in department “${department}”.`);
  }

  const workbook = new ExcelJS.Workbook();
  workbook.creator = "Biometric Attendance";
  workbook.created = new Date();

  const usedNames = new Set<string>();
  for (const member of members) {
    const sheetName = sanitizeSheetName(member.employee.name, usedNames);
    writeMemberSheet(workbook, sheetName, member, fromDate, toDate);
  }

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  triggerBlobDownload(
    blob,
    `department_attendance_${safeFilename(department)}_${fromDate}_${toDate}.xlsx`
  );
}
